"""高斯模型编辑：校验源文件、过滤点并保存副本或覆盖模型，保留 SH0～SH3。"""

import base64
import binascii
import copy
import gzip
import math
import os
import shutil
import struct
import tempfile
import threading
import uuid
from urllib.parse import quote

import numpy as np
from plyfile import PlyData, PlyElement

from backend.services import model_assets, model_convert, model_gallery
from backend.services.model_orientation import normalize_viewer_camera

MAX_POINTS = 8_000_000
MAX_SOURCE_BYTES = 2_000_000_000
MAX_REQUEST_BYTES = 2_000_000
SAVE_LOCK = threading.Lock()


class ModelEditorError(model_assets.ModelAssetServiceError):
    pass


def fail(code='model_editor_invalid', status=400):
    raise ModelEditorError('Model editing could not be completed', code, status)


def source_fingerprint(path):
    """使用文件状态生成不暴露服务器路径的修订标识。"""
    return model_assets.model_source_fingerprint(path)


def resolve_source(paths, asset_id):
    asset = model_assets.get_model_asset(paths, asset_id)
    if not asset or not asset.get('available'):
        fail('model_asset_not_found', 404)
    formats = asset.get('formats', [])
    fmt = next((item for item in ('ply', 'spz', 'splat') if item in formats), None)
    if not fmt:
        fail('model_editor_unsupported', 415)
    resolved = model_assets.resolve_download_file(paths, asset_id, fmt)
    if not resolved or os.path.splitext(resolved[0])[1].lower() != '.' + fmt:
        fail('model_editor_source_changed', 409)
    path = resolved[0]
    if os.path.getsize(path) > MAX_SOURCE_BYTES:
        fail('model_editor_too_large', 413)
    return asset, path, fmt


def gaussian_dtype(degree):
    names = ['x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2']
    names += [f'f_rest_{index}' for index in range(3 * ((degree + 1) ** 2 - 1))]
    names += ['opacity', 'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3']
    return np.dtype([(name, '<f4') for name in names])


def inspect_spz(path):
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(16)
    if len(raw) != 16:
        fail('model_editor_unsupported', 415)
    magic, version, count, degree, bits, flags, reserved = struct.unpack('<IIIBBBB', raw)
    if magic != model_convert.SPZ_MAGIC or version not in (2, 3) or degree > 3 or bits > 24 or reserved or flags & ~1:
        fail('model_editor_unsupported', 415)
    return raw, version, count, degree, bits, flags


def inspect_source(path, fmt):
    if fmt == 'ply':
        data = PlyData.read(path, mmap='r')
        if len(data.elements) != 1 or data.elements[0].name != 'vertex':
            fail('model_editor_unsupported', 415)
        vertices = data['vertex'].data
        names = vertices.dtype.names or ()
        required = set(gaussian_dtype(0).names)
        if not required.issubset(names) or any(vertices.dtype[name].kind not in 'fiu' for name in names):
            fail('model_editor_unsupported', 415)
        if any(vertices.dtype[name].kind != 'f' for name in required):
            fail('model_editor_unsupported', 415)
        rest = [name for name in names if name.startswith('f_rest_')]
        if len(rest) not in (0, 9, 24, 45) or any(f'f_rest_{i}' not in names for i in range(len(rest))):
            fail('model_editor_unsupported', 415)
        if any(vertices.dtype[name].kind != 'f' for name in rest):
            fail('model_editor_unsupported', 415)
        count = len(vertices)
    elif fmt == 'spz':
        count = inspect_spz(path)[2]
    else:
        size = os.path.getsize(path)
        if size % 32:
            fail('model_editor_unsupported', 415)
        count = size // 32
    if count < 1 or count > MAX_POINTS:
        fail('model_editor_too_large', 413)
    return count


def get_editor_descriptor(paths, asset_id):
    """返回完整分辨率编辑源，不复用 LoD 的点编号。"""
    asset, path, fmt = resolve_source(paths, asset_id)
    try:
        count = inspect_source(path, fmt)
    except ModelEditorError:
        raise
    except (OSError, ValueError, EOFError):
        fail('model_editor_unsupported', 415)
    return {'asset_id': asset['id'], 'name': asset['name'], 'format': fmt,
            'point_count': count, 'fingerprint': source_fingerprint(path),
            'source_url': f'/api/model-assets/{quote(asset["id"], safe="")}/editor/source'}


