#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default models to download (embedding only — required for all deployments)
# Speech models (paraformer-*) only needed for Tauri desktop client builds
DEFAULT_MODELS="nomic-embed"
ALL_MODELS="paraformer-zh paraformer-zh-en paraformer-zh-plus paraformer-zh-streaming nomic-embed"

# Parse arguments
MODELS_TO_DOWNLOAD=""
DOWNLOAD_ALL=false
SKIP_FUNASR_CHECK=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --all|-a)
            DOWNLOAD_ALL=true
            shift
            ;;
        --models|-m)
            MODELS_TO_DOWNLOAD="$2"
            shift 2
            ;;
        --skip-funasr-check)
            SKIP_FUNASR_CHECK=true
            shift
            ;;
        --help|-h)
            echo "Download AI models for EvoLoop"
            echo ""
            echo "Usage:"
            echo "  $0 [--models model1,model2] [--all] [--skip-funasr-check]"
            echo ""
            echo "Options:"
            echo "  --models, -m       Comma-separated list of models to download"
            echo "  --all, -a          Download all available models"
            echo "  --skip-funasr-check Skip FunASR installation check"
            echo "  --help, -h         Show this help"
            echo ""
            echo "Available models:"
            echo "  nomic-embed                (default, text embeddings — required for all deployments)"
            echo "  paraformer-zh              (Chinese + English ASR — for desktop client only)"
            echo "  paraformer-zh-en           (Chinese + English mixed)"
            echo "  paraformer-zh-plus         (with VAD & punctuation)"
            echo "  paraformer-zh-streaming    (streaming recognition)"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Determine which models to download
if [ "$DOWNLOAD_ALL" = true ]; then
    MODELS_TO_DOWNLOAD="$ALL_MODELS"
elif [ -z "$MODELS_TO_DOWNLOAD" ]; then
    MODELS_TO_DOWNLOAD="$DEFAULT_MODELS"
fi

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║             EvoLoop Model Downloader (ARM64)                 ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Get project root to locate .env
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Ensure consistent CWD for relative path lookups (e.g. backend/.venv)
cd "$PROJECT_ROOT"

# Load .env if exists to get EVOLOOP_APP_DATA_DIR
if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep '^EVOLOOP_APP_DATA_DIR=' "$PROJECT_ROOT/.env" | xargs) 2>/dev/null || true
fi
APP_DATA_DIR="${EVOLOOP_APP_DATA_DIR:-$HOME/.evoloop}"

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

# Show configuration
echo -e "${CYAN}Configuration:${NC}"
echo -e "  Models: ${GREEN}$MODELS_TO_DOWNLOAD${NC}"
echo ""

# Check Python environment (ARM64)
echo -e "${YELLOW}🐍 Checking Python environment (arm64)...${NC}"

# Detect native architecture
NATIVE_ARCH=$(uname -m)

if [ "$NATIVE_ARCH" = "x86_64" ]; then
    # On Intel Macs or Linux x86_64, just use python3
    PYTHON_CMD="python3"
else
    # On Apple Silicon, force arm64 (in case we are in Rosetta)
    PYTHON_CMD="arch -arm64 python3"
fi

# Check if we can use backend venv
if [ -f "backend/.venv/bin/python" ]; then
    if [ "$NATIVE_ARCH" = "x86_64" ]; then
        PYTHON_CMD="backend/.venv/bin/python"
        echo -e "${GREEN}✅ Using backend virtual environment (x86_64)${NC}"
    else
        PYTHON_CMD="arch -arm64 backend/.venv/bin/python"
        echo -e "${GREEN}✅ Using backend virtual environment (arm64)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Using system Python (arm64)${NC}"
fi

# Verify Python works
if ! $PYTHON_CMD -c "import platform; print(platform.machine())" &> /dev/null; then
    echo -e "${RED}❌ Python not found or not working ($PYTHON_CMD)${NC}"
    exit 1
fi

# Detect architecture
ARCH=$(uname -m)
IS_APPLE_SILICON=false
if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
    IS_APPLE_SILICON=true
    echo -e "${CYAN}📱 Detected Apple Silicon (M1/M2/M3/M4)${NC}"
fi

# Check Python architecture
PYTHON_ARCH=$($PYTHON_CMD -c "import platform; print(platform.machine())")
if [ "$PYTHON_ARCH" = "arm64" ] || [ "$PYTHON_ARCH" = "x86_64" ]; then
    echo -e "${GREEN}✅ Python architecture is $PYTHON_ARCH${NC}"
else
    if [ "$IS_APPLE_SILICON" = true ] && [ "$PYTHON_ARCH" != "arm64" ]; then
        echo -e "${YELLOW}⚠️  Python is running under Rosetta, forcing arm64...${NC}"
        PYTHON_CMD="arch -arm64 $PYTHON_CMD"
    fi
fi

# Install modelscope first (required for downloading)
echo ""
echo -e "${YELLOW}📦 Checking dependencies...${NC}"

# Function to handle pip installs with uv fallback
pip_install() {
    local python_path="$PYTHON_CMD"
    if [[ "$python_path" == "arch -arm64 "* ]]; then
        python_path="${python_path#arch -arm64 }"
    fi

    if command -v uv &> /dev/null; then
        if [ -n "$VIRTUAL_ENV" ] || [ -f "$PROJECT_ROOT/backend/.venv/pyvenv.cfg" ]; then
            uv pip install --python "$python_path" "$@"
        else
            uv pip install --system "$@"
        fi
    else
        $PYTHON_CMD -m pip install "$@"
    fi
}

# Function to install package with fallback
install_package() {
    local pkg=$1
    pip_install --only-binary :all: "$pkg" 2>/dev/null || \
        pip_install "$pkg"
}

