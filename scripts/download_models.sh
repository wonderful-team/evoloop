#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default models to download
DEFAULT_MODELS="paraformer-zh"
ALL_MODELS="paraformer-zh paraformer-zh-plus paraformer-zh-streaming"

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
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Download FunASR models for STT (Speech-to-Text)"
            echo ""
            echo "Options:"
            echo "  --all, -a              Download all available models"
            echo "  --models, -m           Specify models to download (comma-separated)"
            echo "                         Available: paraformer-zh, paraformer-zh-plus,"
            echo "                                   paraformer-zh-streaming"
            echo "  --skip-funasr-check    Skip FunASR dependency check (use modelscope only)"
            echo "  --help, -h             Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                          # Download default model (paraformer-zh)"
            echo "  $0 --all                    # Download all models (~1.2GB)"
            echo "  $0 --models paraformer-zh,paraformer-zh-plus"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Get project root
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

# Check if running in backend directory
if [ -f "pyproject.toml" ]; then
    BACKEND_DIR="."
elif [ -f "backend/pyproject.toml" ]; then
    cd backend
    BACKEND_DIR="."
else
    echo -e "${RED}❌ Could not find backend directory${NC}"
    exit 1
fi

# Activate virtual environment if exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo -e "${CYAN}🔧 Activated virtual environment${NC}"
elif [ -f "../backend/.venv/bin/activate" ]; then
    source ../backend/.venv/bin/activate
    echo -e "${CYAN}🔧 Activated virtual environment${NC}"
fi

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          EvoLoop Model Download                              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Determine which models to download
if [ "$DOWNLOAD_ALL" = true ]; then
    MODELS_TO_DOWNLOAD="$ALL_MODELS"
elif [ -z "$MODELS_TO_DOWNLOAD" ]; then
    MODELS_TO_DOWNLOAD="$DEFAULT_MODELS"
fi

# Convert comma-separated to space-separated
MODELS_TO_DOWNLOAD=$(echo "$MODELS_TO_DOWNLOAD" | tr ',' ' ')

echo -e "${BLUE}📦 Models to download: ${MODELS_TO_DOWNLOAD}${NC}"
echo ""

# Check Python environment
echo -e "${YELLOW}🐍 Checking Python environment...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found${NC}"
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
PYTHON_ARCH=$(python3 -c "import platform; print(platform.machine())")
if [ "$PYTHON_ARCH" = "arm64" ]; then
    echo -e "${GREEN}✅ Python is running natively on Apple Silicon${NC}"
elif [ "$IS_APPLE_SILICON" = true ]; then
    echo -e "${YELLOW}⚠️  Python is running under Rosetta (x86_64)${NC}"
    echo -e "${YELLOW}   This may cause compatibility issues with some packages${NC}"
fi

# Install modelscope first (required for downloading)
echo ""
echo -e "${YELLOW}📦 Checking dependencies...${NC}"

# Function to install package with fallback
install_package() {
    local pkg=$1
    if command -v uv &> /dev/null; then
        # Try with pre-built wheels first
        uv pip install --only-binary :all: "$pkg" 2>/dev/null || \
            uv pip install "$pkg"
    else
        pip install --only-binary :all: "$pkg" 2>/dev/null || \
            pip install "$pkg"
    fi
}

# Check NumPy version (modelscope and torch require NumPy 1.x)
echo -e "${YELLOW}🔍 Checking NumPy version...${NC}"
NUMPY_VERSION=$(python3 -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "")
if [ -n "$NUMPY_VERSION" ]; then
    NUMPY_MAJOR=$(echo "$NUMPY_VERSION" | cut -d. -f1)
    if [ "$NUMPY_MAJOR" = "2" ]; then
        echo -e "${YELLOW}⚠️  NumPy 2.x detected, downgrading to 1.26.4...${NC}"
        if command -v uv &> /dev/null; then
            uv pip install "numpy==1.26.4" --force-reinstall -q
        else
            pip install "numpy==1.26.4" --force-reinstall -q
        fi
        echo -e "${GREEN}✅ NumPy downgraded to 1.26.4${NC}"
    else
        echo -e "${GREEN}✅ NumPy 1.x already installed (${NUMPY_VERSION})${NC}"
    fi
else
    echo -e "${YELLOW}📦 Installing NumPy 1.26.4...${NC}"
    install_package "numpy==1.26.4"
fi

# Install modelscope (lightweight, no heavy dependencies)
if ! python3 -c "import modelscope" 2>/dev/null; then
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
    if ! python3 -c "import funasr" 2>/dev/null; then
        echo -e "${YELLOW}📦 Installing FunASR (optional, for model verification)...${NC}"
        echo -e "${CYAN}   Note: This may take a while on Apple Silicon${NC}"
        
        # Try to install funasr with torch
        if command -v uv &> /dev/null; then
            # For Apple Silicon, try to avoid building llvmlite from source
            if [ "$IS_APPLE_SILICON" = true ]; then
                echo -e "${CYAN}   Attempting Apple Silicon optimized install...${NC}"
                # Install without funasr's heavy dependencies first
                uv pip install torch torchaudio 2>/dev/null || true
            fi
            
            # Try funasr installation (may fail on llvmlite, that's OK)
            uv pip install funasr 2>/dev/null && FUNASR_AVAILABLE=true || {
                echo -e "${YELLOW}⚠️  FunASR installation incomplete (this is OK for downloading)${NC}"
                if [ "$IS_APPLE_SILICON" = true ]; then
                    echo ""
                    echo -e "${CYAN}💡 To use FunASR on Apple Silicon, you have options:${NC}"
                    echo -e "   1. Use conda: conda install -c conda-forge numba llvmlite"
                    echo -e "   2. Use Rosetta Python: arch -x86_64 python3 -m pip install funasr"
                    echo -e "   3. Download models only (models will work when bundled)"
                fi
            }
        else
            pip install funasr 2>/dev/null && FUNASR_AVAILABLE=true || {
                echo -e "${YELLOW}⚠️  FunASR installation incomplete (this is OK for downloading)${NC}"
            }
        fi
    else
        FUNASR_AVAILABLE=true
        echo -e "${GREEN}✅ FunASR already installed${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Skipping FunASR check (--skip-funasr-check)${NC}"
