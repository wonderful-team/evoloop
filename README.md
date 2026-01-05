# EvoLoop - 通用智能体系统 (Universal Agent System)

EvoLoop 是一个先进的**通用智能体系统**，旨在跨多个环境（Web、桌面和移动端）自主规划、研究、编码和执行任务。基于 **LangGraph** 构建，它编排了一组专业的智能体（Agent）来处理复杂的工作流，具备自我纠错和深度上下文感知能力。

## 🌟 核心特性 (Key Features)

- **🧠 自主编排 (Autonomous Orchestration)**: 系统支持 **Multi-Agent Orchestration (Phase 10)**。除了预置的 Supervisor，Agent 现在可以动态发现并根据 YAML 配置生成 **Sub-Agents (Skills)**，实现无限层级的任务委派 (`Manager` -> `Architect` -> `Coder`)。
- **🧩 动态工具 (Dynamic Tooling)**: Agent 具备自我进化能力，能在运行时编写全新的 Python 工具 (`create_python_tool`) 并立即注册使用，不再受限于预定义的工具集。
- **🌐 全平台控制 (Omni-Platform Control)**:
  - **Browser**: 自动化 Web 交互。
  - **Desktop**: 控制本地桌面环境。
  - **Mobile**: 通过 Tauri 管理移动端工作流。
- **📚 深度代码理解 (Deep Code Understanding)**: 使用 **Neo4j** 和 **Tree-sitter** 对代码库进行语义索引和查询。
- **🔄 自愈工作流 (Self-Healing Workflows)**: `Coder` <-> `Tester` 循环允许系统在无需人工干预的情况下迭代检测并修复 Bug。
- **⚡ 并行深度研究 (Parallel Deep Research)**: 在执行前生成并发的研究任务以收集信息。

## 🐝 多智能体编排 (Multi-Agent Orchestration)

EvoLoop Phase 10 引入了**动态技能注册 (Skill Registry)** 和 **委派机制 (Delegation)**，允许您通过 YAML 配置文件定义和组装复杂的 Agent 团队。

### 1. 标准工程团队 (Standard Engineering Team)

系统内置了一组专家级 Agent 配置 (`backend/app/core/workflows/config/`)：

| Agent Role | ID (`skill_name`) | 职能描述 | 核心工具 |
| :--- | :--- | :--- | :--- |
| **Engineering Manager** | `team_manager` | **团队指挥官**。负责接收用户需求，拆解任务计划，并动态委派给 Researcher, Architect 和 Engineer。 | `delegate_task`, `create_plan` |
| **Senior Architect** | `team_architect` | **架构师**。负责顶层设计，查阅现有架构文档，确保技术决策的一致性。 | `consult_architecture` |
| **Researcher** | `team_researcher` | **研究员**。深度阅读代码和文档，提供上下文分析报告。 | `explore_codebase`, `read_document` |
| **Senior Engineer** | `team_engineer` | **高级工程师**。负责实际代码实现。拥有**自制工具** (`create_python_tool`) 的权限。 | `manage_file`, `create_python_tool` |

### 2. 如何使用 (Usage)

Agent 之间通过 `delegate_task` 工具自动协作。如果您想让系统以 "Manager" 模式运行，您可以直接与 `team_manager` 交互（取决于系统配置的入口），或者仅仅只需告诉主 Agent："请让工程团队处理这个问题"。

```python
# 示例：Agent 内部调用逻辑
await delegate_task.ainvoke({
    "skill_name": "team_manager", 
    "task_input": {
        "messages": [{"role": "user", "content": "重构 backend/app/core 模块"}]
    }
})
```

### 3. 自定义 Agent (Custom Skills)

您可以在 `backend/app/core/workflows/config/` 目录下创建新的 `.yaml` 文件来定义新的 Agent：

```yaml
# my_agent.yaml
name: my_special_agent
version: "1.0"
nodes:
  - id: worker
    path: "app.core.workflows.nodes.generic.GenericLLMNode"
    config:
      system_prompt: "You are a Specialist in X."
      tools: ["your_tool_a", "your_tool_b"]
edges:
  - from: worker
    to: END
```
系统会自动扫描并注册 `my_special_agent`，使其可被委派。


## 🏗 系统架构 (Architecture)

系统分为强大的 Python 后端和跨平台的前端。

### 后端 (`/backend`)
- **框架**: FastAPI + LangGraph
- **数据库**: PostgreSQL (关系型) + Neo4j (图数据库)
- **队列**: Redis + Celery
- **运行时**: Python 3.11 (由 `uv` 管理)

### 前端 (`/frontend`)
- **核心**: React 19 + Vite
- **UI 组件**: Shadcn/UI + TailwindCSS v4
- **原生封装**: Tauri v2 (支持 Windows, macOS, Linux, Android, iOS)

## 🚀 快速开始 (Getting Started)

### 环境要求 (Prerequisites)

- **Docker & Docker Compose** (用于数据库基础设施)
- **Python 3.11+** & [uv](https://docs.astral.sh/uv/)
- **Node.js 20+** & npm
- **Rust** (用于 Tauri 桌面应用构建)

### 1. 环境配置 (Environment Setup)

复制示例环境变量文件：
```bash
cp .env.example .env
cd backend && cp .env.example .env
cd ../frontend && cp .env.example .env
```
> **注意**: 你需要在 `backend/.env` 中配置 LLM 提供商（OpenAI/Anthropic）的 API Key。

### 2. 启动基础设施 (Start Infrastructure)

启动 Postgres, Redis, 和 Neo4j：
```bash
docker compose up -d db redis neo4j
```

### 3. 启动后端 (Run Backend)

你可以使用 Docker 或手动启动后端进行开发。

**手动开发模式 (推荐):**
```bash
cd backend
uv sync
source .venv/bin/activate
# 启动 Web 服务
fastapi run --reload app/main.py
```

**启动 Celery Worker (研究/异步任务必需):**
```bash
# 在新终端中执行
cd backend
source .venv/bin/activate
# 使用脚本运行 (推荐)
./scripts/start_worker.sh
# 或者手动运行
# celery -A app.celery_app worker -l info -P solo -Q celery
```

### 4. 启动客户端 (Run Client)

**Web 模式:**
```bash
cd frontend
npm install
npm run dev
```

**桌面应用 (Tauri):**
```bash
cd frontend
npm run tauri dev
```

**构建发布 (Build):**
```bash
cd frontend
npm run tauri build
```

## 🛠 开发指南 (Development)

- **后端文档**: 请参阅 [backend/README.md](./backend/README.md)
- **前端文档**: 请参阅 [frontend/README.md](./frontend/README.md)

## 📄 许可证 (License)

本项目采用 MIT 许可证。详情请参阅 [LICENSE](./LICENSE) 文件。
