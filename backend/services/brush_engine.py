"""固定 Brush CLI 的定位、训练参数、数据适配和输出校验。"""

from __future__ import annotations

import math
import os
import re
import shutil
import struct
import tempfile
import time
from pathlib import Path, PurePosixPath


BRUSH_VERSION = '1.0.0'
BRUSH_COMMIT = '866a7d65b4d6a591ba0d52a88f8b20ea3465c1e5'
BRUSH_RELEASE_TAG = 'ooo-v1.0.0'
BRUSH_INSTALL_RELATIVE_PATH = Path('.sharp-gui-tools') / 'brush' / BRUSH_RELEASE_TAG
BRUSH_RECIPE_VERSION = 'ooobrush-video-v1'
BRUSH_EXPORT_NAME = 'final.ply'
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
_REFINE_PROGRESS = re.compile(r'\bRefine iter\s+(\d+),\s*([\d,]+)\s+splats\b', re.IGNORECASE)
_BAR_PROGRESS = re.compile(r'\b(\d+)\s*/\s*(\d+)\s+Steps\b', re.IGNORECASE)
_TRAIN_PROGRESS = re.compile(r'\bTraining progress:\s*iteration=(\d+)\s+total=(\d+)\b')
_PLY_TYPES = {
    'char': 'i1', 'int8': 'i1', 'uchar': 'u1', 'uint8': 'u1',
    'short': '<i2', 'int16': '<i2', 'ushort': '<u2', 'uint16': '<u2',
    'int': '<i4', 'int32': '<i4', 'uint': '<u4', 'uint32': '<u4',
    'float': '<f4', 'float32': '<f4', 'double': '<f8', 'float64': '<f8',
}
_GAUSSIAN_PROPERTIES = (
    'x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2', 'opacity',
    'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3',
)


def find_brush_executable(base_dir=None, environ=None):
    """优先使用固定包内引擎，再查显式配置和 PATH；导入时不启动进程。"""
    root = Path(base_dir) if base_dir is not None else _PROJECT_ROOT
    process_env = os.environ if environ is None else environ
    names = ('brush-cli.exe', 'brush-cli') if os.name == 'nt' else ('brush-cli', 'brush-cli.exe')
    for name in names:
        bundled = root / BRUSH_INSTALL_RELATIVE_PATH / name
        if bundled.is_file():
            return str(bundled.resolve())
    for key in ('SHARP_BRUSH_EXECUTABLE', 'BRUSH_EXECUTABLE'):
        configured = process_env.get(key)
        if configured:
            resolved = shutil.which(configured, path=process_env.get('PATH', ''))
            candidate = Path(resolved or configured).expanduser()
            if candidate.is_file():
                return str(candidate.resolve())
    for name in names:
        resolved = shutil.which(name, path=process_env.get('PATH', ''))
        if resolved:
            return str(Path(resolved).resolve())
    return None


def _profile_value(profile, keys, default):
    for key in keys:
        if profile.get(key) is not None:
            return profile[key]
    return default


def _positive_integer(value, name):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a positive integer')
    integer = int(value)
    if integer <= 0 or float(value) != integer:
        raise ValueError(f'{name} must be a positive integer')
    return integer


