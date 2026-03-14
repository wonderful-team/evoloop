# EvoLoop Client

EvoLoop 客户端 - 本地代理守护进程，基于 Python 构建，通过 WebSocket 与云端通信。

## 系统要求

* Python 3.11+
* [uv](https://docs.astral.sh/uv/) - Python 包管理和环境管理
* macOS (用于桌面自动化功能)

## 架构

```
┌─────────────────┐      WebSocket      ┌─────────────────┐
│  EvoLoop Client │  ◄──────────────►  │  EvoLoop Cloud  │
│   (本仓库)       │                    │   (云端服务)     │
└────────┬────────┘                    └─────────────────┘
         │
    ┌────┴────┬──────────┬──────────┐
    ▼         ▼          ▼          ▼
┌───────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│SQLite │ │LanceDB │ │本地文件 │ │设备控制   │
│(元数据)│ │(向量)  │ │系统    │ │(macOS)  │
└───────┘ └────────┘ └────────┘ └──────────┘
```

## 快速开始

### 1. 安装依赖

```console
$ cd backend
$ uv sync
```

### 2. 配置环境

复制 `.env.example` 到 `.env` 并配置：

```bash
cp .env.example .env
```

关键配置项：
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` - LLM API 密钥
- `WORKSPACE_ROOT` - 工作空间根目录
- `EVOCLOUD_API_URL` - 云端服务地址

### 3. 启动客户端

```console
# 直接运行
$ uv run python -m app.main

# 或使用脚本
$ bin/evo start
```

## 项目结构

```
backend/
├── app/                    # 应用代码
│   ├── core/              # 核心引擎（代理、内存、环境）
│   ├── domain/            # 领域层（代码库、项目、工具）
│   ├── infrastructure/    # 基础设施（SQLite、LanceDB、云客户端）
│   ├── models/            # SQLModel 模型
│   └── main.py            # 客户端守护进程入口
├── bin/                   # 可执行脚本
│   └── evo                # Evo CLI 工具
└── pyproject.toml         # 项目配置
```

## 存储架构

### Client 模式（本分支）

| 组件 | 技术 | 说明 |
|------|------|------|
| 元数据存储 | SQLite | SQLModel + aiosqlite |
| 向量存储 | LanceDB | 本地嵌入向量 |
| 缓存 | 内存 + 云端 | 通过 CloudDataCache |
| 图数据库 | 禁用 | Neo4j 仅在服务端可用 |
| 任务队列 | 本地 | 无需 Celery |

### Server 模式（云端）

详见 `server` 分支。

## CLI 工具

```bash
# 开发
bin/evo start        # 启动客户端守护进程
bin/evo stop         # 停止守护进程

# 代码质量
bin/evo lint         # 代码检查
bin/evo format       # 代码格式化
```

## 与云端通信

客户端通过 WebSocket 连接到 EvoLoop Cloud：

1. **认证** - 使用 Member Center 的 JWT Token
2. **心跳** - 维持连接和在线状态
3. **命令接收** - 执行云端下发的任务
4. **状态上报** - 返回执行结果和日志

## 打包

### PyInstaller

```bash
# 构建可执行文件
pyinstaller evoloop-client.spec

# 运行
./dist/evoloop-client
```

### Tauri (桌面应用)

详见项目根目录的 `frontend/` 目录。

## 开发配置

### 虚拟环境

```console
$ source .venv/bin/activate
```

### VS Code

项目已配置 VS Code 调试器：
- 断点调试
- 代码格式化（Ruff）
- 类型检查（mypy）

## 注意事项

1. **无 HTTP API** - 客户端不提供 REST API，仅作为后台守护进程运行
2. **SQLite 无需迁移** - 使用 SQLModel 自动建表
3. **本地执行** - 宏执行和代码索引完全在本地完成
4. **云端智能** - LTM、Atlas、技能合成通过 Cloud API 访问

## 更多文档

- [CS 架构实现文档](../docs/CS_ARCHITECTURE_IMPLEMENTATION.md)
- [云端 API 协议](../docs/openapi/cloud_api.yaml)（在 server 分支）
