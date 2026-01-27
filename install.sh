#!/bin/bash
# ============================================================
# Sharp GUI - 一键安装脚本
# 自动拉取 Apple ml-sharp 并部署 GUI
# 支持: Linux (x86_64/aarch64), macOS (Intel/Apple Silicon)
# ============================================================

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_step() { echo -e "${BLUE}==>${NC} $1"; }
print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }

# 配置
SHARP_REPO="https://github.com/apple/ml-sharp.git"
SHARP_DIR="ml-sharp"

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检测操作系统
detect_os() {
    OS="unknown"
    ARCH=$(uname -m)
    
    case "$(uname -s)" in
        Linux*)     OS="linux";;
        Darwin*)    OS="macos";;
        CYGWIN*|MINGW*|MSYS*) OS="windows";;
    esac
    
    echo "检测到系统 (Detected): $OS ($ARCH)"
}

# 检查 Python (详细指引)
check_python() {
    print_step "检查 Python 环境..."
    
    for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v $cmd &> /dev/null; then
            PYTHON_CMD=$cmd
            PYTHON_VERSION=$($cmd --version 2>&1 | awk '{print $2}')
            PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
            PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
            
            # 检查版本 >= 3.10
            if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 10 ]; then
                break
            else
                print_warning "找到 Python $PYTHON_VERSION，但需要 3.10+"
                PYTHON_CMD=""
            fi
        fi
    done
    
    if [ -z "$PYTHON_CMD" ]; then
        print_error "未找到 Python 3.10+！"
        echo ""
        echo "╔══════════════════════════════════════════════════════════════╗"
        echo "║           请安装 Python 3.10+ (Install Python)               ║"
        echo "╠══════════════════════════════════════════════════════════════╣"
        if [ "$OS" == "macos" ]; then
            echo "║  方式一 - Homebrew (推荐):                                    ║"
            echo "║    brew install python@3.12                                   ║"
            echo "║                                                               ║"
            echo "║  方式二 - 官方安装包:                                          ║"
            echo "║    https://www.python.org/downloads/                          ║"
        elif [ "$OS" == "linux" ]; then
            echo "║  Ubuntu/Debian:                                               ║"
            echo "║    sudo apt update                                            ║"
            echo "║    sudo apt install python3.12 python3.12-venv python3-pip    ║"
            echo "║                                                               ║"
            echo "║  Fedora/RHEL/CentOS:                                          ║"
            echo "║    sudo dnf install python3.12                                ║"
            echo "║                                                               ║"
            echo "║  Arch Linux:                                                  ║"
            echo "║    sudo pacman -S python                                      ║"
        fi
        echo "╚══════════════════════════════════════════════════════════════╝"
        exit 1
    fi
    
    # 检查 venv 模块
    if ! $PYTHON_CMD -m venv --help &> /dev/null; then
        print_error "Python venv 模块不可用！"
        echo ""
        if [ "$OS" == "linux" ]; then
            echo "请安装: sudo apt install python3-venv"
        fi
        exit 1
    fi
    
    print_success "找到 Python: $PYTHON_CMD ($PYTHON_VERSION)"
}

# 检查 Git
check_git() {
    print_step "检查 Git..."
    
    if ! command -v git &> /dev/null; then
        print_error "未找到 Git！"
        echo ""
        echo "╔══════════════════════════════════════════════════════════════╗"
        echo "║              请安装 Git (Install Git)                        ║"
        echo "╠══════════════════════════════════════════════════════════════╣"
        if [ "$OS" == "macos" ]; then
            echo "║  xcode-select --install                                       ║"
            echo "║  或: brew install git                                         ║"
        elif [ "$OS" == "linux" ]; then
            echo "║  Ubuntu/Debian: sudo apt install git                          ║"
            echo "║  Fedora/RHEL:   sudo dnf install git                          ║"
            echo "║  Arch Linux:    sudo pacman -S git                            ║"
        fi
        echo "╚══════════════════════════════════════════════════════════════╝"
        exit 1
    fi
    
    print_success "Git 已安装"
}

