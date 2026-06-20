# =============================================================================
# EvoLoop Build Configuration — 单一配置源
# =============================================================================
# 修改此处值后，需重新构建 sidecar 和 DMG 才能生效。
# Rust sidecar 和 Python entry point 也读取此值（通过环境变量）。
# =============================================================================

# 后端服务端口（桌面端本地 sidecar 监听端口）
BACKEND_PORT=20160

# 桌面端前端 API URL（基于 BACKEND_PORT 生成）
VITE_API_URL="http://127.0.0.1:${BACKEND_PORT}"

# Rust 编译目标架构
ARCH="${ARCH:-aarch64-apple-darwin}"

# =============================================================================
# Rsync 排除列表 (多脚本共享)
# =============================================================================
EXCLUDE_RSYNC=(
  --exclude='mobile'
  --exclude='frontend/src-tauri'
  --exclude='frontend/node_modules'
  --exclude='backend/.venv'
  --exclude='frontend/dist'
  --exclude='backend/dist'
  --exclude='backend/build'
  --exclude='backend/evoloop-backend.spec'
  --exclude='backend/entry_point.py'
  --exclude='dist'
  --exclude='Makefile'
  --exclude='.git'
  --exclude='.gitignore'
  --exclude='.pre-commit-config.yaml'
  --exclude='deploy/build'
  --exclude='deploy/dev.sh'
  --exclude='deploy/check_arch.sh'
  --exclude='deploy/update-version.sh'
  --exclude='deploy/generate-client.sh'
  --exclude='deploy/install_funasr.sh'
  --exclude='frontend/playwright.config.ts'
  --exclude='frontend/vitest.config.ts'
  --exclude='.mypy_cache'
  --exclude='__pycache__'
  --exclude='.pytest_cache'
  --exclude='.ruff_cache'
  --exclude='*.pyc'
  --exclude='backend/node_modules'
  --exclude='node_modules'
)
