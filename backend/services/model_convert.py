import gzip
import math
import os
import struct
import tempfile
from io import BytesIO

import numpy as np
from plyfile import PlyData

SPZ_MAGIC = 1347635022
SPZ_VERSION = 3
SQRT1_2 = 1.0 / math.sqrt(2.0)
QUAT_VALUEMASK = (1 << 9) - 1
SPZ_CHUNK_POINTS = 65_536
SH_COEFFICIENT_COUNTS = (0, 9, 24, 45)


def ply_to_splat(ply_path):
    """将 PLY 文件转换为更紧凑的 .splat 格式。"""
    plydata = PlyData.read(ply_path)
    vert = plydata["vertex"]

    sorted_indices = np.argsort(
        -np.exp(vert["scale_0"] + vert["scale_1"] + vert["scale_2"])
        / (1 + np.exp(-vert["opacity"]))
    )

    buffer = BytesIO()
    sh_c0 = 0.28209479177387814

    for idx in sorted_indices:
        v = vert[idx]

        position = np.array([v["x"], v["y"], v["z"]], dtype=np.float32)
        buffer.write(position.tobytes())

        scales = np.exp(np.array([v["scale_0"], v["scale_1"], v["scale_2"]], dtype=np.float32))
        buffer.write(scales.tobytes())

        color = np.array([
            0.5 + sh_c0 * v["f_dc_0"],
            0.5 + sh_c0 * v["f_dc_1"],
            0.5 + sh_c0 * v["f_dc_2"],
            1 / (1 + np.exp(-v["opacity"])),
        ])
        buffer.write((color * 255).clip(0, 255).astype(np.uint8).tobytes())

        rot = np.array([v["rot_0"], v["rot_1"], v["rot_2"], v["rot_3"]], dtype=np.float32)
        rot_normalized = (rot / np.linalg.norm(rot)) * 128 + 128
        buffer.write(rot_normalized.clip(0, 255).astype(np.uint8).tobytes())

    return buffer.getvalue()


def _ply_sh_degree(vertices):
    """只接受完整的 SH0–SH3 字段，避免静默丢弃或错排高阶系数。"""
    names = [name for name in vertices.dtype.names if name.startswith('f_rest_')]
    count = len(names)
    expected = {f'f_rest_{index}' for index in range(count)}
    if count not in SH_COEFFICIENT_COUNTS or set(names) != expected:
        raise ValueError('PLY spherical harmonics must contain complete f_rest_0..N fields for SH0–SH3')
    return SH_COEFFICIENT_COUNTS.index(count)


def _spz_columns(vertices, names, dtype=np.float64):
    values = np.column_stack([vertices[name] for name in names]).astype(dtype, copy=False)
    if not np.isfinite(values).all():
        raise ValueError('PLY gaussian attributes must contain finite values')
    return values


def _spz_rotations(vertices):
    """按 Niantic v3 的 smallest-three 布局批量打包四元数。"""
    quats = _spz_columns(vertices, ('rot_1', 'rot_2', 'rot_3', 'rot_0'))
    norms = np.linalg.norm(quats, axis=1, keepdims=True)
    norms[norms < 1e-10] = 1.0
    quats /= norms
    largest = np.argmax(np.abs(quats), axis=1)
    negative = quats[np.arange(len(quats)), largest] < 0
    packed = largest.astype(np.uint32)
    for component in range(4):
        selected = largest != component
        values = quats[selected, component]
        sign = ((values < 0) ^ negative[selected]).astype(np.uint32)
        magnitude = np.minimum(
            np.floor(QUAT_VALUEMASK * (np.abs(values) / SQRT1_2) + 0.5),
            QUAT_VALUEMASK,
        ).astype(np.uint32)
        packed[selected] = (packed[selected] << 10) | (sign << 9) | magnitude
    return packed.astype('<u4').tobytes()


