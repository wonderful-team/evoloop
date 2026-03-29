#!/bin/bash
set -e

# Build script with pre-downloaded models
# This is a convenience wrapper around build_all.sh with --download-models and --with-models

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default models
MODELS="paraformer-zh"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --all|-a)
            MODELS="paraformer-zh,paraformer-zh-plus,paraformer-zh-streaming"
            shift
            ;;
        --models|-m)
            MODELS="$2"
            shift 2
            ;;
        --help|-h)
            echo "Build EvoLoop with AI Models bundled"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --all, -a           Download and bundle all available models (~1.2GB)"
            echo "  --models, -m LIST   Specify models to bundle (comma-separated)"
            echo "                      Available: paraformer-zh, paraformer-zh-plus,"
            echo "                                paraformer-zh-streaming"
            echo "  --help, -h          Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                          # Bundle default model (paraformer-zh, ~220MB)"
            echo "  $0 --all                    # Bundle all models (~1.2GB)"
            echo "  $0 --models paraformer-zh,paraformer-zh-plus"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Get project root
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  EvoLoop Build with AI Models${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Models to bundle: ${MODELS}${NC}"
echo ""

# Run the main build script with appropriate flags
exec "${PROJECT_ROOT}/scripts/build_all.sh" --download-models "$MODELS" --with-models