def build_brush_train_command(executable, dataset_dir, output_dir, profile):
    """将版本化配方转换为固定 OOOBrush CLI，保留完整 SH 和尺度滤波导出。"""
    steps = _positive_integer(_profile_value(
        profile, ('brush_iterations', 'max_num_iterations', 'total_steps'), 30000,
    ), 'total_steps')
    resolution = _positive_integer(_profile_value(
        profile, ('brush_max_resolution', 'max_resolution'), 1600,
    ), 'max_resolution')
    refine_every = _positive_integer(_profile_value(
        profile, ('brush_refine_every', 'refine_every'), 200,
    ), 'refine_every')
    command = [
        str(executable), '--total-train-iters', str(steps), '--max-resolution', str(resolution),
        '--refine-every', str(refine_every), '--sh-degree', '3',
        '--min-scale-factor', '0.1',
    ]
    max_splats = _profile_value(profile, ('brush_max_splats', 'max_splats'), None)
    if max_splats is not None:
        command.extend(['--max-splats', str(_positive_integer(max_splats, 'max_splats'))])
    grad_threshold = _profile_value(
        profile, ('brush_growth_grad_threshold', 'growth_grad_threshold'), None,
    )
    if grad_threshold is not None:
        threshold = float(grad_threshold)
        if not math.isfinite(threshold) or threshold <= 0:
            raise ValueError('growth_grad_threshold must be finite and positive')
        command.extend(['--growth-grad-threshold', str(threshold)])
    select_fraction = _profile_value(
        profile, ('brush_growth_select_fraction', 'growth_select_fraction'), None,
    )
    if select_fraction is not None:
        fraction = float(select_fraction)
        if not math.isfinite(fraction) or not 0 < fraction <= 1:
            raise ValueError('growth_select_fraction must be in (0, 1]')
        command.extend(['--growth-select-fraction', str(fraction)])
    growth_stop = _profile_value(
        profile, ('brush_growth_stop_iter', 'growth_stop_iter'), None,
    )
    if growth_stop is not None:
        stop = _positive_integer(growth_stop, 'growth_stop_iter')
        if stop > steps:
            raise ValueError('growth_stop_iter cannot exceed total_steps')
        command.extend(['--growth-stop-iter', str(stop)])
    # positional 数据源使官方 CLI 默认关闭 viewer，不打开额外原生窗口。
    command.extend([
        '--export-every', str(steps), '--export-path', str(Path(output_dir).resolve()),
        '--export-name', BRUSH_EXPORT_NAME, str(Path(dataset_dir).resolve()),
    ])
    return command


def build_brush_environment(base_env=None, force_discrete_gpu=True):
    """仅给训练子进程选择独显和日志，保留用户显式设备配置。"""
    process_env = dict(os.environ if base_env is None else base_env)
    if force_discrete_gpu:
        process_env.setdefault('CUBECL_WGPU_DEFAULT_DEVICE', 'DiscreteGpu(0)')
        if os.name == 'nt':
            process_env.setdefault('DISABLE_LAYER_AMD_SWITCHABLE_GRAPHICS_1', '1')
    filters = 'brush_cli=info,brush_process=info,cubecl_wgpu=info,burn_wgpu=info'
    previous = process_env.get('RUST_LOG', '')
    process_env['RUST_LOG'] = f'{previous},{filters}' if previous else filters
    return process_env


def parse_brush_progress(line, total_steps):
    """读取官方 Refine 日志或终端 Steps 进度，不根据耗时编造进度。"""
    cleaned = _ANSI_ESCAPE.sub('', str(line))
    match = _REFINE_PROGRESS.search(cleaned)
    splat_count = None
    if match:
        step = int(match.group(1))
        splat_count = int(match.group(2).replace(',', ''))
        total = int(total_steps)
    else:
        match = _TRAIN_PROGRESS.search(cleaned) or _BAR_PROGRESS.search(cleaned)
        if not match:
            return None
        step, total = int(match.group(1)), int(match.group(2))
        if total_steps and total != int(total_steps):
            return None
    if total <= 0 or not 0 <= step <= total:
        return None
    progress = {'step': step, 'iteration': step, 'total_steps': total, 'progress': step / total}
    if splat_count is not None:
        progress['splat_count'] = splat_count
    return progress


def _read_exact(stream, size):
    payload = stream.read(size)
    if len(payload) != size:
        raise ValueError('Truncated COLMAP model')
    return payload


