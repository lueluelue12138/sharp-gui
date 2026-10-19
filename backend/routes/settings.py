import os

from flask import Blueprint, current_app, g, jsonify, request

from backend import runtime
from backend.config_storage import ConfigData, ConfigStorageError, read_legacy_config
from backend.config import (
    load_config,
    normalize_video_reconstruction_config,
    normalize_access_control_config,
    save_config,
)
from backend.services.folder_picker import browse_folder_native
from backend.services.photo_gallery import migrate_photo_gallery_roots_config
from backend.services.workspace_lock import (
    WorkspaceInUseError,
    WorkspaceInstanceLock,
    WorkspaceUnavailableError,
)
from backend.server import restart_process_later

bp = Blueprint("settings", __name__)


def _workspace_paths_match(first, second):
    """Compare workspace paths using their normalized real locations."""
    first_path = os.path.normcase(os.path.realpath(os.path.abspath(first)))
    second_path = os.path.normcase(os.path.realpath(os.path.abspath(second)))
    return first_path == second_path


@bp.route("/api/settings", methods=["GET", "POST"])
def settings():
    """设置接口。"""
    paths = current_app.config["PATH_CONTEXT"]
    is_local = g.is_owner
    config = load_config()

    if request.method == "GET":
        video_config, _ = normalize_video_reconstruction_config(config)
        return jsonify({
            "is_local": is_local,
            "server_instance_id": current_app.config["SERVER_INSTANCE_ID"],
            "workspace_folder": paths.workspace_folder if is_local else None,
            "model_format": config.get("model_format", "spz"),
            "input_folder": paths.input_folder if is_local else None,
            "output_folder": paths.output_folder if is_local else None,
            "video_reconstruction": video_config,
            'config_file': runtime.get_config_file() if is_local else None,
            'config_scope': ('explicit' if os.environ.get('SHARP_CONFIG_FILE', '').strip() else 'global') if is_local else None,
        })

    if not is_local:
        return jsonify({"error": "Settings can only be modified from localhost"}), 403

    data = request.get_json() or {}
    new_config = load_config()

    if "workspace_folder" in data:
        target_workspace = data["workspace_folder"]
        if not isinstance(target_workspace, str) or not target_workspace.strip():
            return jsonify({
                "success": False,
                "error": "Workspace folder must be a non-empty path.",
                "code": "invalid_workspace_folder",
            }), 400
        target_workspace = target_workspace.strip()

        if not _workspace_paths_match(paths.workspace_folder, target_workspace):
            workspace_probe = WorkspaceInstanceLock(target_workspace)
            try:
                workspace_probe.acquire()
            except WorkspaceInUseError as exc:
                return jsonify({
                    "success": False,
                    "error": str(exc),
                    "code": "workspace_in_use",
                }), 409
            except WorkspaceUnavailableError as exc:
                return jsonify({
                    "success": False,
                    "error": str(exc),
                    "code": "workspace_unavailable",
                }), 409
            finally:
                workspace_probe.release()

        # 切换工作目录前，先把可能残留的旧全局相册配置归档到“当前”工作目录的分桶，
        # 避免切换后旧相册泄漏到新工作目录。相册按工作目录分桶记忆，切回旧目录可恢复。
        migrate_photo_gallery_roots_config(new_config)
        new_config["workspace_folder"] = target_workspace
        new_config.pop("input_folder", None)
        new_config.pop("output_folder", None)

    if "model_format" in data:
        fmt = data["model_format"]
        if fmt in ("ply", "spz"):
            new_config["model_format"] = fmt

    if "video_reconstruction" in data:
        incoming_video_config = data.get("video_reconstruction")
        if isinstance(incoming_video_config, dict):
            current_video_config, _ = normalize_video_reconstruction_config(new_config)
            current_video_config.update(incoming_video_config)
            new_config["video_reconstruction"] = current_video_config
            normalize_video_reconstruction_config(new_config)

    save_config(new_config)

    needs_restart = "workspace_folder" in data

    return jsonify({
        "success": True,
        "needs_restart": needs_restart,
        "message": "Settings saved." + (" Restart server to apply changes." if needs_restart else ""),
    })


@bp.route('/api/settings/restore', methods=['POST'])
def restore_configuration():
    """本机选择旧目录后预览、确认并恢复；不复制或清理旧工作区。"""
    if not g.is_owner:
        return jsonify({'error': 'Only localhost can restore configuration.'}), 403
    data = request.get_json(silent=True)
    folder = data.get('folder') if isinstance(data, dict) else None
    if not isinstance(folder, str) or not folder.strip() or '\0' in folder or not os.path.isabs(folder):
        raise ConfigStorageError('config_source_unavailable', 400)
    source_path = os.path.join(folder, 'config.json')
    restored, source_revision = read_legacy_config(source_path)
    current = load_config()
    migrate_photo_gallery_roots_config(restored)
    normalize_video_reconstruction_config(restored)
    # 门禁信息仅在服务内迁移，不进入预览响应。
    normalize_access_control_config(restored)
    summary = {
        'folder': folder, 'source_revision': source_revision, 'target_revision': current.revision,
        'workspace_folder': restored['workspace_folder'],
        'album_count': sum(len(roots) for roots in restored.get('photo_gallery_roots_by_workspace', {}).values() if isinstance(roots, list)),
    }
    if data.get('confirm') is not True:
        return jsonify(summary)
    if data.get('source_revision') != source_revision or data.get('target_revision') != current.revision:
        raise ConfigStorageError('config_conflict', 409)
    manager = current_app.config['TASK_MANAGER']
    with manager.task_lock:
        if getattr(manager, '_configuration_enqueuing', 0) or any(
                task.get('status') in ('pending', 'running', 'processing') for task in manager.task_status.values()):
            raise ConfigStorageError('config_tasks_active', 409)
        probe = WorkspaceInstanceLock(restored['workspace_folder'])
        try:
            if not _workspace_paths_match(current_app.config['PATH_CONTEXT'].workspace_folder, restored['workspace_folder']):
                probe.acquire()
            replacement = ConfigData(restored, current.source_path, current.revision)
            save_config(replacement, backup=True)
        except (WorkspaceInUseError, WorkspaceUnavailableError) as exc:
            raise ConfigStorageError('config_workspace_unavailable', 409) from exc
        finally:
            probe.release()
        manager._configuration_restore_pending = True
        current_app.config['CONFIG_RESTORE_PENDING'] = True
    restart_process_later()
    return jsonify({'success': True, 'server_instance_id': current_app.config['SERVER_INSTANCE_ID']})


@bp.route("/api/restart", methods=["POST"])
def restart_server():
    """重启服务器。"""
    if not g.is_owner:
        return jsonify({"error": "Restart can only be triggered from localhost"}), 403

    restart_process_later()

    return jsonify({
        "success": True,
        "server_instance_id": current_app.config["SERVER_INSTANCE_ID"],
        "message": "Server will restart in 1 second...",
    })


@bp.route("/api/browse-folder", methods=["POST"])
def browse_folder():
    """调用系统原生文件夹选择对话框。"""
    if not g.is_owner:
        return jsonify({"error": "Only available from localhost"}), 403

    data = request.get_json() or {}
    title = data.get("title", "Select Folder")
    initial_dir = data.get("initial_dir", os.path.expanduser("~"))
    payload, status_code = browse_folder_native(title, initial_dir)
    return jsonify(payload), status_code
