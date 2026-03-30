#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_DIR="backend"
TAURI_BIN_DIR="frontend/src-tauri/binaries"
BINARY_NAME="evoloop-backend"

# Detect Architecture (强制使用 aarch64 for Apple Silicon Macs)
ARCH=$(uname -m)
if [ "$ARCH" == "x86_64" ]; then
  # Check if we're on Apple Silicon running under Rosetta
  if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" == "1" ]; then
    TRIPLE="aarch64-apple-darwin"
    echo -e "${YELLOW}⚠️  Detected x86_64 shell on Apple Silicon, forcing aarch64 build${NC}"
  else
    TRIPLE="x86_64-apple-darwin"
  fi
elif [ "$ARCH" == "arm64" ]; then
  TRIPLE="aarch64-apple-darwin"
else
  echo -e "${RED}Unsupported architecture: $ARCH${NC}"
  exit 1
fi

TARGET_BINARY="${BINARY_NAME}-${TRIPLE}"

echo -e "${BLUE}🚀 Building Backend Sidecar for ${TRIPLE}...${NC}"

# Check if running in backend directory
if [ ! -f "pyproject.toml" ] && [ -f "backend/pyproject.toml" ]; then
  cd backend
  BACKEND_DIR="."
fi

# 1. Clean previous build
echo -e "${YELLOW}🧹 Cleaning previous build...${NC}"
rm -rf "dist" "build" "__pycache__"

# 2. Check Python environment
echo -e "${YELLOW}🐍 Checking Python environment...${NC}"
if ! command -v python3 &> /dev/null; then
  echo -e "${RED}❌ Python 3 not found${NC}"
  exit 1
fi

# Use virtual environment if available (强制使用 arm64)
if [ -d ".venv" ]; then
  PYTHON="arch -arm64 .venv/bin/python"
  echo -e "${GREEN}✅ Using virtual environment: .venv (arm64)${NC}"
else
  PYTHON="arch -arm64 python3"
  echo -e "${YELLOW}⚠️  No virtual environment found, using system Python (arm64)${NC}"
fi

# Check if pyinstaller is available
if ! $PYTHON -c "import PyInstaller" 2>/dev/null; then
  echo -e "${YELLOW}📦 Installing PyInstaller...${NC}"
  $PYTHON -m pip install pyinstaller
fi

# Check NumPy version (torch 2.2 requires NumPy 1.x)
echo -e "${YELLOW}🔍 Checking NumPy version...${NC}"
NUMPY_VERSION=$($PYTHON -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "")
if [ -n "$NUMPY_VERSION" ]; then
  NUMPY_MAJOR=$(echo "$NUMPY_VERSION" | cut -d. -f1)
  if [ "$NUMPY_MAJOR" = "2" ]; then
    echo -e "${YELLOW}⚠️  NumPy 2.x detected, downgrading to 1.26.4 for torch compatibility...${NC}"
    $PYTHON -m pip install "numpy==1.26.4" --force-reinstall
    echo -e "${GREEN}✅ NumPy downgraded to 1.26.4${NC}"
  else
    echo -e "${GREEN}✅ NumPy 1.x already installed (${NUMPY_VERSION})${NC}"
  fi
fi

# 3. Ensure NumPy 1.x before building (PyInstaller isolated process needs this)
echo -e "${YELLOW}🔧 Ensuring NumPy 1.x compatibility...${NC}"
$PYTHON -c "import numpy; print(f'NumPy version: {numpy.__version__}')"

# Set environment variable to help PyInstaller find correct NumPy
export PYTHONPATH="${PWD}:${PYTHONPATH}"

# 4. Build with PyInstaller (arm64)
echo -e "${BLUE}📦 Building with PyInstaller...${NC}"
echo -e "${YELLOW}   This may take several minutes...${NC}"

if [ -f "evoloop-backend.spec" ]; then
  # Use --noconfirm and ensure we're using the correct Python
  $PYTHON -m PyInstaller evoloop-backend.spec --clean --noconfirm
else
  echo -e "${RED}❌ PyInstaller spec file not found${NC}"
  exit 1
fi

# 4. Prepare Tauri Binaries Directory
mkdir -p "../${TAURI_BIN_DIR}"

# 5. Move and Rename Binary
if [ -f "dist/${BINARY_NAME}" ]; then
  mv "dist/${BINARY_NAME}" "../${TAURI_BIN_DIR}/${TARGET_BINARY}"
  echo -e "${GREEN}✅ Backend Sidecar built successfully${NC}"
  echo -e "${GREEN}   Location: ${TAURI_BIN_DIR}/${TARGET_BINARY}${NC}"
else
  echo -e "${RED}❌ Error: Binary not found at dist/${BINARY_NAME}${NC}"
  exit 1
fi

# 6. Set permissions
chmod +x "../${TAURI_BIN_DIR}/${TARGET_BINARY}"

# 7. Sign the binary (ad-hoc signing for local development)
echo -e "${YELLOW}🔏 Signing binary...${NC}"
codesign --force --sign - "../${TAURI_BIN_DIR}/${TARGET_BINARY}" 2>/dev/null || echo -e "${YELLOW}⚠️  Could not sign binary${NC}"

# 8. Show file size
FILE_SIZE=$(du -h "../${TAURI_BIN_DIR}/${TARGET_BINARY}" | cut -f1)
echo -e "${BLUE}📊 Binary size: ${FILE_SIZE}${NC}"

echo ""
echo -e "${GREEN}🎉 Build Complete!${NC}"
echo ""
echo -e "${BLUE}📋 Next steps:${NC}"
echo -e "   1. cd frontend && npm run tauri build"
echo -e "   2. Or test with: cd frontend && npm run tauri dev"