def _read_binary_image_names(path):
    names = []
    with path.open('rb') as stream:
        image_count = struct.unpack('<Q', _read_exact(stream, 8))[0]
        # 每条图像记录至少含 64 字节位姿、一个名称终止字节和 8 字节观测数。
        if image_count > max(0, (path.stat().st_size - 8) // 73):
            raise ValueError('Invalid COLMAP image count')
        for _ in range(image_count):
            _read_exact(stream, 64)
            name = bytearray()
            while True:
                byte = _read_exact(stream, 1)
                if byte == b'\0':
                    break
                name.extend(byte)
                if len(name) > 4096:
                    raise ValueError('COLMAP image name is too long')
            names.append(name.decode('utf-8'))
            observations = struct.unpack('<Q', _read_exact(stream, 8))[0]
            offset = observations * 24
            if stream.tell() + offset > path.stat().st_size:
                raise ValueError('Truncated COLMAP image observations')
            stream.seek(offset, 1)
        if stream.read(1):
            raise ValueError('Unexpected COLMAP image data')
    return names


def _read_text_image_names(path):
    names = []
    with path.open('r', encoding='utf-8') as stream:
        for line in stream:
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            fields = line.strip().split(maxsplit=9)
            if len(fields) != 10:
                raise ValueError('Invalid COLMAP image record')
            int(fields[0])
            int(fields[8])
            names.append(fields[9])
            # 第二行可能为空，不能提前过滤空行而把下一条位姿当作观测。
            if stream.readline() == '':
                raise ValueError('Missing COLMAP image observations')
    return names


def _point_count(path):
    if path.suffix == '.bin':
        with path.open('rb') as stream:
            count = struct.unpack('<Q', _read_exact(stream, 8))[0]
        if count > max(0, (path.stat().st_size - 8) // 51):
            raise ValueError('Invalid COLMAP point count')
        return count
    with path.open('r', encoding='utf-8') as stream:
        return sum(1 for line in stream if line.strip() and not line.lstrip().startswith('#'))


def _within(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def inspect_colmap_models(data_dir):
    """只读统计 COLMAP 子模型，按注册图像数、稀疏点数选择最完整模型。"""
    root = Path(data_dir).resolve()
    if not root.is_dir():
        raise ValueError('COLMAP dataset directory is missing')
    directories = {root}
    for location in (root / 'colmap' / 'sparse', root / 'sparse'):
        if location.is_dir():
            for name in ('images.bin', 'images.txt'):
                directories.update(path.parent for path in location.rglob(name))
    models = []
    errors = []
    for directory in sorted(directories):
        for extension in ('bin', 'txt'):
            files = [directory / f'{name}.{extension}' for name in ('cameras', 'images', 'points3D')]
            if not all(path.is_file() for path in files):
                continue
            if not all(_within(path, root) for path in files):
                raise ValueError('COLMAP model escapes the dataset directory')
            try:
                names = (_read_binary_image_names(files[1]) if extension == 'bin'
                         else _read_text_image_names(files[1]))
                if len(set(names)) != len(names):
                    raise ValueError('COLMAP model contains duplicate image names')
                points = _point_count(files[2])
            except (OSError, UnicodeError, ValueError, struct.error) as error:
                errors.append(f'{directory.name}: {error}')
                continue
            models.append({
                'model_dir': str(directory), 'source_model_dir': str(directory),
                'registered_images': len(names), 'sfm_points': points,
                'image_names': names, 'model_format': extension,
            })
            break
    if not models:
        detail = '; '.join(errors[:3])
        raise ValueError('No complete COLMAP model was found' + (f': {detail}' if detail else ''))
    best = max(models, key=lambda model: (model['registered_images'], model['sfm_points']))
    return {**best, 'models': [{key: value for key, value in model.items() if key != 'image_names'}
                             for model in models]}


def _safe_image_path(name):
    relative = PurePosixPath(name.replace('\\', '/'))
    if relative.is_absolute() or not relative.parts or any(part in ('.', '..') or ':' in part
                                                          for part in relative.parts):
        raise ValueError('Unsafe COLMAP image path')
    return Path(*relative.parts)


def _quaternion_to_rotation(quaternion):
    """COLMAP Hamilton 四元数 (w, x, y, z) 转为 world-to-camera 旋转。"""
    import numpy as np

    quaternion = np.asarray(quaternion, dtype=np.float64)
    length = np.linalg.norm(quaternion)
    if quaternion.shape != (4,) or not np.isfinite(length) or length < 1e-12:
        raise ValueError('Invalid COLMAP camera quaternion')
    w, x, y, z = quaternion / length
    return np.asarray([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _rotation_to_quaternion(rotation):
    """按最大对角分量分支，避免接近 180 度时除以微小的四元数 w。"""
    import numpy as np

    matrix = np.asarray(rotation, dtype=np.float64)
    trace = np.trace(matrix)
    if trace > 0:
        size = math.sqrt(max(0.0, trace + 1.0)) * 2
        quaternion = np.asarray([
            size / 4, (matrix[2, 1] - matrix[1, 2]) / size,
            (matrix[0, 2] - matrix[2, 0]) / size, (matrix[1, 0] - matrix[0, 1]) / size,
        ])
    else:
        largest = int(np.argmax(np.diag(matrix)))
        other, last = (largest + 1) % 3, (largest + 2) % 3
        size = math.sqrt(max(0.0, 1 + matrix[largest, largest]
                             - matrix[other, other] - matrix[last, last])) * 2
        quaternion = np.zeros(4)
        quaternion[0] = (matrix[last, other] - matrix[other, last]) / size
        quaternion[largest + 1] = size / 4
        quaternion[other + 1] = (matrix[other, largest] + matrix[largest, other]) / size
        quaternion[last + 1] = (matrix[last, largest] + matrix[largest, last]) / size
    quaternion /= np.linalg.norm(quaternion)
    if quaternion[0] < 0:
        quaternion = -quaternion
    return quaternion


def _read_colmap_poses(model_dir, extension):
    """读取所有已注册相机的 R、t；保留 COLMAP 的 OpenCV 相机约定。"""
    import numpy as np

    path = Path(model_dir) / f'images.{extension}'
    poses = []
    if extension == 'bin':
        with path.open('rb') as stream:
            count = struct.unpack('<Q', _read_exact(stream, 8))[0]
            for _ in range(count):
                fields = struct.unpack('<i7di', _read_exact(stream, 64))
                rotation = _quaternion_to_rotation(fields[1:5])
                translation = np.asarray(fields[5:8])
                name = bytearray()
                while True:
                    byte = _read_exact(stream, 1)
                    if byte == b'\0':
                        break
                    name.extend(byte)
                    if len(name) > 4096:
                        raise ValueError('COLMAP image name is too long')
                observations = struct.unpack('<Q', _read_exact(stream, 8))[0]
                if stream.tell() + observations * 24 > path.stat().st_size:
                    raise ValueError('Truncated COLMAP image observations')
                stream.seek(observations * 24, 1)
                poses.append((rotation, translation))
    else:
        with path.open('r', encoding='utf-8') as stream:
            for line in stream:
                if not line.strip() or line.lstrip().startswith('#'):
                    continue
                fields = line.strip().split(maxsplit=9)
                if len(fields) != 10:
                    raise ValueError('Invalid COLMAP image record')
                rotation = _quaternion_to_rotation([float(value) for value in fields[1:5]])
                translation = np.asarray([float(value) for value in fields[5:8]])
                if stream.readline() == '':
                    raise ValueError('Missing COLMAP image observations')
                poses.append((rotation, translation))
    if any(not np.isfinite(translation).all() for _, translation in poses):
        raise ValueError('Invalid COLMAP camera translation')
    return poses


def _up_alignment_rotation(poses):
    """用相机上方向估计重力方向，并构造到 Z-up 的无缩放刚性旋转。"""
    import numpy as np

    up = np.mean([-rotation.T[:, 1] for rotation, _ in poses], axis=0)
    length = np.linalg.norm(up)
    target = np.asarray([0.0, 0.0, 1.0])
    if not np.isfinite(length) or length < 1e-6:
        return np.eye(3), {'aligned': False, 'method': 'camera_up', 'reason': 'ambiguous_camera_up'}
    up /= length
    cosine = float(np.clip(np.dot(up, target), -1, 1))
    if cosine > 1 - 1e-12:
        rotation = np.eye(3)
    elif cosine < -1 + 1e-12:
        basis = np.eye(3)[int(np.argmin(np.abs(up)))]
        axis = np.cross(up, basis)
        axis /= np.linalg.norm(axis)
        rotation = 2 * np.outer(axis, axis) - np.eye(3)
    else:
        x, y, z = np.cross(up, target)
        skew = np.asarray([[0, -z, y], [z, 0, -x], [-y, x, 0]])
        rotation = np.eye(3) + skew + skew @ skew / (1 + cosine)
    return rotation, {
        'aligned': True, 'method': 'camera_up', 'source_up': up.tolist(),
        'target_up': target.tolist(), 'rotation_matrix': rotation.tolist(),
    }


def _copy_exact(source, destination, length):
    while length:
        size = min(length, 1024 * 1024)
        destination.write(_read_exact(source, size))
        length -= size


def _normalize_binary_model(source_dir, destination_dir, alignment):
    """只改写目标副本的位姿和点坐标，观测、颜色、track 与相机内参原样保留。"""
    import numpy as np

    with (source_dir / 'images.bin').open('rb') as source, (destination_dir / 'images.bin').open('wb') as output:
        count_bytes = _read_exact(source, 8)
        output.write(count_bytes)
        for _ in range(struct.unpack('<Q', count_bytes)[0]):
            fields = struct.unpack('<i7di', _read_exact(source, 64))
            rotated = _quaternion_to_rotation(fields[1:5]) @ alignment.T
            output.write(struct.pack('<i7di', fields[0], *_rotation_to_quaternion(rotated), *fields[5:]))
            while True:
                byte = _read_exact(source, 1)
                output.write(byte)
                if byte == b'\0':
                    break
            observations = _read_exact(source, 8)
            output.write(observations)
            _copy_exact(source, output, struct.unpack('<Q', observations)[0] * 24)
    with (source_dir / 'points3D.bin').open('rb') as source, (destination_dir / 'points3D.bin').open('wb') as output:
        count_bytes = _read_exact(source, 8)
        output.write(count_bytes)
        for _ in range(struct.unpack('<Q', count_bytes)[0]):
            fields = struct.unpack('<Q3d3Bd', _read_exact(source, 43))
            point = alignment @ np.asarray(fields[1:4])
            if not np.isfinite(point).all():
                raise ValueError('Invalid COLMAP sparse point')
            output.write(struct.pack('<Q3d3Bd', fields[0], *point, *fields[4:]))
            tracks = _read_exact(source, 8)
            output.write(tracks)
            _copy_exact(source, output, struct.unpack('<Q', tracks)[0] * 8)
        if source.read(1):
            raise ValueError('Unexpected COLMAP sparse point data')


def _normalize_text_model(source_dir, destination_dir, alignment):
    """兼容官方 Brush 支持的 COLMAP 文本格式，并保留第二行观测。"""
    import numpy as np

    with (source_dir / 'images.txt').open('r', encoding='utf-8') as source, \
            (destination_dir / 'images.txt').open('w', encoding='utf-8', newline='\n') as output:
        for line in source:
            if not line.strip() or line.lstrip().startswith('#'):
                output.write(line)
                continue
            fields = line.strip().split(maxsplit=9)
            rotation = _quaternion_to_rotation([float(value) for value in fields[1:5]])
            quaternion = _rotation_to_quaternion(rotation @ alignment.T)
            fields[1:5] = [format(value, '.17g') for value in quaternion]
            output.write(' '.join(fields) + '\n')
            output.write(source.readline())
    with (source_dir / 'points3D.txt').open('r', encoding='utf-8') as source, \
            (destination_dir / 'points3D.txt').open('w', encoding='utf-8', newline='\n') as output:
        for line in source:
            if not line.strip() or line.lstrip().startswith('#'):
                output.write(line)
                continue
            fields = line.strip().split()
            if len(fields) < 8:
                raise ValueError('Invalid COLMAP sparse point')
            point = alignment @ np.asarray([float(value) for value in fields[1:4]])
            if not np.isfinite(point).all():
                raise ValueError('Invalid COLMAP sparse point')
            fields[1:4] = [format(value, '.17g') for value in point]
            output.write(' '.join(fields) + '\n')


def prepare_brush_dataset(data_dir, dataset_dir, normalize_up=True):
    """将注册最多的 COLMAP 模型及对应原尺寸图片放到独立训练目录。"""
    source = Path(data_dir).resolve()
    destination = Path(dataset_dir).resolve()
    if _within(destination, source) or _within(source, destination):
        raise ValueError('Brush dataset must be separate from the COLMAP input directory')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Brush dataset destination must be empty')
    model = inspect_colmap_models(source)
    if model['registered_images'] < 2 or model['sfm_points'] < 1:
        raise ValueError('At least two registered images and a nonempty COLMAP point cloud are required')
    image_sources = []
    for name in model['image_names']:
        relative = _safe_image_path(name)
        image = next((path for path in (source / 'images' / relative, source / relative)
                      if path.is_file()), None)
        if image is None:
            raise ValueError(f'Registered COLMAP image is missing: {name}')
        if not _within(image, source):
            raise ValueError('COLMAP image escapes the dataset directory')
        image_sources.append((image, relative))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.brush-dataset-', dir=destination.parent) as temporary:
        staging = Path(temporary)
        images = staging / 'images'
        sparse = staging / 'sparse' / '0'
        images.mkdir()
        sparse.mkdir(parents=True)
        for image, relative in image_sources:
            target = images / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(image, target)
            except OSError:
                shutil.copy2(image, target)
        model_source = Path(model['model_dir'])
        for name in ('cameras', 'images', 'points3D'):
            filename = f'{name}.{model["model_format"]}'
            shutil.copy2(model_source / filename, sparse / filename)
        up_alignment = {'aligned': False, 'method': 'none', 'reason': 'disabled'}
        if normalize_up:
            poses = _read_colmap_poses(model_source, model['model_format'])
            alignment, up_alignment = _up_alignment_rotation(poses)
            if up_alignment['aligned']:
                normalize = _normalize_binary_model if model['model_format'] == 'bin' else _normalize_text_model
                normalize(model_source, sparse, alignment)
        # staging 完整后才发布，失败时不留下会被误当作可训练数据的半成品。
        if destination.exists():
            destination.rmdir()
        # Windows 索引或扫描可能暂时占用刚创建的目录；保留完整 staging 后有限重试。
        for attempt in range(5):
            try:
                os.replace(staging, destination)
                break
            except PermissionError as error:
                if getattr(error, 'winerror', None) not in {5, 32, 33} or attempt == 4:
                    raise
                time.sleep(0.1 * (attempt + 1))
    return {
        **model, 'dataset_dir': str(destination), 'model_dir': str(destination / 'sparse' / '0'),
        'image_count': len(image_sources), 'up_alignment': up_alignment,
    }


def estimate_brush_object_focus(dataset_dir, radius_factor=0.55, min_cameras=8):
    """在 Brush 实际输出坐标中估计环绕拍摄物体中心；不确定时不裁剪。"""
    import numpy as np

    try:
        model = inspect_colmap_models(dataset_dir)
        poses = _read_colmap_poses(model['model_dir'], model['model_format'])
        if len(poses) < min_cameras:
            return None
        origins = np.asarray([-rotation.T @ translation for rotation, translation in poses])
        directions = np.asarray([rotation.T[:, 2] for rotation, _ in poses])
        projectors = np.eye(3)[None, :, :] - directions[:, :, None] * directions[:, None, :]
        left = projectors.sum(axis=0)
        right = np.einsum('nij,nj->i', projectors, origins)
        if np.linalg.cond(left) > 1e8:
            return None
        center = np.linalg.solve(left, right)
        median_distance = float(np.median(np.linalg.norm(origins - center, axis=1)))
        if not np.isfinite(center).all() or not math.isfinite(median_distance) or median_distance <= 0:
            return None
        if np.linalg.norm(center - origins.mean(axis=0)) > 2 * median_distance:
            return None
        return center, float(median_distance * radius_factor)
    except (OSError, ValueError, np.linalg.LinAlgError):
        return None


def build_brush_viewer_camera(dataset_dir):
    """从首个注册视角生成取景提示，避免远处低透明度高斯拉偏包围盒。"""
    import numpy as np

    model = inspect_colmap_models(dataset_dir)
    directory = Path(model['model_dir'])
    if model['model_format'] != 'bin':
        return None
    with (directory / 'cameras.bin').open('rb') as stream:
        if struct.unpack('<Q', _read_exact(stream, 8))[0] != 1:
            return None
        _, camera_model, width, height = struct.unpack('<iiQQ', _read_exact(stream, 24))
        if camera_model == 0:
            focal, _, _ = struct.unpack('<3d', _read_exact(stream, 24))
        elif camera_model == 1:
            _, focal, _, _ = struct.unpack('<4d', _read_exact(stream, 32))
        else:
            return None
    if min(width, height, focal) <= 0 or not math.isfinite(focal):
        return None
    poses = _read_colmap_poses(directory, 'bin')
    first = min(range(len(model['image_names'])), key=lambda index: model['image_names'][index])
    rotation, translation = poses[first]
    origin = -rotation.T @ translation
    direction = rotation.T[:, 2]
    depths = []
    with (directory / 'points3D.bin').open('rb') as stream:
        count = struct.unpack('<Q', _read_exact(stream, 8))[0]
        for _ in range(count):
            fields = struct.unpack('<Q3d3BdQ', _read_exact(stream, 51))
            depth = float(np.dot(np.asarray(fields[1:4]) - origin, direction))
            if math.isfinite(depth) and depth > 1e-6:
                depths.append(depth)
            stream.seek(fields[-1] * 8, os.SEEK_CUR)
    if not depths:
        return None
    up = np.asarray([0.0, 0.0, 1.0])
    if abs(float(np.dot(up, direction))) > 0.99:
        up = -rotation.T[:, 1]
    return {'position': origin.tolist(),
            'target': (origin + direction * float(np.median(depths))).tolist(),
            'up': up.tolist(), 'fov_y_degrees': math.degrees(2 * math.atan(height / (2 * focal))),
            'aspect': width / height}


def find_brush_output(output_dir):
    """只接受本次约定的导出文件，避免选中旧 checkpoint 或任意 PLY。"""
    root = Path(output_dir).resolve()
    for name in (BRUSH_EXPORT_NAME, f'{BRUSH_EXPORT_NAME}.ply'):
        candidate = root / name
        if candidate.is_file() and _within(candidate, root):
            return str(candidate)
    return None


def validate_brush_ply(path):
    """校验 Gaussian PLY 结构、完整长度与所有浮点值，保持内存有界。"""
    import numpy as np

    output = Path(path)
    properties = []
    count = None
    current_element = None
    format_seen = False
    with output.open('rb') as stream:
        if stream.readline() != b'ply\n':
            raise ValueError('Brush output is not a PLY file')
        while stream.tell() < 65536:
            raw = stream.readline()
            if not raw:
                raise ValueError('Brush PLY header is truncated')
            fields = raw.decode('ascii').strip().split()
            if not fields:
                continue
            if fields[0] == 'end_header':
                break
            if fields[0] in ('comment', 'obj_info'):
                continue
            if fields[0] == 'format':
                if fields != ['format', 'binary_little_endian', '1.0']:
                    raise ValueError('Brush output must be an uncompressed binary little-endian PLY')
                format_seen = True
            elif fields[0] == 'element':
                if len(fields) != 3:
                    raise ValueError('Invalid Brush PLY element')
                current_element = fields[1]
                element_count = int(fields[2])
                if current_element == 'vertex':
                    if count is not None:
                        raise ValueError('Duplicate Brush PLY vertex element')
                    count = element_count
                elif element_count != 0:
                    raise ValueError('Brush output contains an unsupported PLY element')
            elif fields[0] == 'property' and current_element == 'vertex':
                if len(fields) != 3 or fields[1] not in _PLY_TYPES:
                    raise ValueError('Invalid Brush PLY vertex property')
                if fields[2] in {name for name, _ in properties}:
                    raise ValueError('Duplicate Brush PLY property')
                properties.append((fields[2], _PLY_TYPES[fields[1]]))
        else:
            raise ValueError('Brush PLY header is too large')
        header_size = stream.tell()
    if not format_seen or count is None or count <= 0:
        raise ValueError('Brush output has no Gaussian vertices')
    names = {name for name, _ in properties}
    if not set(_GAUSSIAN_PROPERTIES).issubset(names):
        raise ValueError('Brush output is missing Gaussian properties')
    rest = sorted(int(name[7:]) for name in names if name.startswith('f_rest_'))
    if rest != list(range(len(rest))) or len(rest) % 3:
        raise ValueError('Brush output has invalid spherical harmonics')
    basis_count = len(rest) // 3 + 1
    degree = math.isqrt(basis_count) - 1
    if (degree + 1) ** 2 != basis_count or degree > 3:
        raise ValueError('Brush output has unsupported spherical harmonics')
    dtype = np.dtype(properties)
    if any(dtype.fields[name][0].kind != 'f' for name in _GAUSSIAN_PROPERTIES):
        raise ValueError('Brush Gaussian properties must be floating point')
    expected_size = header_size + count * dtype.itemsize
    if output.stat().st_size != expected_size:
        raise ValueError('Brush PLY payload length does not match its vertex count')
    vertices = np.memmap(output, dtype=dtype, mode='r', offset=header_size, shape=(count,))
    try:
        float_names = [name for name, _ in properties if dtype.fields[name][0].kind == 'f']
        for start in range(0, count, 65536):
            chunk = vertices[start:start + 65536]
            if any(not np.isfinite(chunk[name]).all() for name in float_names):
                raise ValueError('Brush output contains non-finite Gaussian values')
    finally:
        # Windows 上需及时关闭映射，后续流程才能移动或删除原始导出。
        vertices._mmap.close()
    return {'vertex_count': count, 'sh_degree': degree, 'file_size': expected_size}