# 检查 CUDA
check_cuda() {
    if [ "$OS" == "linux" ]; then
        print_step "检查 CUDA 环境..."
        
        if command -v nvcc &> /dev/null; then
            CUDA_VERSION=$(nvcc --version | grep "release" | awk '{print $6}' | cut -d',' -f1)
            print_success "找到 CUDA: $CUDA_VERSION"
            HAS_CUDA=true
        elif command -v nvidia-smi &> /dev/null; then
            print_warning "找到 NVIDIA 驱动，但未安装 CUDA toolkit"
            print_warning "视频渲染功能将不可用，推理可以正常工作"
            HAS_CUDA=false
        else
            print_warning "未检测到 NVIDIA GPU，将使用 CPU 模式"
            print_warning "这没问题！3D 生成在 CPU 上也能正常运行"
            HAS_CUDA=false
        fi
    elif [ "$OS" == "macos" ]; then
        print_step "检查加速支持..."
        if system_profiler SPDisplaysDataType 2>/dev/null | grep -q "Apple M"; then
            print_success "检测到 Apple Silicon，将使用 MPS 加速"
        else
            print_warning "Intel Mac 将使用 CPU 模式"
        fi
        HAS_CUDA=false
    fi
}

# 检测 Node.js (用于 React 前端)
check_node() {
    print_step "检查 Node.js 环境..."
    
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version)
        NODE_MAJOR=$(echo $NODE_VERSION | sed 's/v//' | cut -d. -f1)
        
        if [ "$NODE_MAJOR" -ge 18 ]; then
            print_success "找到 Node.js: $NODE_VERSION"
            HAS_NODE=true
        else
            print_warning "找到 Node.js $NODE_VERSION，但推荐 18+"
            HAS_NODE=true
        fi
    else
        print_warning "未找到 Node.js，跳过前端安装"
        echo ""
        echo "  如需使用 React 版本，请安装 Node.js 18+:"
        if [ "$OS" == "macos" ]; then
            echo "    brew install node"
        else
            echo "    # Ubuntu/Debian:"
            echo "    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
            echo "    sudo apt install nodejs"
            echo ""
            echo "    # 或使用 nvm (推荐):"
            echo "    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
            echo "    nvm install 20"
        fi
        echo ""
        echo "  注意：预构建包已包含编译好的前端，无需安装 Node.js"
        HAS_NODE=false
    fi
}

# 拉取/更新 ml-sharp
clone_or_update_sharp() {
    print_step "获取 Apple ml-sharp..."
    
    if [ -d "$SCRIPT_DIR/$SHARP_DIR" ]; then
        print_warning "ml-sharp 目录已存在"
        read -p "是否更新到最新版本? [Y/n] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            cd "$SCRIPT_DIR/$SHARP_DIR"
            git pull origin main || git pull origin master || true
            cd "$SCRIPT_DIR"
            print_success "ml-sharp 已更新"
        fi
    else
        echo "正在克隆 $SHARP_REPO ..."
        git clone --depth 1 "$SHARP_REPO" "$SHARP_DIR"
        print_success "ml-sharp 克隆完成"
    fi
}

# 创建虚拟环境
create_venv() {
    print_step "创建虚拟环境..."
    
    VENV_DIR="$SCRIPT_DIR/venv"
    
    if [ -d "$VENV_DIR" ]; then
        print_warning "虚拟环境已存在: $VENV_DIR"
        read -p "是否删除并重新创建? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
        else
            print_success "使用现有虚拟环境"
            return
        fi
    fi
    
    $PYTHON_CMD -m venv "$VENV_DIR"
    print_success "虚拟环境创建完成"
}

# 安装依赖
install_dependencies() {
    print_step "安装 Python 依赖..."
    
    VENV_DIR="$SCRIPT_DIR/venv"
    source "$VENV_DIR/bin/activate"
    
    # 升级 pip
    pip install --upgrade pip
    
    # 安装 ml-sharp
    print_step "安装 Sharp 核心 (这可能需要几分钟)..."
    cd "$SCRIPT_DIR/$SHARP_DIR"
    pip install -r requirements.txt
    cd "$SCRIPT_DIR"
    
    # 安装 GUI 依赖
    print_step "安装 GUI 依赖..."
    pip install flask
    
    print_success "所有依赖安装完成"
}