def decode_vertices(path, fmt):
    if fmt == 'ply':
        return PlyData.read(path, mmap='r')['vertex'].data
    if fmt == 'splat':
        rows = np.fromfile(path, dtype=np.uint8).reshape(-1, 32)
        vertices = np.zeros(len(rows), dtype=gaussian_dtype(0))
        xyz_scale = np.ascontiguousarray(rows[:, :24]).view('<f4').reshape(-1, 6)
        for axis, name in enumerate(('x', 'y', 'z')):
            vertices[name] = xyz_scale[:, axis]
            vertices[f'scale_{axis}'] = np.log(np.maximum(xyz_scale[:, axis + 3], 1e-30))
            vertices[f'f_dc_{axis}'] = (rows[:, 24 + axis] / 255 - 0.5) / 0.28209479177387814
        alpha = np.clip(rows[:, 27] / 255, 1e-8, 1 - 1e-8)
        vertices['opacity'] = np.log(alpha / (1 - alpha))
        for index in range(4):
            vertices[f'rot_{index}'] = (rows[:, 28 + index].astype(float) - 128) / 128
        return vertices
    header, version, count, degree, bits, _ = inspect_spz(path)
    rest = 3 * ((degree + 1) ** 2 - 1)
    expected = 16 + count * (9 + 1 + 3 + 3 + (4 if version == 3 else 3) + rest)
    with gzip.open(path, 'rb') as stream:
        payload = stream.read(expected + 1)
    if len(payload) != expected or payload[:16] != header:
        fail('model_editor_unsupported', 415)
    vertices = np.zeros(count, dtype=gaussian_dtype(degree))
    offset = 16
    def take(stride):
        nonlocal offset
        result = np.frombuffer(payload, dtype=np.uint8, count=count * stride, offset=offset).reshape(count, stride)
        offset += count * stride
        return result
    positions = take(9).reshape(count, 3, 3).astype(np.int32)
    positions = positions[:, :, 0] | positions[:, :, 1] << 8 | positions[:, :, 2] << 16
    positions = (positions ^ 0x800000) - 0x800000
    for axis, name in enumerate(('x', 'y', 'z')):
        vertices[name] = positions[:, axis] / (1 << bits)
    alpha = np.clip(take(1)[:, 0] / 255, 1e-8, 1 - 1e-8)
    vertices['opacity'] = np.log(alpha / (1 - alpha))
    colors, scales = take(3), take(3)
    for index in range(3):
        vertices[f'f_dc_{index}'] = (colors[:, index] / 255 - 0.5) / 0.15
        vertices[f'scale_{index}'] = scales[:, index] / 16 - 10
    quats = np.zeros((count, 4), dtype=np.float64)  # SPZ uses xyzw.
    if version == 2:
        quats[:, :3] = take(3) / 127.5 - 1
        quats[:, 3] = np.sqrt(np.maximum(0, 1 - (quats[:, :3] ** 2).sum(axis=1)))
    else:
        packed = np.ascontiguousarray(take(4)).view('<u4').ravel().copy()
        largest = packed >> 30
        for component in range(3, -1, -1):
            selected = largest != component
            word = packed[selected] & 1023
            quats[selected, component] = (word & 511) / 511 * math.sqrt(0.5) * np.where(word & 512, -1, 1)
            packed[selected] >>= 10
        quats[np.arange(count), largest] = np.sqrt(np.maximum(0, 1 - (quats ** 2).sum(axis=1)))
    for index, component in enumerate((3, 0, 1, 2)):
        vertices[f'rot_{index}'] = quats[:, component]
    if rest:
        harmonics = (take(rest).astype(float) - 128) / 128
        harmonics = harmonics.reshape(count, rest // 3, 3).transpose(0, 2, 1).reshape(count, rest)
        for index in range(rest):
            vertices[f'f_rest_{index}'] = harmonics[:, index]
    return vertices


def validate_matrix(raw):
    if not isinstance(raw, list) or len(raw) != 16 or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in raw):
        fail()
    matrix = np.asarray(raw, dtype=float).reshape(4, 4, order='F')
    if not np.isfinite(matrix).all() or np.max(np.abs(matrix)) > 1e6 or not np.allclose(matrix[3], [0, 0, 0, 1]):
        fail()
    scale = float(np.linalg.norm(matrix[:3, 0]))
    if not 1e-5 <= scale <= 1e4:
        fail()
    rotation = matrix[:3, :3] / scale
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5) or not np.isclose(np.linalg.det(rotation), 1, atol=1e-5):
        fail()
    return matrix, rotation, scale