fi

echo ""

# Create models directory
MODELS_DIR="${MODELS_DIR:-$HOME/.evoloop/models}"
mkdir -p "$MODELS_DIR"
echo -e "${BLUE}📁 Models will be saved to: $MODELS_DIR${NC}"
echo ""

# Clean up stale lock files from previous interrupted downloads
echo -e "${YELLOW}🧹 Cleaning up stale lock files...${NC}"
rm -rf "$MODELS_DIR/.lock" 2>/dev/null || true
rm -rf "$MODELS_DIR/._____temp" 2>/dev/null || true
# Also kill any hanging modelscope processes
pkill -f "snapshot_download" 2>/dev/null || true
echo -e "${GREEN}✅ Cleanup complete${NC}"
echo ""

# Download models
echo -e "${YELLOW}⬇️  Downloading models...${NC}"
echo ""

python3 << PYTHON_SCRIPT
import os
import sys

# Set ModelScope cache directory
os.environ["MODELSCOPE_CACHE"] = "$MODELS_DIR"

try:
    from modelscope import snapshot_download
except ImportError as e:
    print(f"❌ Failed to import modelscope: {e}")
    sys.exit(1)

# Model mapping
MODEL_MAP = {
    "paraformer-zh": "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "paraformer-zh-plus": "damo/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    "paraformer-zh-streaming": "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
    "paraformer-zh-en": "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
}

MODEL_SIZES = {
    "paraformer-zh": "~220MB",
    "paraformer-zh-plus": "~500MB",
    "paraformer-zh-streaming": "~220MB",
    "paraformer-zh-en": "~220MB",
}

models_to_download = "$MODELS_TO_DOWNLOAD".split()
success = []
failed = []

for model_name in models_to_download:
    model_name = model_name.strip()
    if model_name not in MODEL_MAP:
        print(f"⚠️  Unknown model: {model_name}, skipping...")
        continue
    
    model_id = MODEL_MAP[model_name]
    size = MODEL_SIZES.get(model_name, "unknown size")
    
    print(f"⬇️  Downloading {model_name} ({size})...")
    print(f"   Model ID: {model_id}")
    
    try:
        cache_dir = snapshot_download(model_id, cache_dir="$MODELS_DIR")
        print(f"   ✅ Saved to: {cache_dir}")
        success.append(model_name)
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        failed.append(model_name)

print("")
print("=" * 60)
print("Download Summary:")
print("=" * 60)
if success:
    print(f"✅ Successfully downloaded: {', '.join(success)}")
if failed:
    print(f"❌ Failed to download: {', '.join(failed)}")
    sys.exit(1)

print("")
print(f"📁 All models are stored in: $MODELS_DIR")

# Verify with funasr if available
FUNASR_AVAILABLE = "$FUNASR_AVAILABLE"
FUNASR_AVAILABLE = FUNASR_AVAILABLE == "true"
if FUNASR_AVAILABLE:
    print("")
    print("🔍 Verifying models with FunASR...")
    try:
        from funasr import AutoModel
        for model_name in success:
            model_id = MODEL_MAP[model_name]
            model_path = os.path.join("$MODELS_DIR", "hub", model_id)
            if os.path.exists(model_path):
                print(f"   ✅ {model_name}: Found at {model_path}")
    except Exception as e:
        print(f"   ⚠️  Verification skipped: {e}")
else:
    print("")
    print("💡 Models downloaded successfully!")
    print("   FunASR not available for verification, but models are ready for bundling.")
PYTHON_SCRIPT

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}🎉 All models downloaded successfully!${NC}"
    echo ""
    echo -e "${BLUE}💡 Next steps:${NC}"
    echo "   1. Run './scripts/build_all.sh --with-models' to include models in the bundle"
    echo "   2. Or models will be downloaded automatically on first use"
    echo ""
    
    if [ "$FUNASR_AVAILABLE" = false ] && [ "$IS_APPLE_SILICON" = true ]; then
        echo -e "${CYAN}🍎 Apple Silicon Notes:${NC}"
        echo "   Models are downloaded and ready for bundling."
        echo "   When bundled with the app, they will work without requiring FunASR"
        echo "   to be installed on the build machine."
        echo ""
        echo -e "   To use FunASR locally (for development):"
        echo "     conda install -c conda-forge numba llvmlite"
        echo "     uv pip install funasr"
    fi
else
    echo ""
    echo -e "${RED}❌ Some models failed to download${NC}"
    exit 1
fi
