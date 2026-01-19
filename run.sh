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

# 获取本机局域网 IP (简洁版)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS: 优先 en0/en1，回退到 ifconfig 解析
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || \
               ifconfig 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1 || \
               echo "127.0.0.1")
else
    # Linux: hostname -I 返回所有非回环 IP，取第一个私有 IP
    LOCAL_IP=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)' | head -1)
    LOCAL_IP=${LOCAL_IP:-127.0.0.1}
fi

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
