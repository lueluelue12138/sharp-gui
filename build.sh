#!/bin/bash
# ============================================================
# Sharp GUI - 前端构建脚本
# 构建 React 生产版本
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "========================================"
echo "  Sharp GUI - 前端构建"
echo "========================================"
echo ""

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}错误:${NC} 未找到 Node.js"
    echo "请先安装 Node.js 18+ 或运行 install.sh"
    exit 1
fi

# 检查前端目录
if [ ! -d "$SCRIPT_DIR/frontend" ]; then
    echo -e "${YELLOW}错误:${NC} frontend 目录不存在"
    exit 1
fi

cd "$SCRIPT_DIR/frontend"

# 安装依赖 (如果需要)
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# 构建
echo "🔨 Building React frontend..."
npm run build

echo ""
echo -e "${GREEN}✅ 构建完成!${NC}"
echo "   输出目录: frontend/dist/"
echo ""
echo "运行 ./run.sh 启动服务器"
