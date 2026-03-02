# EvoLoop 一键安装与部署指南

## 概述

EvoLoop 支持三种一键安装方式，覆盖不同使用场景：

1. **桌面版** - 面向个人用户（双击安装）
2. **服务器版** - 面向团队/运维（一条命令部署）
3. **开发版** - 面向开发者（环境一键配置）

---

## 一、服务器一键部署（推荐）

### 快速开始

```bash
# 方式 1: curl
curl -fsSL https://get.evoloop.ai | bash

# 方式 2: wget
wget -qO- https://get.evoloop.ai | bash
```

### 安装脚本功能

`scripts/install.sh` 会自动执行：

1. **依赖检测**
   - Docker 是否安装
   - Docker Compose 版本
   - Git 是否安装
   - 内存/磁盘空间检查

2. **自动安装**（可选）
   - Ubuntu/Debian: `apt-get install docker.io`
   - CentOS/RHEL: `yum install docker`
   - macOS: `brew install --cask docker`

3. **环境配置**
   - 创建安装目录 (`~/evoloop`)
   - 下载 `docker-compose.yml`
   - 创建 `.env` 配置文件
   - 生成随机密钥

4. **服务启动**
   - 拉取 Docker 镜像
   - 启动所有服务
   - 健康检查

### 安装后访问

```
前端界面: http://localhost:8080
后端 API: http://localhost:8000
API 文档: http://localhost:8000/docs
```

### 自定义安装

```bash
# 指定版本
export EVOLOOP_VERSION=v1.2.0
curl -fsSL https://get.evoloop.ai | bash

# 指定安装目录
export INSTALL_DIR=/opt/evoloop
curl -fsSL https://get.evoloop.ai | bash
```

---

## 二、桌面版一键安装

### 目标平台

- macOS: `.dmg` 安装包
- Windows: `.exe` 安装程序
- Linux: `.AppImage`

### 安装流程

```
用户下载 EvoLoop-1.0.0.dmg
    ↓
双击打开，拖拽到 Applications
    ↓
首次启动自动检测：
  ✓ Docker Desktop 是否安装
  ✓ 系统权限是否 granted
    ↓
启动 EvoLoop 应用
```

### 打包命令

```bash
# 打包后端
pyinstaller evoloop-backend.spec

# 打包前端 + 后端
cd frontend
cargo tauri build
```

---

## 三、开发环境一键配置

### 方式 1: 使用 evo CLI

```bash
# 进入 backend 目录
cd backend

# 一键配置开发环境
./bin/evo setup

# 环境诊断
./bin/evo doctor
```

### evo setup 功能

1. 安装 uv（如果未安装）
2. 安装 Python 依赖 (`uv sync`)
3. 创建数据目录 (`~/.evoloop/*`)
4. 生成 `.env` 配置文件
5. 初始化数据库（可选）

### evo doctor 检查项

| 检查项 | 状态 |
|--------|------|
| Python 3 | ✅ 必需 |
| uv | ✅ 必需 |
| Docker | ⚠️ 可选 |
| Docker Compose | ⚠️ 可选 |
| Node.js | ⚠️ 可选 |
| .env 文件 | ⚠️ 提醒创建 |

---

## 四、命令对照表

| 操作 | 服务器版 | 开发版 | 桌面版 |
|------|----------|--------|--------|
| 安装 | `curl \| bash` | `evo setup` | 双击安装包 |
| 启动 | `docker-compose up` | `evo dev` | 点击图标 |
| 停止 | `docker-compose down` | `Ctrl+C` | 点击退出 |
| 日志 | `docker-compose logs` | 终端输出 | 内置日志窗口 |
| 更新 | 重新执行安装脚本 | `git pull && evo setup` | 自动更新 |

---

## 五、常见问题

### Q1: Docker 安装失败

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# 重新登录

# macOS
brew install --cask docker
# 启动 Docker Desktop
```

### Q2: 端口被占用

编辑 `.env` 文件修改端口：
```bash
# 后端端口
PORT=8001

# 前端端口（docker-compose.yml）
frontend:
  ports:
    - "8081:80"
```

### Q3: 如何更新

```bash
# 服务器版
cd ~/evoloop
docker-compose pull
docker-compose up -d

# 开发版
git pull
./bin/evo setup
```

---

## 六、架构对比

```
┌─────────────────────────────────────────────────────────┐
│                    用户选择                              │
└──────────────────┬──────────────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        ↓          ↓          ↓
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ 服务器  │ │ 开发    │ │ 桌面    │
   │ Docker  │ │ 本地    │ │ 应用    │
   └────┬────┘ └────┬────┘ └────┬────┘
        │           │           │
        ↓           ↓           ↓
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │docker-  │ │evo setup│ │Tauri    │
   │compose  │ │evo dev  │ │Sidecar  │
   │up       │ │         │ │         │
   └────┬────┘ └────┬────┘ └────┬────┘
        │           │           │
        └───────────┴───────────┘
                    │
              ┌─────┴─────┐
              │  backend  │
              │ bin/run.py│  ← 统一入口
              └───────────┘
```

---

## 七、扩展阅读

- [Docker 部署详解](./DOCKER_DEPLOY.md)
- [开发环境配置](./DEVELOPMENT.md)
- [Tauri 桌面应用](./DESKTOP_APP.md)
