#!/usr/bin/env python3
"""Install and validate the PyTorch build used by Sharp GUI.

The ml-sharp requirements pin torch/torchvision versions. On Windows, pip may
install a CPU build first, and older CUDA wheels can appear usable while missing
kernels for new NVIDIA architectures such as sm_120. AMD ROCm wheels also use
the torch.cuda namespace, so this helper runs after the core requirements and
makes the final torch install match the local driver.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
import site
from urllib.parse import unquote
from urllib.parse import urlparse


TORCH_VERSION = "2.8.0"
TORCHVISION_VERSION = "0.23.0"
ROCM_VERSION = "7.2.1"
CUDA_CHOICES = (
    ((12, 8), "cu128"),
    ((12, 6), "cu126"),
)
ROCM_GPU_PATTERNS = (
    "radeon rx 9070",
    "radeon rx 9060",
    "radeon ai pro r9700",
    "radeon pro ai r9700",
    "radeon pro w7900",
    "radeon pro w7800",
    "radeon pro w7700",
    "radeon rx 7900",
    "radeon rx 7800",
    "radeon rx 7700",
)
ROCM_ARCH_PATTERNS = ("gfx1201", "gfx1200", "gfx1101", "gfx1100")
ROCM_PIP_NO_PROXY_HOSTS = ("repo.radeon.com",)
ROCM_COMPAT_MODULE = "sharp_rocm_import_compat"
ROCM_COMPAT_PTH = "sharp_rocm_import_compat.pth"
ROCM_COMPAT_SOURCE = r'''
"""Lazy import compatibility for Windows ROCm PyTorch.

Some Windows ROCm PyTorch builds expose HIP devices through torch.cuda but ship
without torch.distributed support. gsplat imports torch.distributed.nn.functional
at module import time even for single-GPU inference, so provide a narrow stub only
for that module and only when a HIP build reports distributed as unavailable.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys


TARGET = "torch.distributed.nn.functional"


def _unavailable(*args, **kwargs):
    raise RuntimeError("torch.distributed is unavailable in this ROCm PyTorch build")


class _RocmDistributedFunctionalLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return None

    def exec_module(self, module):
        for name in (
            "all_gather",
            "all_reduce",
            "all_to_all",
            "all_to_all_single",
            "broadcast",
            "reduce_scatter",
        ):
            setattr(module, name, _unavailable)


class _RocmDistributedFunctionalFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != TARGET:
            return None

        try:
            import torch
            import torch.distributed as dist
        except Exception:
            return None

        torch_version = getattr(torch, "version", None)
        if not getattr(torch_version, "hip", None):
            return None

        try:
            if dist.is_available():
                return None
        except Exception:
            pass

        return importlib.machinery.ModuleSpec(
            fullname,
            _RocmDistributedFunctionalLoader(),
            origin="sharp-rocm-compat",
        )