# Check NumPy version (modelscope and torch require NumPy 1.x)
echo -e "${YELLOW}🔍 Checking NumPy version...${NC}"
NUMPY_VERSION=$($PYTHON_CMD -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "")
if [ -n "$NUMPY_VERSION" ]; then
    NUMPY_MAJOR=$(echo "$NUMPY_VERSION" | cut -d. -f1)
    if [ "$NUMPY_MAJOR" = "2" ]; then
        echo -e "${YELLOW}⚠️  NumPy 2.x detected, downgrading to 1.26.4...${NC}"
        pip_install "numpy==1.26.4" --force-reinstall -q
        echo -e "${GREEN}✅ NumPy downgraded to 1.26.4${NC}"
    else
        echo -e "${GREEN}✅ NumPy 1.x already installed (${NUMPY_VERSION})${NC}"
    fi
else
    echo -e "${YELLOW}📦 Installing NumPy 1.26.4...${NC}"
    install_package "numpy==1.26.4"
fi

# Install modelscope (lightweight, no heavy dependencies)
if ! $PYTHON_CMD -c "import modelscope" 2>/dev/null; then
    echo -e "${YELLOW}📦 Installing modelscope (required for downloading)...${NC}"
    install_package "modelscope" || {
        echo -e "${RED}❌ Failed to install modelscope${NC}"
        exit 1
    }
fi
echo -e "${GREEN}✅ modelscope installed${NC}"

# Optional: Try to install funasr (not required for downloading, but good for verification)
FUNASR_AVAILABLE=false
if [ "$SKIP_FUNASR_CHECK" = false ]; then
    if ! $PYTHON_CMD -c "import funasr" 2>/dev/null; then
        echo -e "${YELLOW}📦 Installing FunASR (optional, for model verification)...${NC}"
        echo -e "${CYAN}   Note: This may take a while on Apple Silicon${NC}"
        
        # Try to install funasr with torch
        pip_install torch torchaudio 2>/dev/null || true
        
        # Try funasr installation (may fail on llvmlite, that's OK)
        pip_install funasr 2>/dev/null && FUNASR_AVAILABLE=true || {
            echo -e "${YELLOW}⚠️  FunASR installation incomplete (this is OK for downloading)${NC}"
            if [ "$IS_APPLE_SILICON" = true ]; then
                echo ""
                echo -e "${CYAN}💡 To use FunASR on Apple Silicon, you have options:${NC}"
                echo -e "   1. Use conda: conda install -c conda-forge numba llvmlite"
                echo -e "   2. Download models only (models will work when bundled)"
            fi
        }
    else
        FUNASR_AVAILABLE=true
        echo -e "${GREEN}✅ FunASR already installed${NC}"
    fi
else
    echo -e "${YELLOW}⏭️  Skipping FunASR check${NC}"
fi

# Set up model directory
MODEL_DIR="$APP_DATA_DIR/models"
echo ""
echo -e "${YELLOW}📁 Model directory: ${CYAN}$MODEL_DIR${NC}"
mkdir -p "$MODEL_DIR"

# Download models
echo ""
echo -e "${YELLOW}⬇️  Downloading models...${NC}"
echo ""

for model_name in $MODELS_TO_DOWNLOAD; do
    echo -e "${BLUE}────────────────────────────────────────${NC}"
    echo -e "${CYAN}Downloading: $model_name${NC}"
    echo -e "${BLUE}────────────────────────────────────────${NC}"
    
    case $model_name in
        paraformer-zh|paraformer-zh-en)
            # zh-en uses the same model as zh (supports both Chinese and English)
            model_id="damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
            ;;
        paraformer-zh-plus)
            model_id="damo/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
            ;;
        paraformer-zh-streaming)
            model_id="damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online"
            ;;
        nomic-embed)
            echo -e "${YELLOW}📦 Installing sentence-transformers if needed...${NC}"
            pip_install sentence-transformers 2>/dev/null || true
            $PYTHON_CMD backend/scripts/download_models.py
            if [ $? -eq 0 ]; then
                echo -e "${GREEN}✅ $model_name downloaded successfully${NC}"
            else
                echo -e "${RED}❌ $model_name download failed${NC}"
            fi
            echo ""
            continue
            ;;
        *)
            echo -e "${RED}❌ Unknown model: $model_name${NC}"
            continue
            ;;
    esac
    
    # Download using modelscope
    $PYTHON_CMD << PYTHON_SCRIPT
import sys
sys.path.insert(0, 'backend')
from modelscope import snapshot_download
import os

model_id = "$model_id"
model_dir = "$MODEL_DIR"

try:
    print(f"Downloading {model_id}...")
    download_dir = snapshot_download(model_id, cache_dir=model_dir)
    print(f"✅ Downloaded to: {download_dir}")
except Exception as e:
    print(f"❌ Failed to download: {e}")
    sys.exit(1)
PYTHON_SCRIPT
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $model_name downloaded successfully${NC}"
    else
        echo -e "${RED}❌ $model_name download failed${NC}"
    fi
    echo ""
done

# Show summary
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                   Download Summary                           ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✅ Models downloaded to:${NC}"
echo -e "   ${CYAN}$MODEL_DIR${NC}"
echo ""
echo -e "${CYAN}Downloaded models:${NC}"
for model in $MODELS_TO_DOWNLOAD; do
    echo -e "   • $model"
done

if [ "$FUNASR_AVAILABLE" = false ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Note: FunASR not fully installed${NC}"
    echo -e "${YELLOW}   Models are downloaded but local verification is skipped${NC}"
    echo -e "${YELLOW}   Models will work correctly in the bundled application${NC}"
fi

echo ""
echo -e "${GREEN}🎉 All done!${NC}"
