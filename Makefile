# EvoLoop Makefile
# 自动检测并使用正确的架构

.PHONY: dev setup clean arm64-setup

# 检测架构
ARCH := $(shell uname -m)

# 默认开发命令
dev:
ifeq ($(ARCH),x86_64)
	@echo "⚠️  当前终端是 x86_64 模式，切换到 ARM64..."
	@arch -arm64 zsh -c 'cd $(PWD) && $(MAKE) arm64-dev'
else
	@$(MAKE) arm64-dev
endif

# ARM64 原生开发命令
arm64-dev:
	@echo "✅ 当前架构: $(shell uname -m)"
	cd backend && ./bin/evo dev

# 设置 ARM64 环境
setup:
ifeq ($(ARCH),x86_64)
	@echo "⚠️  当前终端是 x86_64 模式，切换到 ARM64..."
	@arch -arm64 zsh -c 'cd $(PWD) && $(MAKE) arm64-setup'
else
	@$(MAKE) arm64-setup
endif

# 实际 ARM64 设置
arm64-setup:
	@echo "🔧 设置 ARM64 环境..."
	cd backend && rm -rf .venv uv.lock
	cd backend && uv venv
	cd backend && uv sync --no-dev
	@echo "✅ 环境设置完成！"

# 清理环境
clean:
	cd backend && rm -rf .venv uv.lock

# 强制使用 ARM64 Python
force-arm64:
	@echo "🔄 强制使用 ARM64 Python..."
	cd backend && rm -rf .venv
	arch -arm64 uv venv --python 3.11
	arch -arm64 uv sync --no-dev
