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

# 获取本机 IP (改进版：从物理网卡获取，排除虚拟接口)
get_local_ip() {
    # 方法: 遍历网卡，优先选择 wl*(WiFi) 或 en*/eth*(以太网) 接口
    # 排除: docker*, br*, veth*, lo, Mihomo, tun*, virbr*
    local ip=""
    
    # 获取所有网卡IP，格式: "IP 接口名"
    while read -r line; do
        local addr=$(echo "$line" | awk '{print $1}' | cut -d'/' -f1)
        local iface=$(echo "$line" | awk '{print $NF}')
        
        # 跳过虚拟接口
        case "$iface" in
            docker*|br-*|veth*|lo|Mihomo|tun*|virbr*|cni*) continue ;;
        esac
        
        # 优先选择 WiFi 或以太网接口
        case "$iface" in
            wl*|en*|eth*)
                echo "$addr"
                return
                ;;
        esac
    done < <(ip addr show | grep -E "inet " | grep -v "127.0.0.1" | awk '{print $2, $NF}')
    
    # 兜底: 返回 hostname -I 的第一个非 Docker/VPN IP
    for ip in $(hostname -I 2>/dev/null); do
        case "$ip" in
            172.17.*|28.0.*) continue ;;  # Docker, Mihomo
            *) echo "$ip"; return ;;
        esac
    done
    
    echo "127.0.0.1"
}

if [ "$(uname)" == "Darwin" ]; then
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "127.0.0.1")
else
    LOCAL_IP=$(get_local_ip)
fi

# 检查 HTTPS 证书状态并显示访问地址
echo ""
if [ -f "$SCRIPT_DIR/cert.pem" ] && [ -f "$SCRIPT_DIR/key.pem" ]; then
    PROTOCOL="https"
    echo "🔒 HTTPS Mode / HTTPS 模式"
else
    PROTOCOL="http"
    echo "🌐 HTTP Mode / HTTP 模式"
    echo "   💡 Run 'python generate_cert.py' for HTTPS"
fi
echo ""
echo "Access URLs / 访问地址:"
echo "  Local:    ${PROTOCOL}://127.0.0.1:5050"
echo "  LAN:      ${PROTOCOL}://${LOCAL_IP}:5050"
echo ""
echo "Press Ctrl+C to stop / 按 Ctrl+C 停止"
echo "=========================================="
echo ""

python app.py
