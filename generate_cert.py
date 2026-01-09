#!/usr/bin/env python3
"""
生成自签名 SSL 证书用于内网 HTTPS 访问
支持: macOS, Linux, Windows
运行: python generate_cert.py
"""
import os
import subprocess
import sys
import platform
import tempfile
import re
import argparse

CERT_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_FILE = os.path.join(CERT_DIR, 'cert.pem')
KEY_FILE = os.path.join(CERT_DIR, 'key.pem')


def get_openssl_path():
    """查找 OpenSSL 可执行文件路径"""
    system = platform.system()
    
    # 首先尝试系统 PATH
    try:
        result = subprocess.run(['openssl', 'version'], capture_output=True, text=True)
        if result.returncode == 0:
            return 'openssl'
    except FileNotFoundError:
        pass
    
    # Windows 常见安装路径
    if system == 'Windows':
        possible_paths = [
            # Git for Windows (最常见)
            r'C:\Program Files\Git\usr\bin\openssl.exe',
            r'C:\Program Files (x86)\Git\usr\bin\openssl.exe',
            # Chocolatey
            r'C:\ProgramData\chocolatey\bin\openssl.exe',
            # Strawberry Perl
            r'C:\Strawberry\c\bin\openssl.exe',
            # OpenSSL 官方安装
            r'C:\Program Files\OpenSSL-Win64\bin\openssl.exe',
            r'C:\Program Files (x86)\OpenSSL-Win32\bin\openssl.exe',
            # MSYS2
            r'C:\msys64\usr\bin\openssl.exe',
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
    
    return None


def get_openssl_version(openssl_path):
    """获取 OpenSSL 版本号"""
    try:
        result = subprocess.run([openssl_path, 'version'], capture_output=True, text=True)
        if result.returncode == 0:
            # 解析版本号，例如 "OpenSSL 1.1.1k  25 Mar 2021" 或 "LibreSSL 3.3.6"
            version_str = result.stdout.strip()
            match = re.search(r'(\d+\.\d+\.\d+)', version_str)
            if match:
                return match.group(1), version_str
    except Exception:
        pass
    return None, None


def version_tuple(version_str):
    """将版本字符串转换为可比较的元组"""
    try:
        return tuple(map(int, version_str.split('.')))
    except:
        return (0, 0, 0)


def supports_addext(version):
    """检查 OpenSSL 版本是否支持 -addext 选项 (需要 1.1.1+)"""
    if version is None:
        return False
    return version_tuple(version) >= (1, 1, 1)


def generate_with_addext(openssl_path):
    """使用 -addext 选项生成证书 (OpenSSL 1.1.1+)"""
    cmd = [
        openssl_path, 'req', '-x509', '-newkey', 'rsa:4096',
        '-keyout', KEY_FILE,
        '-out', CERT_FILE,
        '-days', '365',
        '-nodes',
        '-subj', '/CN=Sharp3D-Local/O=Sharp3D/C=CN',
        '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1,IP:0.0.0.0'
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def generate_with_extfile(openssl_path):
    """使用 -extfile 选项生成证书 (兼容旧版 OpenSSL)"""
    # 创建临时扩展配置文件
    ext_content = """
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = Sharp3D-Local
O = Sharp3D
C = CN

[v3_req]
subjectAltName = DNS:localhost,IP:127.0.0.1,IP:0.0.0.0
"""
    
    # 使用临时文件
    fd, ext_file = tempfile.mkstemp(suffix='.cnf')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(ext_content)
        
        cmd = [
            openssl_path, 'req', '-x509', '-newkey', 'rsa:4096',
            '-keyout', KEY_FILE,
            '-out', CERT_FILE,
            '-days', '365',
            '-nodes',
            '-config', ext_file,
            '-extensions', 'v3_req'
        ]
        return subprocess.run(cmd, capture_output=True, text=True)
    finally:
        # 清理临时文件
        try:
            os.unlink(ext_file)
        except:
            pass


def print_install_instructions():
    """根据平台打印 OpenSSL 安装指南"""
    system = platform.system()
    print("❌ 未找到 OpenSSL，请先安装：")
    print("")
    
    if system == 'Darwin':
        print("  macOS:")
        print("    brew install openssl")
        print("")
    elif system == 'Linux':
        print("  Ubuntu/Debian:")
        print("    sudo apt install openssl")
        print("")
        print("  CentOS/RHEL/Fedora:")
        print("    sudo dnf install openssl")
        print("")
    elif system == 'Windows':
        print("  Windows (推荐方式):")
        print("    1. 安装 Git for Windows: https://git-scm.com/download/win")
        print("       (自带 OpenSSL)")
        print("")
        print("    2. 或使用 Chocolatey:")
        print("       choco install openssl")
        print("")
        print("    3. 或下载 OpenSSL 安装包:")
        print("       https://slproweb.com/products/Win32OpenSSL.html")
        print("")


def generate_certificate(quiet=False):
    """使用 OpenSSL 生成自签名证书"""
    # 检查证书是否已存在
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        if not quiet:
            print("✅ 证书已存在，跳过生成")
            print(f"   证书: {CERT_FILE}")
            print(f"   密钥: {KEY_FILE}")
        return True
    
    # 查找 OpenSSL
    openssl_path = get_openssl_path()
    if openssl_path is None:
        print_install_instructions()
        return False
    
    # 获取版本信息
    version, version_str = get_openssl_version(openssl_path)
    
    if not quiet:
        print(f"🔐 正在生成自签名 SSL 证书...")
        print(f"   使用: {version_str or openssl_path}")
    
    # 根据版本选择生成方式
    try:
        if supports_addext(version):
            result = generate_with_addext(openssl_path)
        else:
            if not quiet:
                print(f"   (使用兼容模式，适用于 OpenSSL < 1.1.1)")
            result = generate_with_extfile(openssl_path)
        
        if result.returncode == 0:
            if not quiet:
                print("✅ 证书生成成功!")
                print(f"   证书: {CERT_FILE}")
                print(f"   密钥: {KEY_FILE}")
                print("")
                print("📱 首次在设备上访问时会显示安全警告，选择「继续访问」即可")
            return True
        else:
            print(f"❌ 生成失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 生成证书时出错: {e}")
        return False


def check_dependencies(quiet=False):
    """检查依赖是否就绪"""
    openssl_path = get_openssl_path()
    
    if openssl_path is None:
        if not quiet:
            print_install_instructions()
        return False
    
    version, version_str = get_openssl_version(openssl_path)
    
    if not quiet:
        print(f"✅ OpenSSL 已安装: {version_str}")
        print(f"   路径: {openssl_path}")
        if supports_addext(version):
            print(f"   支持 -addext 选项")
        else:
            print(f"   将使用兼容模式 (-extfile)")
    
    return True


def main():
    parser = argparse.ArgumentParser(description='生成自签名 SSL 证书用于 HTTPS')
    parser.add_argument('--check-only', action='store_true', 
                        help='仅检查依赖，不生成证书')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='静默模式，减少输出')
    
    args = parser.parse_args()
    
    if args.check_only:
        success = check_dependencies(quiet=args.quiet)
    else:
        success = generate_certificate(quiet=args.quiet)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