if not any(isinstance(finder, _RocmDistributedFunctionalFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _RocmDistributedFunctionalFinder())
'''
ROCM_WINDOWS_META_PACKAGE = (
    f"https://repo.radeon.com/rocm/windows/rocm-rel-{ROCM_VERSION}/rocm-{ROCM_VERSION}.tar.gz"
)
ROCM_WINDOWS_PACKAGES = (
    f"https://repo.radeon.com/rocm/windows/rocm-rel-{ROCM_VERSION}/"
    f"rocm_sdk_core-{ROCM_VERSION}-py3-none-win_amd64.whl",
    f"https://repo.radeon.com/rocm/windows/rocm-rel-{ROCM_VERSION}/"
    f"rocm_sdk_devel-{ROCM_VERSION}-py3-none-win_amd64.whl",
    f"https://repo.radeon.com/rocm/windows/rocm-rel-{ROCM_VERSION}/"
    f"rocm_sdk_libraries_custom-{ROCM_VERSION}-py3-none-win_amd64.whl",
    f"https://repo.radeon.com/rocm/windows/rocm-rel-{ROCM_VERSION}/"
    f"torch-2.9.1%2Brocm{ROCM_VERSION}-cp312-cp312-win_amd64.whl",
    f"https://repo.radeon.com/rocm/windows/rocm-rel-{ROCM_VERSION}/"
    f"torchaudio-2.9.1%2Brocm{ROCM_VERSION}-cp312-cp312-win_amd64.whl",
    f"https://repo.radeon.com/rocm/windows/rocm-rel-{ROCM_VERSION}/"
    f"torchvision-0.24.1%2Brocm{ROCM_VERSION}-cp312-cp312-win_amd64.whl",
)
ROCM_LINUX_PACKAGES = {
    (3, 10): (
        f"https://repo.radeon.com/rocm/manylinux/rocm-rel-{ROCM_VERSION}/"
        f"torch-2.9.1%2Brocm{ROCM_VERSION}.lw.gitff65f5bc-cp310-cp310-linux_x86_64.whl",
        f"https://repo.radeon.com/rocm/manylinux/rocm-rel-{ROCM_VERSION}/"
        f"torchvision-0.24.0%2Brocm{ROCM_VERSION}.gitb919bd0c-cp310-cp310-linux_x86_64.whl",
        f"https://repo.radeon.com/rocm/manylinux/rocm-rel-{ROCM_VERSION}/"
        f"triton-3.5.1%2Brocm{ROCM_VERSION}.gita272dfa8-cp310-cp310-linux_x86_64.whl",
        f"https://repo.radeon.com/rocm/manylinux/rocm-rel-{ROCM_VERSION}/"
        f"torchaudio-2.9.0%2Brocm{ROCM_VERSION}.gite3c6ee2b-cp310-cp310-linux_x86_64.whl",
    ),
    (3, 12): (
        f"https://repo.radeon.com/rocm/manylinux/rocm-rel-{ROCM_VERSION}/"
        f"torch-2.9.1%2Brocm{ROCM_VERSION}.lw.gitff65f5bc-cp312-cp312-linux_x86_64.whl",
        f"https://repo.radeon.com/rocm/manylinux/rocm-rel-{ROCM_VERSION}/"
        f"torchvision-0.24.0%2Brocm{ROCM_VERSION}.gitb919bd0c-cp312-cp312-linux_x86_64.whl",
        f"https://repo.radeon.com/rocm/manylinux/rocm-rel-{ROCM_VERSION}/"
        f"triton-3.5.1%2Brocm{ROCM_VERSION}.gita272dfa8-cp312-cp312-linux_x86_64.whl",
        f"https://repo.radeon.com/rocm/manylinux/rocm-rel-{ROCM_VERSION}/"
        f"torchaudio-2.9.0%2Brocm{ROCM_VERSION}.gite3c6ee2b-cp312-cp312-linux_x86_64.whl",
    ),
}


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    detail: str
    backend: str = "unknown"
    version: str | None = None
    cuda: str | None = None
    hip: str | None = None
    device_name: str | None = None
    capability: tuple[int, int] | None = None
    arch_list: tuple[str, ...] = ()


def run(
    cmd: list[str],
    *,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check, text=True, env=env)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _pip_network_flags() -> list[str]:
    return [
        "--timeout",
        os.environ.get("SHARP_TORCH_PIP_TIMEOUT", "120"),
        "--retries",
        os.environ.get("SHARP_TORCH_PIP_RETRIES", "2"),
    ]


def _merge_no_proxy(existing: str | None, hosts: tuple[str, ...]) -> str:
    entries = [entry.strip() for entry in (existing or "").split(",") if entry.strip()]
    seen = {entry.lower() for entry in entries}
    if "*" in seen:
        return ",".join(entries)
    for host in hosts:
        lowered = host.lower()
        if lowered not in seen:
            entries.append(host)
            seen.add(lowered)
    return ",".join(entries)


def rocm_pip_environment(
    urls: tuple[str, ...], base_env: dict[str, str] | None = None
) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    if _truthy(env.get("SHARP_TORCH_USE_SYSTEM_PROXY")):
        return env

    hosts = tuple(
        dict.fromkeys(
            host
            for host in (
                urlparse(url).hostname for url in urls
            )
            if host in ROCM_PIP_NO_PROXY_HOSTS
        )
    )
    if not hosts:
        return env

    no_proxy = _merge_no_proxy(env.get("NO_PROXY") or env.get("no_proxy"), hosts)
    env["NO_PROXY"] = no_proxy
    env["no_proxy"] = no_proxy
    return env


def _filename_from_url(url: str) -> str:
    return unquote(urlparse(url).path.rsplit("/", 1)[-1])


def rocm_package_specs(
    urls: tuple[str, ...], wheel_dir: str | os.PathLike[str] | None = None
) -> tuple[str, ...]:
    if not wheel_dir:
        return urls

    directory = Path(wheel_dir)
    specs: list[str] = []
    for url in urls:
        local_path = directory / _filename_from_url(url)
        specs.append(str(local_path) if local_path.exists() else url)
    return tuple(specs)


def _site_packages_dir() -> Path:
    candidates = [Path(path) for path in site.getsitepackages()]
    for path in candidates:
        if path.name == "site-packages":
            return path
    if os.name == "nt":
        return Path(sys.prefix) / "Lib" / "site-packages"
    return Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"


def install_rocm_import_compat() -> None:
    site_packages = _site_packages_dir()
    site_packages.mkdir(parents=True, exist_ok=True)
    module_path = site_packages / f"{ROCM_COMPAT_MODULE}.py"
    pth_path = site_packages / ROCM_COMPAT_PTH
    module_path.write_text(ROCM_COMPAT_SOURCE.lstrip(), encoding="utf-8")
    pth_path.write_text(f"import {ROCM_COMPAT_MODULE}\n", encoding="utf-8")
    print(f"[INFO] Installed ROCm import compatibility hook: {module_path}")


def driver_cuda_version() -> tuple[int, int] | None:
    try:
        output = subprocess.check_output(
            ["nvidia-smi"], stderr=subprocess.STDOUT, text=True, timeout=15
        )
    except Exception:
        return None
    match = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", output)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def nvidia_gpu_names() -> list[str]:
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
        )
    except Exception:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def choose_cuda_index(driver_cuda: tuple[int, int] | None) -> str | None:
    if driver_cuda is None:
        return None
    for minimum, tag in CUDA_CHOICES:
        if driver_cuda >= minimum:
            return tag
    return None


def amd_gpu_names() -> list[str]:
    system = platform.system()
    commands: list[list[str]] = []
    if system == "Windows":
        commands.append(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }",
            ]
        )
        commands.append(["wmic", "path", "win32_VideoController", "get", "name"])
    elif system == "Linux":
        commands.extend((["rocminfo"], ["rocm-smi", "--showproductname"], ["lspci"]))

    names: list[str] = []
    for cmd in commands:
        try:
            output = subprocess.check_output(
                cmd, stderr=subprocess.STDOUT, text=True, timeout=20
            )
        except Exception:
            continue
        for line in output.splitlines():
            cleaned = line.strip()
            lowered = cleaned.lower()
            if "amd" in lowered or "radeon" in lowered or "gfx" in lowered:
                names.append(cleaned)

    return list(dict.fromkeys(names))


def is_rocm_supported_gpu(names: list[str]) -> bool:
    haystack = "\n".join(names).lower()
    return any(pattern in haystack for pattern in ROCM_GPU_PATTERNS + ROCM_ARCH_PATTERNS)


def rocm_wheel_urls(
    system: str | None = None,
    python_version: tuple[int, int] | None = None,
) -> tuple[str, ...]:
    system = system or platform.system()
    python_version = python_version or sys.version_info[:2]
    if system == "Windows" and python_version == (3, 12):
        return ROCM_WINDOWS_PACKAGES
    if system == "Linux":
        return ROCM_LINUX_PACKAGES.get(python_version, ())
    return ()


def rocm_meta_package_url(
    system: str | None = None,
    python_version: tuple[int, int] | None = None,
) -> str | None:
    system = system or platform.system()
    python_version = python_version or sys.version_info[:2]
    if system == "Windows" and python_version == (3, 12):
        return ROCM_WINDOWS_META_PACKAGE
    return None


def verify_accelerator_runtime() -> VerifyResult:
    try:
        import torch
    except Exception as exc:
        return VerifyResult(False, f"torch import failed: {exc}")

    version = getattr(torch, "__version__", None)
    torch_version = getattr(torch, "version", None)
    torch_cuda = getattr(torch_version, "cuda", None)
    torch_hip = getattr(torch_version, "hip", None)
    backend = "rocm" if torch_hip else "cuda"

    if not torch.cuda.is_available():
        return VerifyResult(
            False,
            "torch.cuda.is_available() is False",
            backend=backend,
            version=version,
            cuda=torch_cuda,
            hip=torch_hip,
        )

    try:
        device_name = torch.cuda.get_device_name(0)
        capability = torch.cuda.get_device_capability(0)
        arch_list = tuple(torch.cuda.get_arch_list())
        x = torch.ones((16, 16), device="cuda")
        y = (x @ x).sum()
        torch.cuda.synchronize()
        _ = float(y.cpu())
    except Exception as exc:
        first_line = str(exc).splitlines()[0] if str(exc) else repr(exc)
        return VerifyResult(
            False,
            f"{backend.upper()} kernel test failed: {first_line}",
            backend=backend,
            version=version,
            cuda=torch_cuda,
            hip=torch_hip,
        )

    return VerifyResult(
        True,
        f"{backend.upper()} kernel test passed",
        backend=backend,
        version=version,
        cuda=torch_cuda,
        hip=torch_hip,
        device_name=device_name,
        capability=capability,
        arch_list=arch_list,
    )


def verify_torch_import() -> bool:
    try:
        import torch

        print(f"[OK] PyTorch import: {torch.__version__}")
        return True
    except Exception as exc:
        print(f"[ERROR] PyTorch import failed: {exc}")
        return False


def pip_install_torch(index_tag: str | None) -> bool:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        *_pip_network_flags(),
        "--force-reinstall",
        "--no-deps",
        f"torch=={TORCH_VERSION}",
        f"torchvision=={TORCHVISION_VERSION}",
    ]
    if index_tag:
        cmd.extend(["--index-url", f"https://download.pytorch.org/whl/{index_tag}"])
    try:
        run(cmd)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"[WARN] pip install failed with exit code {exc.returncode}")
        return False


def pip_install_rocm(wheel_dir: str | None = None) -> bool:
    urls = rocm_wheel_urls()
    if not urls:
        print(
            "[WARN] ROCm PyTorch wheels are only configured for "
            "Windows Python 3.12 and Linux Python 3.10/3.12."
        )
        return False

    package_specs = rocm_package_specs(urls, wheel_dir)
    meta_url = rocm_meta_package_url()
    meta_spec = rocm_package_specs((meta_url,), wheel_dir)[0] if meta_url else None
    local_specs = [spec for spec in package_specs if not spec.startswith(("http://", "https://"))]
    if local_specs:
        print(f"[INFO] Using local ROCm wheel directory: {wheel_dir}")

    uninstall_cmd = [
        sys.executable,
        "-m",
        "pip",
        "uninstall",
        "-y",
        "torch",
        "torchvision",
        "triton",
        "torchaudio",
        "rocm",
        "rocm-sdk-core",
        "rocm-sdk-devel",
        "rocm-sdk-libraries-custom",
    ]
    run(uninstall_cmd, check=False)

    if meta_spec:
        meta_cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            *_pip_network_flags(),
            "--no-cache-dir",
            "--no-deps",
            meta_spec,
        ]
        try:
            run(meta_cmd, env=rocm_pip_environment((meta_url,)))
        except subprocess.CalledProcessError as exc:
            print(f"[WARN] ROCm meta-package install failed with exit code {exc.returncode}")
            return False

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        *_pip_network_flags(),
        "--no-cache-dir",
        *package_specs,
    ]
    env = rocm_pip_environment(urls)
    if not _truthy(env.get("SHARP_TORCH_USE_SYSTEM_PROXY")):
        print(
            "[INFO] ROCm downloads bypass system proxy for repo.radeon.com. "
            "Set SHARP_TORCH_USE_SYSTEM_PROXY=1 to keep the system proxy."
        )
    try:
        run(cmd, env=env)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"[WARN] ROCm PyTorch install failed with exit code {exc.returncode}")
        return False


def install_cpu_fallback() -> int:
    print("[INFO] Installing CPU PyTorch fallback.")
    if not pip_install_torch(None):
        return 1
    return 0 if verify_torch_import() else 1


def print_verified_runtime(result: VerifyResult) -> None:
    print(
        f"[OK] {result.backend.upper()} PyTorch verified: "
        f"torch={result.version}, cuda={result.cuda}, hip={result.hip}, "
        f"device={result.device_name}, capability={result.capability}, "
        f"archs={','.join(result.arch_list)}"
    )


def default_backend() -> str:
    configured = os.environ.get("SHARP_TORCH_BACKEND", "auto").strip().lower()
    return configured if configured in {"auto", "cuda", "rocm", "cpu"} else "auto"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend",
        choices=("auto", "cuda", "rocm", "cpu"),
        default=default_backend(),
        help="Preferred PyTorch backend. ROCm uses torch.cuda/HIP on AMD GPUs.",
    )
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--cpu-only", action="store_true")
    parser.add_argument(
        "--rocm-wheel-dir",
        default=os.environ.get("SHARP_TORCH_ROCM_WHEEL_DIR"),
        help="Optional directory containing pre-downloaded ROCm wheels.",
    )
    args = parser.parse_args()

    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    if args.cpu_only or args.backend == "cpu":
        return install_cpu_fallback()

    current = verify_accelerator_runtime()
    if current.ok and args.backend in {"auto", current.backend}:
        if current.backend == "rocm" and not args.check_only:
            install_rocm_import_compat()
        print_verified_runtime(current)
        return 0

    print(f"[INFO] Current PyTorch accelerator check: {current.detail}")
    if current.version:
        print(
            f"[INFO] Current torch={current.version}, cuda={current.cuda}, hip={current.hip}"
        )

    if args.check_only:
        return 1

    amd_names = amd_gpu_names()
    wants_rocm = args.backend == "rocm" or (
        args.backend == "auto" and is_rocm_supported_gpu(amd_names)
    )
    if wants_rocm:
        if amd_names:
            print("[INFO] AMD ROCm candidate GPU detected: " + "; ".join(amd_names))
        else:
            print("[INFO] ROCm backend requested explicitly.")
        print(f"[INFO] Installing PyTorch ROCm {ROCM_VERSION} for AMD/RDNA GPUs.")
        if pip_install_rocm(args.rocm_wheel_dir):
            updated = verify_accelerator_runtime()
            if updated.ok and updated.backend == "rocm":
                install_rocm_import_compat()
                print_verified_runtime(updated)
                return 0
            print(f"[WARN] ROCm PyTorch installed but failed verification: {updated.detail}")
        print("[WARN] Falling back to CPU PyTorch so inference remains functional.")
        return install_cpu_fallback()

    gpu_names = nvidia_gpu_names()
    if not gpu_names:
        if amd_names:
            print(
                "[INFO] AMD GPU detected but it is not in the ROCm auto-install list: "
                + "; ".join(amd_names)
            )
            print("[INFO] Set SHARP_TORCH_BACKEND=rocm to force a ROCm install attempt.")
        else:
            print("[INFO] No NVIDIA or supported AMD ROCm GPU detected.")
        print("[INFO] Keeping/installing CPU PyTorch.")
        return install_cpu_fallback()

    print("[INFO] NVIDIA GPU detected: " + "; ".join(gpu_names))
    driver_cuda = driver_cuda_version()
    print(f"[INFO] NVIDIA driver reports CUDA {driver_cuda or 'unknown'}")
    index_tag = choose_cuda_index(driver_cuda)

    if index_tag is None:
        print(
            "[WARN] Driver CUDA is below 12.6 or could not be detected. "
            "Falling back to CPU PyTorch for a reliable install."
        )
        return install_cpu_fallback()

    print(
        f"[INFO] Installing torch {TORCH_VERSION} / "
        f"torchvision {TORCHVISION_VERSION} from {index_tag}."
    )
    if not pip_install_torch(index_tag):
        print("[WARN] CUDA PyTorch install failed; falling back to CPU.")
        return install_cpu_fallback()

    updated = verify_accelerator_runtime()
    if updated.ok:
        print_verified_runtime(updated)
        return 0

    print(f"[WARN] CUDA PyTorch installed but failed verification: {updated.detail}")
    print("[WARN] Falling back to CPU PyTorch so inference remains functional.")
    return install_cpu_fallback()


if __name__ == "__main__":
    raise SystemExit(main())