def sh_basis(directions, degree):
    """标准 3DGS 实球谐基；用于旋转方向颜色而非重新训练。"""
    x, y, z = np.asarray(directions).T
    values = []
    if degree >= 1:
        values += [-0.4886025119029199 * y, 0.4886025119029199 * z, -0.4886025119029199 * x]
    if degree >= 2:
        values += [1.0925484305920792*x*y, -1.0925484305920792*y*z,
                   0.31539156525252005*(2*z*z-x*x-y*y), -1.0925484305920792*x*z,
                   0.5462742152960396*(x*x-y*y)]
    if degree >= 3:
        values += [-0.5900435899266435*y*(3*x*x-y*y), 2.890611442640554*x*y*z,
                   -0.4570457994644658*y*(4*z*z-x*x-y*y), 0.3731763325901154*z*(2*z*z-3*x*x-3*y*y),
                   -0.4570457994644658*x*(4*z*z-x*x-y*y), 1.445305721320277*z*(x*x-y*y),
                   -0.5900435899266435*x*(x*x-3*y*y)]
    return np.column_stack(values)


def sh_rotation(rotation, degree):
    # 每个带宽内的旋转是精确线性映射；过定约束的单位球采样只用于求这组系数。
    indices = np.arange(128, dtype=float) + 0.5
    z = 1 - 2 * indices / len(indices)
    angle = indices * (math.pi * (3 - math.sqrt(5)))
    radius = np.sqrt(1 - z*z)
    directions = np.column_stack([radius*np.cos(angle), radius*np.sin(angle), z])
    return np.linalg.lstsq(sh_basis(directions, degree), sh_basis(directions @ rotation, degree), rcond=None)[0]


def rotation_quaternion(rotation):
    # 对称特征值法支持 180 度旋转，返回 wxyz。
    r = rotation
    k = np.array([[r[0,0]-r[1,1]-r[2,2], r[1,0]+r[0,1], r[2,0]+r[0,2], r[2,1]-r[1,2]],
                  [r[1,0]+r[0,1], r[1,1]-r[0,0]-r[2,2], r[2,1]+r[1,2], r[0,2]-r[2,0]],
                  [r[2,0]+r[0,2], r[2,1]+r[1,2], r[2,2]-r[0,0]-r[1,1], r[1,0]-r[0,1]],
                  [r[2,1]-r[1,2], r[0,2]-r[2,0], r[1,0]-r[0,1], np.trace(r)]]) / 3
    _, vectors = np.linalg.eigh(k)
    return vectors[:, -1][[3, 0, 1, 2]]


def transform_chunk(chunk, matrix, rotation, scale, harmonics_rotation):
    xyz = np.column_stack([chunk[name] for name in ('x', 'y', 'z')])
    xyz = xyz @ matrix[:3, :3].T + matrix[:3, 3]
    for index, name in enumerate(('x', 'y', 'z')):
        chunk[name] = xyz[:, index]
        chunk[f'scale_{index}'] += math.log(scale)
    q = np.column_stack([chunk[f'rot_{i}'] for i in range(4)])
    norms = np.linalg.norm(q, axis=1, keepdims=True)
    if np.any(norms < 1e-10):
        fail('model_editor_invalid_source', 415)
    q = q / norms
    a = rotation_quaternion(rotation)
    w = a[0]*q[:, 0] - q[:, 1:] @ a[1:]
    xyz_q = a[0]*q[:, 1:] + q[:, :1]*a[1:] + np.cross(a[1:], q[:, 1:])
    for index, values in enumerate([w, *xyz_q.T]):
        chunk[f'rot_{index}'] = values
    if harmonics_rotation is not None:
        count = harmonics_rotation.shape[0]
        for channel in range(3):
            names = [f'f_rest_{channel*count+i}' for i in range(count)]
            coefficients = np.column_stack([chunk[name] for name in names]) @ harmonics_rotation.T
            for index, name in enumerate(names):
                chunk[name] = coefficients[:, index]
    if {'nx', 'ny', 'nz'}.issubset(chunk.dtype.names):
        normals = np.column_stack([chunk[name] for name in ('nx', 'ny', 'nz')]) @ rotation.T
        for index, name in enumerate(('nx', 'ny', 'nz')):
            chunk[name] = normals[:, index]
    for name in chunk.dtype.names:
        if not np.isfinite(chunk[name]).all():
            fail('model_editor_invalid_source', 415)
    return chunk


