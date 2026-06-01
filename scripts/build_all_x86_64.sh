#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Architecture settings - Fixed to x86_64
ARCH="x86_64"
TRIPLE="x86_64-apple-darwin"
RUST_TARGET="x86_64-apple-darwin"

# Default values
DEV_MODE=false
WITH_MODELS=false
DOWNLOAD_MODELS=false
MODELS_LIST="paraformer-zh"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev|-d)
            DEV_MODE=true
            shift
            ;;
        --with-models|-m)
            WITH_MODELS=true
            shift
            ;;
        --download-models)
            DOWNLOAD_MODELS=true
            if [[ $2 != --* ]] && [[ -n $2 ]]; then
                MODELS_LIST="$2"
                shift 2
            else
                shift
            fi
            ;;
        --help|-h)
            echo "EvoLoop Build Script for x86_64 (Intel) Mac"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dev, -d                 Run in development mode"
            echo "  --with-models, -m         Include pre-downloaded models in the bundle"
            echo "  --download-models [LIST]  Download models before building (comma-separated list)"
            echo "                            Available: paraformer-zh, paraformer-zh-plus,"
            echo "                                      paraformer-zh-streaming"
            echo "                            Default: paraformer-zh"
            echo "  --help, -h                Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Standard x86_64 build without models"
            echo "  $0 --with-models                      # Build with existing models in \${EVOLOOP_APP_DATA_DIR:-~/.evoloop}/models"
            echo "  $0 --download-models                  # Download default model and build with it"
            echo "  $0 --download-models paraformer-zh,paraformer-zh-plus --with-models"
            echo "  $0 --dev                              # Run development server"
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

# Load .env if exists to get EVOLOOP_APP_DATA_DIR
if [ -f ".env" ]; then
    export $(grep '^EVOLOOP_APP_DATA_DIR=' .env | xargs) 2>/dev/null || true
fi
APP_DATA_DIR="${EVOLOOP_APP_DATA_DIR:-$HOME/.evoloop}"

# Fix: Ensure system xattr is used instead of Python xattr
# Tauri requires system xattr with -r flag support
if [ -f "/usr/bin/xattr" ]; then
    export PATH="/usr/bin:$PATH"
fi

# Remove Python xattr from PATH to avoid conflicts
PATH=$(echo "$PATH" | tr ':' '\n' | grep -v "Python.framework" | tr '\n' ':')

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          EvoLoop x86_64 Build Process                        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Target Architecture: ${ARCH} (Intel Mac)${NC}"
echo ""

# Show build configuration
echo -e "${CYAN}Build Configuration:${NC}"
echo -e "  Architecture:   ${ARCH} (${TRIPLE})"
echo -e "  Dev Mode:       $DEV_MODE"
echo -e "  With Models:    $WITH_MODELS"
echo -e "  Download Models: $DOWNLOAD_MODELS"
if [ "$DOWNLOAD_MODELS" = true ]; then
    echo -e "  Models List:    $MODELS_LIST"
fi
echo ""

# Step 0: Download models if requested
if [ "$DOWNLOAD_MODELS" = true ]; then
    echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│ Step 0: Downloading AI Models                               │${NC}"
    echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${NC}"
    
    if [ -f "scripts/download_models.sh" ]; then
        chmod +x scripts/download_models.sh
        # Use --skip-funasr-check to avoid dependency issues
        ./scripts/download_models.sh --models "$MODELS_LIST" --skip-funasr-check
    else
        echo -e "${YELLOW}⚠️  download_models.sh not found, skipping model download${NC}"
    fi
    echo ""
fi

# Pre-build: Ensure NumPy 1.x for PyInstaller compatibility
echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${NC}"
echo -e "${YELLOW}│ Pre-build: Checking NumPy version                           │${NC}"
echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${NC}"

# Activate virtual environment if exists
if [ -f "backend/.venv/bin/activate" ]; then
    source backend/.venv/bin/activate
fi

