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

# 获取本机 IP
if [ "$(uname)" == "Darwin" ]; then
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "127.0.0.1")
else
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
fi

echo "访问地址:"
echo "  本机: http://127.0.0.1:5050"
echo "  局域网: http://$LOCAL_IP:5050"
echo ""
echo "按 Ctrl+C 停止服务器"
echo ""

python app.py
