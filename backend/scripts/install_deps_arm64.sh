#!/bin/bash
# ARM64 (Apple Silicon) 依赖安装脚本

set -e

echo "🍎 检测到 ARM64 架构，开始安装依赖..."

# 设置环境变量确保使用 ARM64 架构
export ARCHFLAGS="-arch arm64"
export CMAKE_OSX_ARCHITECTURES="arm64"

# 1. 先升级 pip 和基础工具
echo "📦 升级 pip..."
pip install --upgrade pip setuptools wheel

# 2. 安装核心依赖（按依赖顺序）
echo "🔧 安装核心依赖..."

# 基础科学计算（ARM64 优化版）
pip install numpy --no-cache-dir

# LangChain 核心
pip install langchain-core>=1.2.7
pip install langchain>=1.2.3
pip install langchain-community>=0.4.1
pip install langchain-openai>=1.1.7
pip install langchain-anthropic>=1.3.1

# 3. 安装 tree-sitter（ARM64 原生编译）
echo "🌳 安装 tree-sitter..."
pip install tree-sitter>=0.23.0

# 4. 安装 tree-sitter 语言包（ARM64 兼容）
echo "📝 安装 tree-sitter 语言包..."
pip install tree-sitter-python>=0.21.0
pip install tree-sitter-javascript>=0.21.0
pip install tree-sitter-typescript>=0.21.0
pip install tree-sitter-go>=0.21.0
pip install tree-sitter-java>=0.21.0
pip install tree-sitter-cpp>=0.21.0
pip install tree-sitter-rust>=0.21.0
pip install tree-sitter-php>=0.21.0
pip install tree-sitter-ruby>=0.21.0
pip install tree-sitter-c-sharp>=0.21.0
pip install tree-sitter-kotlin>=1.1.0
pip install tree-sitter-swift>=0.0.1
pip install tree-sitter-sql>=0.3.11
pip install tree-sitter-html>=0.23.2
pip install tree-sitter-language-pack>=0.13.0

# 5. 安装其他缺失的核心依赖
echo "📚 安装其他核心依赖..."
pip install \
    fastapi[standard]>=0.114.2 \
    sqlmodel>=0.0.21 \
    alembic>=1.12.1 \
    pydantic>2.0 \
    pydantic-settings>=2.2.1 \
    httpx[http2]>=0.25.1 \
    python-multipart>=0.0.7 \
    email-validator>=2.1.0.post1 \
    passlib[bcrypt]>=1.7.4 \
    bcrypt==4.3.0 \
    tenacity>=8.2.3 \
    emails>=0.6 \
    jinja2>=3.1.4 \
    sentry-sdk[fastapi]>=1.40.6 \
    pyjwt>=2.8.0

# 6. 安装 AI/ML 相关依赖（ARM64 版本）
echo "🤖 安装 AI/ML 依赖..."
pip install \
    openai>=1.30.0 \
    anthropic>=0.25.0 \
    google-genai>=1.0.0

# 7. 安装嵌入式数据库（ARM64）
echo "💾 安装嵌入式数据库..."
pip install \
    aiosqlite>=0.20.0 \
    lancedb>=0.15.0,<0.26.0 \
    pyarrow>=15.0.0

# 8. 安装工具类依赖
echo "🛠️ 安装工具类依赖..."
pip install \
    watchdog>=4.0.0 \
    playwright>=1.40.0 \
    psutil>=5.9.0 \
    croniter>=6.0.0 \
    PyYAML>=6.0.1 \
    yamllint>=1.35.1 \
    websockets>=13.0,<15.0 \
    pathspec>=0.12.0 \
    pyright>=1.1.408 \
    requests>=2.32.5 \
    docker>=7.1.0 \
    rich>=13.0.0 \
    pandas>=2.2.0 \
    openpyxl>=3.1.2 \
    python-docx>=1.1.0 \
    pypdf>=4.0.0 \
    markdownify>=0.11.0 \
    mammoth>=1.6.0 \
    rapidfuzz>=3.14.3 \
    anytree>=2.12.0 \
    ddgs>=9.11.4

# 9. 安装 macOS 特定依赖（ARM64）
echo "🍏 安装 macOS ARM64 特定依赖..."
pip install \
    pyobjc>=12.1 \
    pyobjc-framework-quartz>=12.1 \
    pyobjc-framework-vision>=12.1 \
    imagehash>=4.3.2 \
    keyring>=25.0.0

echo "✅ ARM64 依赖安装完成！"
echo ""
echo "🧪 运行测试验证..."
cd "$(dirname "$0")"
python -m pytest tests/test_event_discovery.py -v --tb=short 2>&1 | tail -20
