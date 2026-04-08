#!/bin/bash
# 强制使用 ARM64 架构启动

echo "🍎 强制使用 ARM64 架构..."

# 使用 arch -arm64 强制 ARM64 模式
arch -arm64 /bin/bash -c '
    cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
    
    # 创建 ARM64 虚拟环境
    rm -rf .venv
    arch -arm64 python3.11 -m venv .venv
    source .venv/bin/activate
    
    # 验证架构
    echo "Python 架构:"
    file $(which python)
    
    # 安装依赖
    pip install --upgrade pip
    pip install pydantic-core pydantic fastapi uvicorn
    
    # 验证
    python -c "import pydantic_core; print(f\"✅ pydantic-core {pydantic_core.__version__} (ARM64) 导入成功\")"
    
    # 启动服务器
    ./bin/evo dev
'
