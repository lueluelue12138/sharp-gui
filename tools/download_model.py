"""Download Sharp model to torch hub cache.

Handles:
- Multiple download sources (HuggingFace → HF Mirror → Apple CDN)
- SSL certificate errors (common on Windows)
- SHA256 integrity verification
- Progress display
- Partial download recovery
"""
import hashlib
import os
import sys
import urllib.request
import ssl

MODEL_FILENAME = "sharp_2572gikvuh.pt"
MODEL_SHA256 = "94211a75198c47f61fca7d739ba08a215418d8d398d48fddf023baccc24f073d"
SOURCES = [
    ("HuggingFace", f"https://huggingface.co/apple/Sharp/resolve/main/{MODEL_FILENAME}"),
    ("HF镜像(国内)", f"https://hf-mirror.com/apple/Sharp/resolve/main/{MODEL_FILENAME}"),
    ("Apple CDN", f"https://ml-site.cdn-apple.com/models/sharp/{MODEL_FILENAME}"),
]


def ordered_sources():
    """Return model sources, optionally preferring mainland-friendly mirrors."""
    preferred = os.environ.get("SHARP_MODEL_SOURCE", "").strip().lower()
    use_china = os.environ.get("SHARP_USE_CHINA_MIRROR", "").strip() == "1"
    if preferred not in {"china", "mirror", "hf-mirror"} and not use_china:
        return SOURCES

    def source_rank(source):
        url = source[1]
        if "hf-mirror.com" in url:
            return 0
        if "ml-site.cdn-apple.com" in url:
            return 1
        return 2

    return sorted(SOURCES, key=source_rank)


def get_model_path():
    cache_dir = os.path.join(
        os.path.expanduser("~"), ".cache", "torch", "hub", "checkpoints"
    )
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, MODEL_FILENAME)


def sha256_file(filepath):
    """Calculate SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download_with_progress(url, dest, ssl_context=None):
    """Download a file with progress bar."""

    def reporthook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100, downloaded * 100 // total_size)
            mb_done = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            bar_len = 30
            filled = int(bar_len * pct / 100)
            bar = "#" * filled + "-" * (bar_len - filled)
            sys.stdout.write(
                f"\r  {bar} {mb_done:.1f}/{mb_total:.1f} MB ({pct}%)"
            )
        else:
            mb_done = downloaded / (1024 * 1024)
            sys.stdout.write(f"\r  下载中: {mb_done:.1f} MB")
        sys.stdout.flush()

    if ssl_context:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl_context)
        )
        urllib.request.install_opener(opener)

    urllib.request.urlretrieve(url, dest, reporthook=reporthook)
    print()  # newline after progress bar


def try_download(url, dest):
    """Try to download, handling SSL errors."""
    # Attempt 1: normal SSL verification
    try:
        download_with_progress(url, dest)
        return True
    except (urllib.error.URLError, ssl.SSLError) as e:
        if "CERTIFICATE_VERIFY_FAILED" not in str(e):
            raise  # not an SSL issue, re-raise

    # Attempt 2: skip SSL verification (common fix for Windows)
    print("\n  SSL 证书验证失败，尝试跳过验证...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        download_with_progress(url, dest, ssl_context=ctx)
        return True
    except Exception:
        return False


def main():
    model_path = get_model_path()

    # Check if model already exists and is valid
    if os.path.exists(model_path):
        print(f"检查已有模型: {model_path}")
        print("  校验 SHA256...", end=" ", flush=True)
        file_hash = sha256_file(model_path)
        if file_hash == MODEL_SHA256:
            size_mb = os.path.getsize(model_path) / (1024 * 1024)
            print(f"通过 ({size_mb:.0f} MB)")
            print(f"[OK] 模型完整，跳过下载")
            return 0
        else:
            print(f"不匹配!")
            print(f"  期望: {MODEL_SHA256[:16]}...")
            print(f"  实际: {file_hash[:16]}...")
            print(f"[警告] 模型文件损坏或版本不对，重新下载...")
            os.remove(model_path)

    print(f"目标路径: {model_path}")
    print(f"文件大小约 500MB, 请耐心等待...")
    print()

    tmp_path = model_path + ".downloading"

    for name, url in ordered_sources():
        print(f"[{name}] {url}")
        try:
            # Clean up any previous partial download
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

            if try_download(url, tmp_path):
                # Verify SHA256
                print("  校验 SHA256...", end=" ", flush=True)
                file_hash = sha256_file(tmp_path)
                if file_hash == MODEL_SHA256:
                    size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
                    os.rename(tmp_path, model_path)
                    print(f"通过")
                    print(f"[OK] 模型下载完成! ({size_mb:.0f} MB)")
                    return 0
                else:
                    print(f"不匹配!")
                    print(f"  期望: {MODEL_SHA256[:16]}...")
                    print(f"  实际: {file_hash[:16]}...")
                    os.remove(tmp_path)
        except Exception as e:
            err = str(e).split("\n")[0][:80]
            print(f"\n  失败: {err}")

        # Clean up
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print()

    # All sources failed
    print("=" * 50)
    print("[错误] 所有下载源都失败了!")
    print()
    print("请手动下载模型:")
    print(f"  链接: {SOURCES[0][1]}")
    print(f"  放到: {model_path}")
    print("=" * 50)
    return 1


if __name__ == "__main__":
    sys.exit(main())
