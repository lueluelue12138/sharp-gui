"""旧便携包的轻量升级入口，发布时与固定版本 helper 一起交付。"""

import argparse
import hashlib
import json
import os
import socket
import sys
from pathlib import Path


CODE_ROOT = Path(__file__).resolve().parent
BASE_DIR = CODE_ROOT.parent
if CODE_ROOT.name == 'tools' and not (CODE_ROOT / 'tool.json').is_file():
    CODE_ROOT = BASE_DIR
sys.path.insert(0, str(CODE_ROOT))


def verify_tool():
    if CODE_ROOT == BASE_DIR:
        return  # 仓库内开发入口，正式产物一定包含 tool.json。
    manifest_path = CODE_ROOT / 'tool.json'
    if manifest_path.resolve() != manifest_path.absolute():
        raise RuntimeError('Invalid migration tool / 升级工具清单无效')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schemaVersion') != 1 or manifest.get('repository') != 'lueluelue12138/sharp-gui':
        raise RuntimeError('Invalid migration tool / 升级工具来源无效')
    expected = {
        'bootstrap.py', 'application_dependencies.py', 'backend/__init__.py',
        'backend/services/__init__.py', 'backend/services/self_update.py',
        'backend/services/portable_compatibility.py',
    }
    if set(manifest.get('files', {})) != expected:
        raise RuntimeError('Invalid migration tool / 升级工具清单无效')
    for name, checksum in manifest['files'].items():
        path = CODE_ROOT / name
        if path.resolve() != path.absolute() or hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise RuntimeError('Migration tool integrity failed / 升级工具校验失败')


def server_running():
    for port in {5050, int(os.environ.get('SHARP_PORT', '5050'))}:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.4):
                return True
        except OSError:
            pass
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description='Upgrade an existing managed portable package / 升级现有受管便携包')
    parser.add_argument('--channel', choices=('stable', 'latest'), default='stable')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--yes', '-y', action='store_true')
    args = parser.parse_args(argv)
    try:
        verify_tool()
        from backend.services.self_update import (
            SelfUpdateManager, UpdateError, get_installed_identity, load_update_state,
            prepare_cli_operation, run_update_operation,
            recover_interrupted_operation,
        )
        identity = get_installed_identity(BASE_DIR)
        if identity.get('installation_kind') != 'portable' or not identity.get('managed'):
            raise UpdateError('update_installation_unsupported')
        if identity.get('dirty'):
            raise UpdateError('update_worktree_dirty')
        # 旧服务没有安全的停服握手，绝不强杀端口或从不可信 PID 文件取进程。
        if not args.check and server_running():
            print('Close Sharp GUI normally, then run this tool again. / 请先正常关闭 Sharp GUI，再运行升级工具。')
            return 2
        if not args.check and recover_interrupted_operation(BASE_DIR):
            print('Interrupted update recovered. Start Sharp GUI normally. / 已恢复中断的更新，请正常启动。')
            return 0
        manager = SelfUpdateManager(base_dir=BASE_DIR)
        manager.check(args.channel, is_owner=True)
        candidate = load_update_state(BASE_DIR)['channels'][args.channel]
        print(f"Target / 目标版本: {candidate['display_version']} ({candidate['short_sha']})")
        if not candidate.get('compatible'):
            raise UpdateError(candidate.get('compatibility_code') or 'update_incompatible')
        if args.check or not candidate.get('update_available'):
            print('Check complete / 检查完成')
            return 0
        if not args.yes:
            answer = input('Apply update and keep your runtime/data? / 保留运行环境和数据并升级？ [y/N]: ')
            if answer.strip().lower() not in {'y', 'yes'}:
                return 0
        operation = prepare_cli_operation(BASE_DIR, args.channel, candidate)
        if not run_update_operation(BASE_DIR, operation['id'], wait_for_server=False, relaunch=False):
            final = load_update_state(BASE_DIR).get('operation') or {}
            print(f"Upgrade failed / 升级失败: {final.get('error_code')}", file=sys.stderr)
            if final.get('rolled_back'):
                print('Previous version restored / 已恢复原版本')
            return 1
        print('Upgrade complete. Start portable-run.bat. / 升级完成，请运行 portable-run.bat。')
        return 0
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print(f"Upgrade error / 升级错误: {getattr(exc, 'code', 'update_bootstrap_tool_invalid')}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