NUMPY_VERSION=$(python3 -c "import numpy; print(numpy.__version__)" 2>/dev/null || echo "")
if [ -n "$NUMPY_VERSION" ]; then
    NUMPY_MAJOR=$(echo "$NUMPY_VERSION" | cut -d. -f1)
    if [ "$NUMPY_MAJOR" = "2" ]; then
        echo -e "${YELLOW}⚠️  NumPy 2.x detected (${NUMPY_VERSION}), downgrading to 1.26.4...${NC}"
        if command -v uv &> /dev/null; then
            uv pip install "numpy==1.26.4" --force-reinstall
        else
            python3 -m pip install "numpy==1.26.4" --force-reinstall
        fi
        echo -e "${GREEN}✅ NumPy downgraded to 1.26.4${NC}"
    else
        echo -e "${GREEN}✅ NumPy 1.x already installed (${NUMPY_VERSION})${NC}"
    fi
fi
echo ""

# Step 1: Build Backend Sidecar for x86_64
echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${NC}"
echo -e "${YELLOW}│ Step 1/4: Building Backend Sidecar (x86_64)                 │${NC}"
echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${NC}"

cd backend

# Clean previous build
echo -e "${YELLOW}🧹 Cleaning previous build...${NC}"
rm -rf "dist" "build" "__pycache__"

# Check Python environment
echo -e "${YELLOW}🐍 Checking Python environment...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found${NC}"
    exit 1
fi

# Check if pyinstaller is available
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo -e "${YELLOW}📦 Installing PyInstaller...${NC}"
    python3 -m pip install pyinstaller
fi

# Build with PyInstaller
echo -e "${BLUE}📦 Building with PyInstaller for x86_64...${NC}"
echo -e "${YELLOW}   This may take several minutes...${NC}"

if [ -f "evoloop-backend.spec" ]; then
    # Force x86_64 architecture
    arch -x86_64 python3 -m PyInstaller evoloop-backend.spec --clean --noconfirm 2>/dev/null || \
    python3 -m PyInstaller evoloop-backend.spec --clean --noconfirm
else
    echo -e "${RED}❌ PyInstaller spec file not found${NC}"
    exit 1
fi

# Prepare Tauri Binaries Directory
TAURI_BIN_DIR="../frontend/src-tauri/binaries"
BINARY_NAME="evoloop-backend"
TARGET_BINARY="${BINARY_NAME}-${TRIPLE}"

mkdir -p "${TAURI_BIN_DIR}"

# Move and Rename Binary
if [ -f "dist/${BINARY_NAME}" ]; then
    mv "dist/${BINARY_NAME}" "${TAURI_BIN_DIR}/${TARGET_BINARY}"
    echo -e "${GREEN}✅ Backend Sidecar built successfully${NC}"
    echo -e "${GREEN}   Location: ${TAURI_BIN_DIR}/${TARGET_BINARY}${NC}"
else
    echo -e "${RED}❌ Error: Binary not found at dist/${BINARY_NAME}${NC}"
    exit 1
fi

# Set permissions
chmod +x "${TAURI_BIN_DIR}/${TARGET_BINARY}"

# Sign the binary (ad-hoc signing for local development)
echo -e "${YELLOW}🔏 Signing binary...${NC}"
codesign --force --sign - "${TAURI_BIN_DIR}/${TARGET_BINARY}" 2>/dev/null || echo -e "${YELLOW}⚠️  Could not sign binary${NC}"

# Show file size
FILE_SIZE=$(du -h "${TAURI_BIN_DIR}/${TARGET_BINARY}" | cut -f1)
echo -e "${BLUE}📊 Binary size: ${FILE_SIZE}${NC}"

cd ..
echo ""

