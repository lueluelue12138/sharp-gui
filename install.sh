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

if [ "${SHARP_USE_CHINA_MIRROR:-1}" != "0" ]; then
    export SHARP_PIP_INDEX_URL="${SHARP_PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
    export PIP_INDEX_URL="$SHARP_PIP_INDEX_URL"
    export PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn mirrors.aliyun.com pypi.org files.pythonhosted.org}"
    export PIP_DISABLE_PIP_VERSION_CHECK=1
    export SHARP_MODEL_SOURCE="${SHARP_MODEL_SOURCE:-china}"
    echo "Using PyPI mirror: $PIP_INDEX_URL"
fi

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
    
    # --- 检测并安装正确版本的 PyTorch ---
    # Linux 上 PyPI 的 torch 默认包含 CUDA 支持，但有时可能安装了 CPU 版
    CUDA_INDEX_URL=""
    if [ "$OS" == "linux" ] && command -v nvidia-smi &> /dev/null; then
        print_step "检测到 NVIDIA GPU，检查 PyTorch CUDA 支持..."
        
        if python -c "import torch; exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
            print_success "PyTorch 已支持 CUDA，无需重装"
        else
            print_warning "当前 PyTorch 不支持 CUDA，将自动选择合适的 CUDA 版本"
            
            # 从 nvidia-smi 获取驱动支持的 CUDA 版本
            DRIVER_CUDA_VER=$(nvidia-smi 2>/dev/null | grep -oP "CUDA Version: \K[0-9.]+" || echo "")
            
            if [ -n "$DRIVER_CUDA_VER" ]; then
                CUDA_MAJOR=$(echo "$DRIVER_CUDA_VER" | cut -d. -f1)
                echo "驱动支持的 CUDA 版本: $DRIVER_CUDA_VER"
                
                if [ "$CUDA_MAJOR" -ge 12 ] 2>/dev/null; then
                    CUDA_INDEX_URL="https://download.pytorch.org/whl/cu124"
                    echo "选择 PyTorch CUDA 12.4 版本"
                elif [ "$CUDA_MAJOR" -ge 11 ] 2>/dev/null; then
                    CUDA_INDEX_URL="https://download.pytorch.org/whl/cu118"
                    echo "选择 PyTorch CUDA 11.8 版本"
                else
                    print_warning "CUDA 版本过低 ($DRIVER_CUDA_VER)，将使用 CPU 模式"
                fi
            else
                # 无法检测版本，使用兼容性最好的 CUDA 11.8
                CUDA_INDEX_URL="https://download.pytorch.org/whl/cu118"
                echo "无法检测 CUDA 版本，使用兼容性最广的 CUDA 11.8"
            fi
            
            if [ -n "$CUDA_INDEX_URL" ]; then
                echo "下载源: $CUDA_INDEX_URL"
                if pip install torch torchvision --index-url "$CUDA_INDEX_URL" --force-reinstall; then
                    print_success "CUDA 版 PyTorch 安装完成！"
                else
                    print_warning "CUDA 版 PyTorch 安装失败，将使用 CPU 版本"
                    echo "  推理仍可工作，但速度较慢"
                fi
            fi
        fi
    fi
    
    # 安装 ml-sharp
    print_step "安装 Sharp 核心 (这可能需要几分钟)..."
    cd "$SCRIPT_DIR/$SHARP_DIR"
    pip install -r requirements.txt
    cd "$SCRIPT_DIR"
    
    # --- 保护: 确保 CUDA torch 没有被 requirements.txt 覆盖 ---
    if [ "$OS" == "linux" ] && [ -n "$CUDA_INDEX_URL" ]; then
        if ! python -c "import torch; exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
            print_warning "CUDA PyTorch 被 requirements.txt 覆盖，正在重新安装..."
            if pip install torch torchvision --index-url "$CUDA_INDEX_URL" --force-reinstall; then
                print_success "CUDA 版 PyTorch 重新安装完成"
            fi
        fi
    fi

    print_step "检查 PyTorch CUDA / ROCm 运行环境..."
    if ! python "$SCRIPT_DIR/tools/install_torch.py"; then
        print_error "PyTorch CUDA / ROCm 运行环境验证失败"
        exit 1
    fi
    
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

# 下载模型
download_model() {
    print_step "下载推理模型..."
    
    VENV_DIR="$SCRIPT_DIR/venv"
    source "$VENV_DIR/bin/activate"
    
    if python "$SCRIPT_DIR/tools/download_model.py"; then
        print_success "模型准备完成"
    else
        print_warning "模型下载失败，首次推理时会重试下载"
        echo "  也可稍后手动下载 (见下方提示)"
    fi
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
    if python "$SCRIPT_DIR/tools/generate_cert.py"; then
        print_success "HTTPS 证书已生成"
    else
        print_warning "证书生成失败，但不影响基本功能"
        echo "  HTTPS 不可用，陀螺仪功能仅限本机访问"
        echo "  可稍后手动运行: python tools/generate_cert.py"
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
    
    # 显示 GPU 状态
    python -c "import torch; cuda=torch.cuda.is_available(); hip=getattr(torch.version,'hip',None); mps=hasattr(torch.backends,'mps') and torch.backends.mps.is_available(); device='ROCm (AMD GPU)' if cuda and hip else ('CUDA (NVIDIA GPU)' if cuda else ('MPS (Apple GPU)' if mps else 'CPU')); print(f'推理设备: {device}')"
    
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
    echo -e "${YELLOW}提示: 如果推理时提示模型缺失或下载失败，可手动下载:${NC}"
    echo ""
    echo "  下载地址 (任选其一):"
    echo "    HuggingFace: https://huggingface.co/apple/Sharp/resolve/main/sharp_2572gikvuh.pt"
    echo "    HF镜像(国内): https://hf-mirror.com/apple/Sharp/resolve/main/sharp_2572gikvuh.pt"
    echo ""
    echo "  下载后放到:"
    python -c "import os; print(f'    {os.path.expanduser(\"~/.cache/torch/hub/checkpoints/sharp_2572gikvuh.pt\")}')"
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
    clone_or_update_sharp
    create_venv
    install_dependencies
    setup_gui
    download_model
    generate_https_cert
    test_installation
    show_completion
}

main "$@"
