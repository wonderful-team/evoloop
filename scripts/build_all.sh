#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

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
            echo "EvoLoop Build Script"
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
            echo "  $0                                    # Standard build without models"
            echo "  $0 --with-models                      # Build with existing models in ~/.evoloop/models"
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

# Fix: Ensure system xattr is used instead of Python xattr
# Tauri requires system xattr with -r flag support
if [ -f "/usr/bin/xattr" ]; then
    export PATH="/usr/bin:$PATH"
fi

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          EvoLoop Complete Build Process                      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Show build configuration
echo -e "${CYAN}Build Configuration:${NC}"
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
        # Use --skip-funasr-check to avoid dependency issues on Apple Silicon
        ./scripts/download_models.sh --models "$MODELS_LIST" --skip-funasr-check
    else
        echo -e "${RED}❌ download_models.sh not found${NC}"
        exit 1
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

# Step 1: Build Backend Sidecar
echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${NC}"
echo -e "${YELLOW}│ Step 1/4: Building Backend Sidecar                          │${NC}"
echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${NC}"

if [ -f "scripts/build_sidecar.sh" ]; then
    chmod +x scripts/build_sidecar.sh
    ./scripts/build_sidecar.sh
else
    echo -e "${RED}❌ build_sidecar.sh not found${NC}"
    exit 1
fi

echo ""

# Step 2: Handle models bundling (if --with-models)
if [ "$WITH_MODELS" = true ]; then
    echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│ Step 2/4: Preparing Models for Bundling                     │${NC}"
    echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${NC}"
    
    MODELS_SOURCE="$HOME/.evoloop/models"
    MODELS_DEST="frontend/src-tauri/models"
    
    if [ ! -d "$MODELS_SOURCE" ]; then
        echo -e "${RED}❌ Models not found at $MODELS_SOURCE${NC}"
        echo -e "${YELLOW}   Please run: ./scripts/download_models.sh${NC}"
        echo -e "${YELLOW}   Or use: ./scripts/build_all.sh --download-models --with-models${NC}"
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

# Step 4: Build Tauri Application
echo -e "${YELLOW}┌─────────────────────────────────────────────────────────────┐${NC}"
if [ "$WITH_MODELS" = true ]; then
    echo -e "${YELLOW}│ Step 4/4: Building Tauri Application                        │${NC}"
else
    echo -e "${YELLOW}│ Step 3/3: Building Tauri Application                        │${NC}"
fi
echo -e "${YELLOW}└─────────────────────────────────────────────────────────────┘${NC}"

# Check if we should build for distribution or just dev
if [ "$DEV_MODE" = true ]; then
    echo -e "${BLUE}🔧 Running in DEV mode...${NC}"
    echo -e "${YELLOW}   This will start the Tauri development server${NC}"
    npm run tauri dev
else
    echo -e "${BLUE}📦 Building for DISTRIBUTION...${NC}"
    if [ "$WITH_MODELS" = true ]; then
        echo -e "${CYAN}   Including AI models in the bundle${NC}"
    fi
    # Run Tauri build for arm64, but handle bundle failures gracefully
    if npm run tauri build -- --target aarch64-apple-darwin; then
        echo ""
        echo -e "${GREEN}🎉 Tauri build successful!${NC}"
    else
        echo ""
        echo -e "${YELLOW}⚠️  Tauri bundle failed, attempting manual bundling...${NC}"
    fi
    
    # Fix libvosk.dylib in the app bundle
    APP_BUNDLE="src-tauri/target/aarch64-apple-darwin/release/bundle/macos/EvoLoop.app"
    if [ ! -d "$APP_BUNDLE" ]; then
        # Try to find the app bundle in alternative locations
        if [ -d "src-tauri/target/release/EvoLoop.app" ]; then
            mkdir -p "src-tauri/target/release/bundle/macos"
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
        
        # Create DMG manually if it doesn't exist
        DMG_PATH="src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/EvoLoop_0.1.0_aarch64.dmg"
        if [ ! -f "$DMG_PATH" ]; then
            echo ""
            echo -e "${YELLOW}📦 Creating DMG...${NC}"
            mkdir -p "src-tauri/target/aarch64-apple-darwin/release/bundle/dmg"
            hdiutil create -volname "EvoLoop" -srcfolder "$APP_BUNDLE" -ov -format UDZO "$DMG_PATH" 2>/dev/null || {
                echo -e "${YELLOW}⚠️  DMG creation may have issues, but app is ready${NC}"
            }
            if [ -f "$DMG_PATH" ]; then
                echo -e "${GREEN}✅ DMG created${NC}"
            fi
        fi
        
        # Copy DMG to dist folder
        if [ -f "$DMG_PATH" ]; then
            mkdir -p "../dist"
            cp "$DMG_PATH" "../dist/"
            echo -e "${GREEN}✅ DMG copied to dist folder${NC}"
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
        find src-tauri/target/aarch64-apple-darwin/release/bundle/dmg -type f -name "*.dmg" 2>/dev/null | while read -r file; do
            FILE_SIZE=$(du -h "$file" | cut -f1)
            echo -e "   ${GREEN}$(basename "$file")${NC} (${FILE_SIZE})"
        done
        if [ -f "../dist/$(basename "$DMG_PATH")" ]; then
            DIST_SIZE=$(du -h "../dist/$(basename "$DMG_PATH")" | cut -f1)
            echo -e "   ${GREEN}dist/$(basename "$DMG_PATH")${NC} (${DIST_SIZE})"
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
echo -e "${GREEN}✨ All Done!${NC}"