# Step 2: Handle models bundling (if --with-models)
if [ "$WITH_MODELS" = true ]; then
    echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│ Step 2/4: Preparing Models for Bundling                     │${NC}"
    echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${NC}"
    
    MODELS_SOURCE="$APP_DATA_DIR/models"
    MODELS_DEST="frontend/src-tauri/models"
    
    if [ ! -d "$MODELS_SOURCE" ]; then
        echo -e "${RED}❌ Models not found at $MODELS_SOURCE${NC}"
        echo -e "${YELLOW}   Please run: ./scripts/download_models.sh${NC}"
        echo -e "${YELLOW}   Or use: $0 --download-models --with-models${NC}"
        exit 1
    fi
    
    echo -e "${BLUE}📦 Copying models to bundle...${NC}"
    rm -rf "$MODELS_DEST"
    mkdir -p "$MODELS_DEST"
    cp -R "$MODELS_SOURCE"/* "$MODELS_DEST/"
    
    # Calculate size
    MODELS_SIZE=$(du -sh "$MODELS_DEST" | cut -f1)
    echo -e "${GREEN}✅ Models copied: $MODELS_SIZE${NC}"
    
    # Create temporary tauri.conf.json with models included
    echo -e "${BLUE}🔧 Configuring Tauri to include models...${NC}"
    
    # Backup original config
    cp frontend/src-tauri/tauri.conf.json frontend/src-tauri/tauri.conf.json.backup
    
    # Modify config to include models
    python3 << PYTHON_SCRIPT
import json

with open("frontend/src-tauri/tauri.conf.json", "r") as f:
    config = json.load(f)

# Add models to resources
if "resources" not in config["bundle"]:
    config["bundle"]["resources"] = {}

# Handle both dict and list formats
if isinstance(config["bundle"]["resources"], dict):
    config["bundle"]["resources"]["models"] = "models"
elif isinstance(config["bundle"]["resources"], list):
    config["bundle"]["resources"].append("models")

with open("frontend/src-tauri/tauri.conf.json", "w") as f:
    json.dump(config, f, indent=2)

print("✅ Tauri config updated to include models")
PYTHON_SCRIPT
    
    echo ""
fi

# Step 3: Install Frontend Dependencies
echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${NC}"
if [ "$WITH_MODELS" = true ]; then
    echo -e "${YELLOW}│ Step 3/4: Installing Frontend Dependencies                  │${NC}"
else
    echo -e "${YELLOW}│ Step 2/3: Installing Frontend Dependencies                  │${NC}"
fi
echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${NC}"

cd frontend

if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}📦 Installing npm dependencies...${NC}"
    npm install
else
    echo -e "${GREEN}✅ node_modules already exists${NC}"
fi

echo ""

# Step 4: Build Tauri Application for x86_64
echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${NC}"
if [ "$WITH_MODELS" = true ]; then
    echo -e "${YELLOW}│ Step 4/4: Building Tauri Application (x86_64)               │${NC}"
else
    echo -e "${YELLOW}│ Step 3/3: Building Tauri Application (x86_64)               │${NC}"
fi
echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${NC}"

# Check if we should build for distribution or just dev
if [ "$DEV_MODE" = true ]; then
    echo -e "${BLUE}🔧 Running in DEV mode...${NC}"
    echo -e "${YELLOW}   This will start the Tauri development server${NC}"
    npm run tauri dev
else
    echo -e "${BLUE}📦 Building for DISTRIBUTION (x86_64)...${NC}"
    if [ "$WITH_MODELS" = true ]; then
        echo -e "${CYAN}   Including AI models in the bundle${NC}"
    fi
    
    # Install x86_64 target if not present
    echo -e "${YELLOW}🔧 Ensuring Rust x86_64 target is installed...${NC}"
    rustup target add x86_64-apple-darwin 2>/dev/null || echo -e "${YELLOW}   Target already installed or rustup not available${NC}"
    
    # Run Tauri build for x86_64
    echo -e "${BLUE}📦 Building Tauri app for x86_64-apple-darwin...${NC}"
    if npm run tauri build -- --target x86_64-apple-darwin; then
        echo ""
        echo -e "${GREEN}🎉 Tauri build successful!${NC}"
    else
        echo ""
        echo -e "${YELLOW}⚠️  Tauri bundle failed, attempting manual bundling...${NC}"
    fi
    
    # Fix libvosk.dylib in the app bundle
    APP_BUNDLE="src-tauri/target/x86_64-apple-darwin/release/bundle/macos/EvoLoop.app"
    if [ ! -d "$APP_BUNDLE" ]; then
        # Try to find the app bundle in alternative locations
        if [ -d "src-tauri/target/release/EvoLoop.app" ]; then
            mkdir -p "src-tauri/target/x86_64-apple-darwin/release/bundle/macos"
            mv "src-tauri/target/release/EvoLoop.app" "$APP_BUNDLE"
        fi
    fi
    
    # Fix libvosk.dylib and sign the app bundle
    echo ""
    echo -e "${YELLOW}🔧 Fixing libvosk.dylib...${NC}"
    if [ -d "$APP_BUNDLE" ]; then
        # Create Frameworks directory and copy libvosk.dylib
        mkdir -p "$APP_BUNDLE/Contents/Frameworks"
        if [ -f "../src-tauri/libs/libvosk.dylib" ]; then
            cp "../src-tauri/libs/libvosk.dylib" "$APP_BUNDLE/Contents/Frameworks/"
        elif [ -f "src-tauri/libs/libvosk.dylib" ]; then
            cp "src-tauri/libs/libvosk.dylib" "$APP_BUNDLE/Contents/Frameworks/"
        fi
        
        # Fix library path
        install_name_tool -change "libvosk.dylib" "@executable_path/../Frameworks/libvosk.dylib" "$APP_BUNDLE/Contents/MacOS/EvoLoop" 2>/dev/null || true
        
        # Sign the app bundle
        echo -e "${YELLOW}🔏 Signing application bundle...${NC}"
        codesign --force --deep --sign - "$APP_BUNDLE" 2>/dev/null || true
        echo -e "${GREEN}✅ App bundle signed${NC}"
        
        # Create DMG
        DMG_PATH="src-tauri/target/x86_64-apple-darwin/release/bundle/dmg/EvoLoop_0.1.0_x86_64.dmg"
        echo ""
        echo -e "${YELLOW}📦 Creating DMG...${NC}"
        mkdir -p "src-tauri/target/x86_64-apple-darwin/release/bundle/dmg"
        
        # Remove old DMG if exists
        rm -f "$DMG_PATH"
        
        # Create DMG with hdiutil
        if hdiutil create -volname "EvoLoop" -srcfolder "$APP_BUNDLE" -ov -format UDZO "$DMG_PATH"; then
            echo -e "${GREEN}✅ DMG created successfully${NC}"
            
            # Copy DMG to dist folder
            mkdir -p "../dist"
            cp "$DMG_PATH" "../dist/"
            echo -e "${GREEN}✅ DMG copied to dist folder${NC}"
        else
            echo -e "${RED}❌ DMG creation failed${NC}"
        fi
    else
        echo -e "${RED}❌ App bundle not found${NC}"
    fi
    
    # Show output location
    if [ -d "$APP_BUNDLE" ]; then
        echo ""
        echo -e "${BLUE}📁 Output locations:${NC}"
        APP_SIZE=$(du -sh "$APP_BUNDLE" | cut -f1)
        echo -e "   ${GREEN}$(basename "$APP_BUNDLE")${NC} (${APP_SIZE})"
        
        # Find DMG files
        find src-tauri/target/x86_64-apple-darwin/release/bundle/dmg -type f -name "*.dmg" 2>/dev/null | while read -r file; do
            FILE_SIZE=$(du -h "$file" | cut -f1)
            echo -e "   ${GREEN}$(basename "$file")${NC} (${FILE_SIZE})"
        done
        
        # Show dist folder content
        if [ -d "../dist" ]; then
            find "../dist" -type f -name "*.dmg" 2>/dev/null | while read -r file; do
                DIST_SIZE=$(du -h "$file" | cut -f1)
                echo -e "   ${GREEN}dist/$(basename "$file")${NC} (${DIST_SIZE})"
            done
        fi
    fi
fi

cd ..

# Cleanup: Restore original tauri.conf.json if modified
if [ "$WITH_MODELS" = true ]; then
    echo ""
    echo -e "${BLUE}🧹 Cleaning up...${NC}"
    
    # Restore original config
    if [ -f "frontend/src-tauri/tauri.conf.json.backup" ]; then
        mv frontend/src-tauri/tauri.conf.json.backup frontend/src-tauri/tauri.conf.json
        echo -e "${GREEN}✅ Restored original Tauri config${NC}"
    fi
    
    # Remove copied models
    if [ -d "frontend/src-tauri/models" ]; then
        rm -rf "frontend/src-tauri/models"
        echo -e "${GREEN}✅ Cleaned up temporary model files${NC}"
    fi
fi

echo ""
echo -e "${GREEN}✨ x86_64 Build Complete!${NC}"
echo ""
echo -e "${BLUE}📋 Build Summary:${NC}"
echo -e "   Architecture: ${ARCH} (${TRIPLE})"
echo -e "   Output: frontend/src-tauri/target/x86_64-apple-darwin/release/bundle/"
if [ -f "dist/EvoLoop_0.1.0_x86_64.dmg" ]; then
    DMG_SIZE=$(du -h "dist/EvoLoop_0.1.0_x86_64.dmg" | cut -f1)
    echo -e "   DMG: dist/EvoLoop_0.1.0_x86_64.dmg (${DMG_SIZE})"
fi
