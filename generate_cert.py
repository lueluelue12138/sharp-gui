#!/usr/bin/env python3
"""
生成自签名 SSL 证书用于内网 HTTPS 访问
运行: python generate_cert.py
"""
import os
import subprocess
import sys

CERT_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_FILE = os.path.join(CERT_DIR, 'cert.pem')
KEY_FILE = os.path.join(CERT_DIR, 'key.pem')

def generate_certificate():
    """使用 OpenSSL 生成自签名证书"""
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        print("✅ 证书已存在，跳过生成")
        print(f"   证书: {CERT_FILE}")
        print(f"   密钥: {KEY_FILE}")
        return True
    
    print("🔐 正在生成自签名 SSL 证书...")
    
    # OpenSSL 命令生成证书
    cmd = [
        'openssl', 'req', '-x509', '-newkey', 'rsa:4096',
        '-keyout', KEY_FILE,
        '-out', CERT_FILE,
        '-days', '365',
        '-nodes',  # 无密码
        '-subj', '/CN=Sharp3D-Local/O=Sharp3D/C=CN',
        '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1,IP:0.0.0.0'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ 证书生成成功!")
            print(f"   证书: {CERT_FILE}")
            print(f"   密钥: {KEY_FILE}")
            print("\n📱 首次在设备上访问时会显示安全警告，选择「继续访问」即可")
            return True
        else:
            print(f"❌ 生成失败: {result.stderr}")
            return False
    except FileNotFoundError:
        print("❌ 未找到 openssl 命令，请先安装 OpenSSL")
        print("   macOS: brew install openssl")
        print("   Ubuntu: sudo apt install openssl")
        return False

if __name__ == '__main__':
    generate_certificate()
