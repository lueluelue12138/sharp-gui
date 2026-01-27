#!/bin/bash
# ============================================================
# Sharp GUI - Release Build Script
# Creates pre-built release package
#
# Usage: ./release.sh [version]
#   Example: ./release.sh v1.0.0
# ============================================================

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Get version
VERSION=${1:-$(date +%Y%m%d)}
if [[ ! $VERSION =~ ^v ]]; then
    VERSION="v$VERSION"
fi

echo ""
echo "========================================"
echo "  Sharp GUI - Release Build"
echo "  Version: $VERSION"
echo "========================================"
echo ""

# 1. Build frontend using build.sh
echo -e "${BLUE}==>${NC} Building frontend..."
./build.sh

# 2. Create release package
echo -e "${BLUE}==>${NC} Creating release package..."
RELEASE_DIR="$SCRIPT_DIR/.release-build"
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

# Copy core files
cp app.py generate_cert.py "$RELEASE_DIR/"
cp install.sh install.bat run.sh run.bat build.sh build.bat "$RELEASE_DIR/"
cp release.sh release.bat "$RELEASE_DIR/" 2>/dev/null || true
cp README.md README.en.md LICENSE "$RELEASE_DIR/" 2>/dev/null || true

# Copy directories
cp -r templates static frontend "$RELEASE_DIR/"

# Clean unnecessary files
rm -rf "$RELEASE_DIR/frontend/node_modules"
rm -rf "$RELEASE_DIR/frontend/.vite"
rm -rf "$RELEASE_DIR/frontend/src"

# Create zip
OUTPUT_FILE="$SCRIPT_DIR/sharp-gui-${VERSION}.zip"
cd "$RELEASE_DIR"
zip -r "$OUTPUT_FILE" . -q

# Cleanup
cd "$SCRIPT_DIR"
rm -rf "$RELEASE_DIR"

# Done
echo ""
echo -e "${GREEN}✓${NC} Release package created!"
echo ""
echo "  📦 File: sharp-gui-${VERSION}.zip"
echo "  📊 Size: $(du -h "$OUTPUT_FILE" | cut -f1)"
echo ""
echo "Next steps:"
echo "  1. Create GitHub Release: https://github.com/YOUR_REPO/releases/new"
echo "  2. Set tag: $VERSION"
echo "  3. Upload sharp-gui-${VERSION}.zip"
echo ""
