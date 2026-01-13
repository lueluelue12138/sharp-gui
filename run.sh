#!/bin/bash
# ============================================================
# Sharp GUI - 一键启动脚本 (Linux/macOS)
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查虚拟环境
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "错误: 虚拟环境不存在"
    echo "请先运行: ./install.sh"
    exit 1
fi

# 检查 ml-sharp
if [ ! -d "$SCRIPT_DIR/ml-sharp" ]; then
    echo "错误: ml-sharp 未安装"
    echo "请先运行: ./install.sh"
    exit 1
fi

# 激活虚拟环境
source "$SCRIPT_DIR/venv/bin/activate"

# 检查 sharp 命令
if ! command -v sharp &> /dev/null; then
    echo "错误: Sharp 未正确安装"
    echo "请重新运行: ./install.sh"
    exit 1
fi

echo ""
echo "========================================"
echo "  Sharp GUI 启动中..."
echo "========================================"
echo ""

# 获取本机局域网 IP (跨平台: 使用 Python getaddrinfo)
LOCAL_IP=$(python3 -c "
import socket
try:
    ips = list(set(ip[4][0] for ip in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)))
    result = next((ip for ip in ips if ip.startswith('192.168.') or ip.startswith('10.') or (ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31 and not ip.startswith('172.17.'))), None)
    print(result or next((ip for ip in ips if not ip.startswith('127.')), '127.0.0.1'))
except: print('127.0.0.1')
" 2>/dev/null || echo "127.0.0.1")

# 检查 HTTPS 证书状态并显示访问地址
echo ""
if [ -f "$SCRIPT_DIR/cert.pem" ] && [ -f "$SCRIPT_DIR/key.pem" ]; then
    PROTOCOL="https"
    echo "🔒 HTTPS Mode / HTTPS 模式"
else
    PROTOCOL="http"
    echo "🌐 HTTP Mode / HTTP 模式"
    echo "   💡 Run 'python generate_cert.py' for HTTPS to support Gyroscope (陀螺仪)"
fi
echo ""
echo "Access URLs / 访问地址:"
echo "  Local / 本地:    ${PROTOCOL}://127.0.0.1:5050"
echo "  LAN / 局域网:    ${PROTOCOL}://${LOCAL_IP}:5050"
echo ""
echo "Press Ctrl+C to stop / 按 Ctrl+C 停止"
echo "=========================================="
echo ""

# 传递正确的 LAN IP 给 Flask，用于日志输出
export SHARP_LAN_IP="${LOCAL_IP}"
python app.py