def decode_mask(encoded, count):
    if not isinstance(encoded, str) or len(encoded) > ((count + 7) // 8 + 2) * 4 // 3 + 4:
        fail()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        fail()
    if len(raw) != (count + 7) // 8 or (count % 8 and raw[-1] & ~((1 << (count % 8)) - 1)):
        fail()
    return np.unpackbits(np.frombuffer(raw, dtype=np.uint8), bitorder='little')[:count].astype(bool)


def release_vertices(vertices):
    """覆盖前释放 PLY 映射，避免 Windows 锁住正在读取的源文件。"""
    while vertices is not None:
        if isinstance(vertices, np.memmap):
            vertices._mmap.close()
            return
        vertices = getattr(vertices, 'base', None)


def save_edited_model(paths, asset_id, payload):
    """默认创建副本；显式 overwrite 时沿用原资产编号和来源。"""
    if not isinstance(payload, dict):
        fail()
    save_mode = payload.get('save_mode', 'copy')
    if save_mode not in ('copy', 'overwrite'):
        fail()
    overwrite = save_mode == 'overwrite'
    raw_name = payload.get('name')
    if raw_name is not None and (not isinstance(raw_name, str) or len(raw_name) > 160):
        fail()
    matrix, rotation, scale = validate_matrix(payload.get('matrix'))
    camera = normalize_viewer_camera(payload.get('camera'))
    if camera is None:
        fail()
    if not SAVE_LOCK.acquire(blocking=False):
        fail('model_editor_busy', 409)
    temporary = None
    staging = None
    vertices = None
    published = []
    try:
        asset, source, fmt = resolve_source(paths, asset_id)
        fingerprint = source_fingerprint(source)
        if payload.get('fingerprint') != fingerprint:
            fail('model_editor_source_changed', 409)
        count = inspect_source(source, fmt)
        if isinstance(payload.get('point_count'), bool) or payload.get('point_count') != count:
            fail('model_editor_source_changed', 409)
        deleted = decode_mask(payload.get('deleted_mask'), count)
        retained = int(count - np.count_nonzero(deleted))
        if retained == 0:
            fail('model_editor_empty')
        vertices = decode_vertices(source, fmt)
        rest = sum(name.startswith('f_rest_') for name in vertices.dtype.names)
        degree = {0: 0, 9: 1, 24: 2, 45: 3}[rest]
        harmonic_matrix = sh_rotation(rotation, degree) if degree else None
        root = paths.model_asset_import_folder if overwrite and asset.get('is_imported') else paths.output_folder
        model_assets.require_controlled_root(paths, root, 'model_asset_path_invalid')
        os.makedirs(root, exist_ok=True)
        if overwrite:
            staging = tempfile.TemporaryDirectory(dir=root, prefix='.model-edit-')
        destination = staging.name if staging else root
        model_id = 'edited' if overwrite else 'edit-' + uuid.uuid4().hex
        ply_path = os.path.join(destination, model_id + '.ply')
        spz_path = os.path.join(destination, model_id + '.spz')
        max_coordinate = 0.0
        with tempfile.NamedTemporaryFile(dir=destination, prefix='.model-edit-', suffix='.tmp', delete=False) as file:
            temporary = file.name
            header = str(PlyData([PlyElement.describe(np.empty(0, dtype=vertices.dtype), 'vertex')], text=False, byte_order='<').header)
            header = header.replace('element vertex 0', f'element vertex {retained}')
            file.write((header + '\n').encode('ascii'))
            for start in range(0, count, 16384):
                chunk = vertices[start:start+16384][~deleted[start:start+16384]].copy()
                if len(chunk):
                    transformed = transform_chunk(chunk, matrix, rotation, scale, harmonic_matrix)
                    max_coordinate = max(max_coordinate, *(float(np.max(np.abs(transformed[name]))) for name in ('x', 'y', 'z')))
                    file.write(transformed.astype(vertices.dtype.newbyteorder('<'), copy=False).tobytes())
        if max_coordinate >= (1 << 23) - 1:
            fail('model_editor_coordinate_range')
        if source_fingerprint(source) != fingerprint:
            fail('model_editor_source_changed', 409)
        os.replace(temporary, ply_path)
        temporary = None
        published.append(ply_path)
        model_convert.ply_to_spz(ply_path, spz_path)
        published.append(spz_path)
        name = (raw_name or '').strip() or (str(asset['name']) if overwrite else str(asset['name'])[:140] + ' · Edited')
        if asset.get('is_generated') and not overwrite:
            original_name, original_path = model_gallery.find_original_image(paths, asset['id'])
            if original_path:
                if not model_assets.is_controlled_path(paths, original_path, paths.input_folder):
                    fail('model_asset_path_invalid', 403)
                model_assets.require_controlled_root(paths, paths.input_folder, 'model_asset_path_invalid')
                image_path = os.path.join(paths.input_folder, model_id + os.path.splitext(original_name)[1])
                published.append(image_path)
                shutil.copyfile(original_path, image_path)
        source_metadata = (model_gallery.read_model_metadata(paths, asset['id']) if asset.get('is_generated')
                           else asset.get('metadata', {}))
        # 来源及重建报告是谱系资料；点数、坐标、相机等结果属性必须由本次编辑重新生成。
        metadata = {key: copy.deepcopy(source_metadata[key]) for key in (
            'source_media_type', 'source_media_id', 'source_name', 'source_video_path', 'source_mime_type',
            'mode', 'quality', 'custom_options', 'engine', 'resolved_engine', 'reconstruction',
        ) if key in source_metadata}
        metadata.update({'generator': 'model_editor', 'display_name': name,
                    'viewer_orientation': 'default', 'viewer_transform': None,
                    'viewer_camera': camera, 'point_count': retained,
                    'editing': {'source_asset_id': asset['id'], 'source_count': count,
                                'deleted_count': count-retained, 'matrix': payload['matrix'], 'sh_degree': degree,
                                'source_generator': source_metadata.get('generator'),
                                'previous_editing': source_metadata.get('editing')}})
        if overwrite:
            staged_files = {'ply': ply_path, 'spz': spz_path}
            if asset.get('is_imported'):
                metadata = {**{key: value for key, value in source_metadata.items() if key not in (
                    'bounding_box', 'gaussian_points', 'coordinate_system', 'attributes', 'compression', 'version',
                )}, **metadata}
                if fmt == 'splat':
                    splat_path = os.path.join(destination, model_id + '.splat')
                    with open(splat_path, 'wb') as file:
                        file.write(model_convert.ply_to_splat(ply_path))
                    staged_files['splat'] = splat_path
            release_vertices(vertices)
            vertices = None
            return model_assets.replace_edited_model_asset(paths, asset['id'], staged_files, metadata, source, fingerprint)
        meta_path = model_gallery.write_model_metadata(paths, model_id, metadata)
        published.append(meta_path)
        result = model_assets.sync_generated_model_asset(paths, model_id)
        if asset.get('tags') or asset.get('note'):
            result = model_assets.update_model_asset_profile(paths, model_id, {
                'display_name': name, 'tags': asset.get('tags', []), 'note': asset.get('note', ''),
            })
        return result
    except ModelEditorError:
        for path in published:
            if os.path.isfile(path):
                os.remove(path)
        raise
    except Exception:
        for path in published:
            if os.path.isfile(path):
                os.remove(path)
        raise
    finally:
        try:
            release_vertices(vertices)
            if temporary and os.path.isfile(temporary):
                os.remove(temporary)
            if staging:
                staging.cleanup()
        finally:
            SAVE_LOCK.release()


def save_edited_copy(paths, asset_id, payload):
    """兼容既有服务调用；未指定保存方式的请求仍创建独立副本。"""
    return save_edited_model(paths, asset_id, payload)