def _spz_spherical_harmonics(vertices, sh_degree):
    """将 PLY 的通道优先顺序转换为 SPZ 的系数优先 RGB 顺序并量化。"""
    count = SH_COEFFICIENT_COUNTS[sh_degree]
    coefficients = _spz_columns(
        vertices, [f'f_rest_{index}' for index in range(count)], dtype=np.float32,
    ).reshape(len(vertices), 3, count // 3).transpose(0, 2, 1)
    # 官方 quantizeSH：先舍入至 8 位，再归入 SH1 的 8 或 SH2+ 的 16 大小的桶。
    # https://github.com/nianticlabs/spz/blob/main/src/cc/load-spz.cc
    scaled = np.clip(coefficients, -1.0, 1.0) * np.float32(128.0)
    quantized = np.copysign(np.floor(np.abs(scaled) + 0.5), scaled) + 128.0
    bucket_sizes = np.full((count // 3, 1), 16, dtype=np.int32)
    bucket_sizes[:3] = 8
    quantized = np.trunc((quantized + bucket_sizes // 2) / bucket_sizes) * bucket_sizes
    return np.clip(quantized, 0, 255).astype(np.uint8).tobytes()


def _spz_attribute_chunks(vertices, sh_degree, fractional_bits):
    """逐属性分块输出，保持 SPZ 布局且限制百万级模型的临时内存。"""
    attributes = ('positions', 'alphas', 'colors', 'scales', 'rotations')
    if sh_degree:
        attributes += ('sh',)
    for attribute in attributes:
        for start in range(0, len(vertices), SPZ_CHUNK_POINTS):
            chunk = vertices[start:start + SPZ_CHUNK_POINTS]
            if attribute == 'positions':
                xyz = _spz_columns(chunk, ('x', 'y', 'z'))
                quantized = np.clip(
                    np.round(xyz * (1 << fractional_bits)), -(1 << 23) + 1, (1 << 23) - 1,
                ).astype(np.int32)
                unsigned = quantized.astype(np.uint32) & 0xFFFFFF
                encoded = np.stack([
                    unsigned & 0xFF, (unsigned >> 8) & 0xFF, (unsigned >> 16) & 0xFF,
                ], axis=-1).astype(np.uint8)
            elif attribute == 'alphas':
                logits = _spz_columns(chunk, ('opacity',))
                alphas = 1.0 / (1.0 + np.exp(-np.clip(logits, -20, 20)))
                encoded = np.round(alphas * 255).clip(0, 255).astype(np.uint8)
            elif attribute == 'colors':
                dc = _spz_columns(chunk, ('f_dc_0', 'f_dc_1', 'f_dc_2'))
                sh_c0 = 0.28209479177387814
                colors = 0.5 + sh_c0 * dc
                encoded = np.round(
                    ((colors - 0.5) / (sh_c0 / 0.15) + 0.5) * 255,
                ).clip(0, 255).astype(np.uint8)
            elif attribute == 'scales':
                log_scales = _spz_columns(chunk, ('scale_0', 'scale_1', 'scale_2'))
                encoded = np.round((log_scales + 10.0) * 16.0).clip(0, 255).astype(np.uint8)
            elif attribute == 'rotations':
                yield _spz_rotations(chunk)
                continue
            else:
                yield _spz_spherical_harmonics(chunk, sh_degree)
                continue
            yield encoded.tobytes()


def ply_to_spz(ply_path, spz_path=None, fractional_bits=11):
    """将 PLY 高斯泼溅模型转换为保留 SH0–SH3 的 SPZ 格式（Niantic v3）。"""
    plydata = PlyData.read(ply_path)
    vertices = plydata['vertex'].data
    sh_degree = _ply_sh_degree(vertices)
    if not isinstance(fractional_bits, int) or not 0 <= fractional_bits <= 24:
        raise ValueError('SPZ fractional_bits must be an integer between 0 and 24')
    if spz_path is None:
        spz_path = os.path.splitext(ply_path)[0] + '.spz'
    header = struct.pack(
        '<IIIBBBB', SPZ_MAGIC, SPZ_VERSION, len(vertices), sh_degree, fractional_bits, 0, 0,
    )
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='wb', prefix='.spz-', suffix='.tmp',
            dir=os.path.dirname(os.path.abspath(spz_path)), delete=False,
        ) as temporary:
            temporary_path = temporary.name
            with gzip.GzipFile(filename='', fileobj=temporary, mode='wb', compresslevel=6, mtime=0) as compressed:
                compressed.write(header)
                for payload in _spz_attribute_chunks(vertices, sh_degree, fractional_bits):
                    compressed.write(payload)
        os.replace(temporary_path, spz_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            os.unlink(temporary_path)
    return spz_path