# 配置 GUI
setup_gui() {
    print_step "配置 GUI..."
    
    # 创建目录
    mkdir -p "$SCRIPT_DIR/inputs"
    mkdir -p "$SCRIPT_DIR/outputs"
    
    print_success "GUI 配置完成"
}

# 安装前端依赖 (可选)
install_frontend() {
    if [ "$HAS_NODE" != "true" ]; then
        print_warning "跳过前端安装 (Node.js 不可用)"
        return
    fi
    
    if [ ! -d "$SCRIPT_DIR/frontend" ]; then
        print_warning "跳过前端安装 (frontend 目录不存在)"
        return
    fi
    
    print_step "安装前端依赖..."
    cd "$SCRIPT_DIR/frontend"
    npm install
    cd "$SCRIPT_DIR"
    print_success "前端依赖安装完成"
}

# 生成 HTTPS 证书
generate_https_cert() {
    print_step "生成 HTTPS 证书 (可选)..."
    
    VENV_DIR="$SCRIPT_DIR/venv"
    source "$VENV_DIR/bin/activate"
    
    # 检查 OpenSSL
    if ! command -v openssl &> /dev/null; then
        print_warning "未找到 OpenSSL，跳过证书生成"
        if [ "$OS" == "macos" ]; then
            echo "  可通过 brew install openssl 安装"
        elif [ "$OS" == "linux" ]; then
            echo "  可通过 sudo apt install openssl 安装"
        fi
        echo "  HTTPS 不可用，陀螺仪功能仅限本机访问"
        return 0
    fi
    
    # 生成证书
    if python "$SCRIPT_DIR/generate_cert.py"; then
        print_success "HTTPS 证书已生成"
    else
        print_warning "证书生成失败，但不影响基本功能"
        echo "  HTTPS 不可用，陀螺仪功能仅限本机访问"
        echo "  可稍后手动运行: python generate_cert.py"
    fi
}

# 测试安装
test_installation() {
    print_step "测试安装..."
    
    VENV_DIR="$SCRIPT_DIR/venv"
    source "$VENV_DIR/bin/activate"
    
    if sharp --help &> /dev/null; then
        print_success "Sharp CLI 可用"
    else
        print_error "Sharp CLI 安装失败"
        exit 1
    fi
    
    python -c "import torch; print(f'PyTorch: {torch.__version__}')" || {
        print_error "PyTorch 导入失败"
        exit 1
    }
    
    python -c "import flask; print(f'Flask: {flask.__version__}')" || {
        print_error "Flask 导入失败"
        exit 1
    }
    
    print_success "安装测试通过"
}

# 显示完成信息
show_completion() {
    echo ""
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  Sharp GUI 安装完成!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo ""
    echo "使用方法 (Usage):"
    echo ""
    echo "  1. 启动 GUI (Start GUI):"
    echo "     ./run.sh"
    echo ""
    echo "  2. 命令行推理 (CLI Inference):"
    echo "     source venv/bin/activate"
    echo "     sharp predict -i input.jpg -o outputs/"
    echo ""
    if [ "$OS" == "linux" ] && [ "$HAS_CUDA" == "true" ]; then
        echo "  3. 渲染视频 (需要 CUDA):"
        echo "     sharp predict -i input.jpg -o outputs/ --render"
        echo ""
    fi
    echo "首次运行会自动下载模型 (~500MB)"
    echo "First run will download model automatically."
    echo ""
}

# 主流程
main() {
    echo ""
    echo "========================================"
    echo "  Sharp GUI - 一键安装脚本"
    echo "  https://github.com/apple/ml-sharp"
    echo "========================================"
    echo ""
    
    detect_os
    check_python
    check_git
    check_cuda
    check_node
    clone_or_update_sharp
    create_venv
    install_dependencies
    setup_gui
    install_frontend
    generate_https_cert
    test_installation
    show_completion
}

main "$@"
