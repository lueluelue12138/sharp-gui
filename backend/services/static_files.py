import os

from backend import runtime

WORKSPACE_FILES_PREFIX = "workspace/"
DEFAULT_FILE_CACHE_SECONDS = 3600
THUMBNAIL_CACHE_SECONDS = 86400

SENSITIVE_FILE_NAMES = frozenset({
    "config.json",
    "app.py",
    "cert.pem",
    "key.pem",
    ".env",
})
SENSITIVE_FILE_EXTENSIONS = frozenset({
    ".pem",
    ".key",
    ".crt",
    ".p12",
    ".pfx",
    ".env",
})


def is_path_inside(path, root):
    """判断路径是否位于指定根目录内，兼容 Windows 跨盘符场景。"""
    try:
        abs_path = os.path.abspath(path)
        abs_root = os.path.abspath(root)
        common_path = os.path.commonpath([abs_path, abs_root])
        return os.path.normcase(common_path) == os.path.normcase(abs_root)
    except ValueError:
        return False


def is_real_path_inside(path, root):
    """判断真实路径是否在 root 内，避免符号链接逃逸。"""
    try:
        abs_path = os.path.realpath(os.path.abspath(path))
        abs_root = os.path.realpath(os.path.abspath(root))
        common_path = os.path.commonpath([abs_path, abs_root])
        return os.path.normcase(common_path) == os.path.normcase(abs_root)
    except ValueError:
        return False


def to_url_path(path):
    """将本地路径片段转换为 URL 路径片段。"""
    return path.replace(os.sep, "/").replace("\\", "/")


def get_relative_files_path(path, paths):
    """将绝对路径转换为 /files 可用的相对路径。"""
    abs_path = os.path.abspath(path)

    if is_path_inside(abs_path, runtime.BASE_DIR):
        return to_url_path(os.path.relpath(abs_path, runtime.BASE_DIR))

    if is_path_inside(abs_path, paths.workspace_folder):
        workspace_relative_path = to_url_path(os.path.relpath(abs_path, paths.workspace_folder))
        return f"{WORKSPACE_FILES_PREFIX}{workspace_relative_path}"

    raise ValueError(f"File path is outside served roots: {path}")


def is_sensitive_served_file(abs_path):
    """判断目标文件是否属于敏感类型，命中则不应通过任何静态路由服务。"""
    name = os.path.basename(abs_path)
    if name.lower() in SENSITIVE_FILE_NAMES:
        return True
    _, ext = os.path.splitext(name)
    return ext.lower() in SENSITIVE_FILE_EXTENSIONS


def resolve_served_file_path(paths, served_root, served_filename):
    """解析 /files 请求，并强制约束在白名单服务根内。"""
    if not served_filename or os.path.isabs(served_filename):
        return None

    candidate = os.path.realpath(os.path.join(served_root, served_filename))
    safe_roots = tuple(
        root
        for root in paths.allowed_file_serve_roots
        if is_real_path_inside(root, paths.workspace_folder)
    )
    if not any(
        is_real_path_inside(candidate, root)
        and is_real_path_inside(candidate, paths.workspace_folder)
        for root in safe_roots
    ):
        return None

    if is_sensitive_served_file(candidate):
        return None

    if not os.path.isfile(candidate):
        return None

    return candidate


def resolve_files_route_path(paths, filename):
    normalized_filename = filename.replace("\\", "/")
    served_root = runtime.BASE_DIR
    served_filename = normalized_filename
    if normalized_filename.startswith(WORKSPACE_FILES_PREFIX):
        served_root = paths.workspace_folder
        served_filename = normalized_filename[len(WORKSPACE_FILES_PREFIX):]

    resolved_path = resolve_served_file_path(paths, served_root, served_filename)
    if not resolved_path:
        return None, None, None

    thumbnail_prefixes = (
        get_relative_files_path(paths.thumbnail_folder, paths) + "/",
        get_relative_files_path(paths.model_asset_thumbnail_folder, paths) + "/",
    )
    cache_timeout = (
        THUMBNAIL_CACHE_SECONDS
        if normalized_filename.startswith(thumbnail_prefixes)
        else DEFAULT_FILE_CACHE_SECONDS
    )
    return resolved_path, os.path.basename(resolved_path), cache_timeout
