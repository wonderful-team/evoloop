# ARM64 环境设置指南

## 问题
当前终端在 Rosetta (x86_64) 模式下运行，导致：
- Python 是 x86_64
- uv 是 x86_64
- 所有安装的包默认是 x86_64

## 解决方案

### 方法 1: 使用原生 ARM64 终端（推荐）

1. 关闭当前终端
2. 在 Finder 中右键点击终端应用 → 获取信息 → 取消勾选 "使用 Rosetta 打开"
3. 打开新终端
4. 验证架构：`uname -m` 应该显示 `arm64`
5. 运行：
   ```bash
   cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
   rm -rf .venv
   uv venv
   source .venv/bin/activate
   uv pip install -e .
   ./bin/evo dev
   ```

### 方法 2: 使用 Conda（无需更改终端）

```bash
# 安装 Miniconda (ARM64)
curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh
bash Miniconda3-latest-MacOSX-arm64.sh

# 创建 ARM64 环境
conda create -n evoloop python=3.11
conda activate evoloop

# 安装依赖
pip install -e .
./bin/evo dev
```

### 方法 3: 接受 x86_64（最快但性能略低）

如果不需要 ARM64 原生性能，可以直接使用当前 x86_64 环境：

```bash
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
./bin/evo dev
```

Rosetta 2 的性能损失约为 20%，大部分情况下可以接受。

## 验证 ARM64 架构

```bash
# 终端架构
uname -m  # 应显示 arm64

# Python 架构
python -c "import platform; print(platform.machine())"  # 应显示 arm64

# 包架构
file .venv/lib/python*/site-packages/pydantic_core/*.so  # 应显示 arm64
```
