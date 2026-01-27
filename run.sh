#!/bin/bash
# ============================================================
# Sharp GUI - 一键启动脚本 (Linux/macOS)
# 
# 用法: ./run.sh [--legacy]
#   --legacy  使用原始单文件版本
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 默认使用 React 版本
USE_LEGACY=false

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --legacy)
            USE_LEGACY=true
            shift
            ;;
        -h|--help)
            echo "用法 (Usage): ./run.sh [--legacy]"
            echo ""
            echo "选项 (Options):"
            echo "  --legacy    使用原始单文件前端"
            echo "  -h, --help  显示帮助信息"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

# 检查虚拟环境
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  错误: 虚拟环境不存在 (Virtual environment not found)        ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  请先运行安装脚本:                                            ║"
    echo "║    ./install.sh                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    exit 1
fi

# 检查 ml-sharp
if [ ! -d "$SCRIPT_DIR/ml-sharp" ]; then
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  错误: ml-sharp 未安装 (ml-sharp not installed)              ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  请先运行安装脚本:                                            ║"
    echo "║    ./install.sh                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    exit 1
fi

# 激活虚拟环境
source "$SCRIPT_DIR/venv/bin/activate"

# 检查 sharp 命令
if ! command -v sharp &> /dev/null; then
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  错误: Sharp 未正确安装 (Sharp not properly installed)       ║"
    echo "╠══════════════════════════════════════════════════════════════╣"
    echo "║  请重新安装:                                                  ║"
    echo "║    rm -rf venv && ./install.sh                               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    exit 1
fi

echo ""
echo "========================================"
echo "  Sharp GUI 启动中..."
echo "========================================"
echo ""

# 获取本机局域网 IP
if [[ "$OSTYPE" == "darwin"* ]]; then
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || \
               ifconfig 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1 || \
               echo "127.0.0.1")
else
    LOCAL_IP=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)' | head -1)
    LOCAL_IP=${LOCAL_IP:-127.0.0.1}
fi

# 检查 HTTPS 证书状态
echo ""
if [ -f "$SCRIPT_DIR/cert.pem" ] && [ -f "$SCRIPT_DIR/key.pem" ]; then
    PROTOCOL="https"
    echo "🔒 HTTPS 模式 (完整功能)"
else
    PROTOCOL="http"
    echo "🌐 HTTP 模式"
    echo "   💡 运行 'python generate_cert.py' 可启用 HTTPS，支持局域网陀螺仪"
fi
echo ""
echo "访问地址 (Access URLs):"
echo "  本地:    ${PROTOCOL}://127.0.0.1:5050"
echo "  局域网:  ${PROTOCOL}://${LOCAL_IP}:5050"
echo ""
echo "按 Ctrl+C 停止服务器"
echo "=========================================="
echo ""

# 传递 LAN IP 给 Flask
export SHARP_LAN_IP="${LOCAL_IP}"

# 设置前端模式
if [ "$USE_LEGACY" == "true" ]; then
    echo "📦 Legacy 模式 (单文件版本)"
    export SHARP_FRONTEND_MODE="legacy"
else
    if [ -d "$SCRIPT_DIR/frontend/dist" ]; then
        echo "⚛️  React 模式 (现代版本)"
        export SHARP_FRONTEND_MODE="react"
    else
        echo "⚠️  React 构建不存在，使用 Legacy 模式"
        echo "   运行 './build.sh' 可构建 React 前端"
        export SHARP_FRONTEND_MODE="legacy"
    fi
fi
echo ""

python app.py
