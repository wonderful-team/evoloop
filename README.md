# EvoLoop - 通用智能体系统 (Universal Agent System)

EvoLoop 是一个先进的**通用智能体系统**，旨在跨多个环境（Web、桌面和移动端）自主规划、研究、编码和执行任务。基于 **LangGraph** 构建，它编排了一组专业的智能体（Agent）来处理复杂的**任务循环 (Task Loops)**，具备自我纠错和深度上下文感知能力。

## 🌟 核心特性 (Key Features)

- **🧠 自主编排 (Autonomous Orchestration)**: 系统支持 **Multi-Agent Orchestration (Phase 10)**。除了预置的 Supervisor，Agent 现在可以动态发现并根据 YAML 配置生成 **Sub-Agents (Skills)**，实现无限层级的任务委派 (`Manager` -> `Architect` -> `Coder`)。
- **🔮 自省与进化 (Introspection & Evolution)**:
  - **Runtime Introspection**: `Meta-Reviewer` 节点充当即时裁判。当任务陷入死循环或测试反复失败时，它会介入分析架构上下文，提供破局建议。
  - **Meta-Evolution Loop**: `SystemScanner` 充当系统医生。全天候监控运行日志，统计故障率。一旦发现系统性缺陷，自动触发 "进化模式"，修改自身后端代码以适应新环境（需开启 `ENABLE_SELF_EVOLUTION`）。
- **🕸️ 图谱情节记忆 (Graph-RAG Episodic Memory)**: 将每一次任务的经验（目标、计划、结果）转化为 Neo4j 中的知识图谱节点。Agent 在规划新任务时会自动回忆相似的历史情节，避免重复错误。
- **🧩 动态工具与 MCP (Dynamic Tooling & MCP)**:
  - **Self-Evolution**: Agent 能在运行时编写全新的 Python 工具 (`create_python_tool`) 并立即注册使用。
  - **MCP Management**: 支持运行时动态挂载/卸载符合 Model Context Protocol 的外部工具服务（如文件系统、搜索工具），无需重启。
- **🌐 全平台控制 (Omni-Platform Control)**:
  - **Browser**: 自动化 Web 交互 (基于 Playwright)。
  - **Desktop**: 控制本地桌面环境 (基于 Agent-S)。
  - **Mobile**: 通过 Tauri 管理移动端任务循环。
- **☁️ EvoCloud 集成 (EvoCloud Integration)**: 内置 `EvoCloudClient`，实现本地智能体与云端项目管理（任务、工时、预算）的实时同步，并支持通过 WebSocket 远程控制设备。
- **📚 深度代码理解 (Deep Code Understanding)**:
  - **Semantic Indexing**: 使用 **Neo4j** 和 **Tree-sitter** 对代码库进行语义索引。
  - **Architecture Inference**: 自动推断模块间的高层依赖关系（如 "Module A depends on Module B"），生成架构知识图谱。
- **🗣️ 动态语言适配 (Dynamic Language Adaptation)**: 系统提示词 (Prompts) 会根据用户偏好动态注入语言设置，支持多语言无缝切换。
- **🔄 自愈循环 (Self-Healing Loops)**: `Coder` <-> `Tester` 循环允许系统在无需人工干预的情况下迭代检测并修复 Bug。
- **👁️ 视觉理解 (Visual Understanding)**:
  - **Multimodal Analysis**: 支持输入图片（本地路径或 URL）。Agent 可以调用 `analyze_image` 工具对 UI 截图、架构图或报错截图进行深度分析。
  - **UI Vision**: 专门针对 GUI/Web 界面优化，能识别按钮、表单和布局结构，辅助 `Browser` 和 `Desktop` Agent 进行精准操作。
  - **Mobile Visual Command**: 移动端 App 支持直接向 Agent 发送图片指令（如拍照上传 Bug 截图）。系统会自动解析图片内容并作为上下文的一部分进行处理，实现随时随地的多模态交互。
- **⚡ 并行深度研究 (Parallel Deep Research)**: 在执行前生成并发的研究任务以收集信息。
- **🛡️ Human-in-the-Loop (HITL) 2.0**:
  - **Approval Card**: 关键决策（如大范围文件修改、危险Shell命令）会自动挂起。前端会弹出 "Approval Card" 展示 Diff 和风险等级，等待用户 `Approve` 或 `Reject`。
  - **Interrupt & Resume**: 即使 Agent 处于后台长时间运行（如 Deep Research），用户也可以随时发送指令中断当前执行，调整目标后无缝恢复。
  - **Autonomous Mode**: 支持在设置中按需开启 "自主模式" 以跳过低风险审批，但在高风险操作时自动回落到 HITL。
- **📖 自动化文档 (Automated Documentation)**:
  - **Auto-Wiki**: 一键生成项目 Wiki。Agent 会深度扫描项目结构，规划章节，并撰写 Markdown 文档。

## 🐝 多智能体编排 (Multi-Agent Orchestration)

EvoLoop Phase 10 引入了**动态技能注册 (Skill Registry)** 和 **委派机制 (Delegation)**，允许您通过 YAML 配置文件定义和组装复杂的 Agent 团队。

### 1. 标准工程团队 (Standard Engineering Team)

系统内置了一组专家级 Agent 配置 (`backend/app/core/engine/config/`)：

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

您可以在 `backend/app/core/engine/config/` 目录下创建新的 `.yaml` 文件来定义新的 Agent：

```yaml
# my_agent.yaml
name: my_special_agent
version: "1.0"
nodes:
  - id: worker
    path: "app.core.engine.nodes.generic.GenericLLMNode"
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
- **核心引擎**: FastAPI + LangGraph (Supervisor/Nodes Architecture)
- **数据库**: PostgreSQL (关系型) + Neo4j (图数据库)
- **队列**: Redis + Celery
- **云连接**: EvoCloud Client (WebSocket + REST)
- **运行时**: Python 3.11 (由 `uv` 管理)

### 前端 (`/frontend`)
- **核心**: React 19 + Vite
- **UI 组件**: Shadcn/UI + TailwindCSS v4
- **原生封装**: Tauri v2 (支持 Windows, macOS, Linux, Android, iOS)

## ☁️ EvoCloud 架构 (Cloud Architecture)

EvoLoop 不仅仅是一个本地 Agent，它通过 `EvoCloudClient` 深度集成到企业级研发管理流中：

1.  **项目同步 (Project Sync)**: 本地代码变更会自动追踪，并与云端项目任务 (Task/Feature) 关联。
2.  **远程控制 (Device Link)**: 通过 WebSocket 长连接，云端 Supervisor 可以向本地 Agent 发送指令（如 "修复这个 Bug"），Agent 执行后自动上传日志和结果。
3.  **资源管理**: 自动同步工时 (Timesheet) 和预算消耗，实现精确的研发成本核算。

## ⚡ 微技能架构 (Micro-Skills Architecture)

EvoLoop 采用先进的 **Micro-Skills** 架构，将重型能力（如浏览器、Docker环境、GUI控制）剥离为独立的 Docker Sidecar 容器。核心 Backend 保持极度轻量，通过 **MCP (Model Context Protocol)** 协议与这些技能单元（Skill Cells）通信。

这种架构带来了极致的稳定性和扩展性：即使某个技能崩溃（如浏览器假死），也不会影响主系统的运行。

| Skill Cell | 端口 | 协议 | 功能描述 |
| :--- | :--- | :--- | :--- |
| **GUI Control (Agent-S)** | `8001` | MCP/SSE | **桌面自动化**。基于 Agent-S，通过 Xvfb/PyAutoGUI 控制 Linux 桌面环境。 |
| **Web Browser (Browser-Use)** | `8002` | MCP/SSE | **复杂网页操作**。基于 Playwright，支持复杂的 DOM 交互和视觉理解。 |
| **Mobile Control (Open-AutoGLM)** | `8003` | MCP/SSE | **移动端控制**。基于 ADB/Uiautomator2，控制 Android 真机或模拟器。 |
| **Web Crawler (Crawl4AI)** | `8004` | MCP/SSE | **高性能爬虫**。将动态网页极速转换为 Markdown/JSON，供 LLM 阅读。 |

### 扩展新技能

只需三步即可无缝挂载新能力：
1. **Containerize**: 将新工具封装为 Docker 容器，暴露 MCP 接口。
2. **Sidecar**: 在 `docker-compose.yaml` 中添加服务定义。
3. **Register**: 系统启动时自动发现并注册为由 LLM 调用的工具。

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

### 高级特性配置 (Advanced Configuration)

为了安全起见，**自我进化 (Self-Evolution)** 功能默认是**禁用**的。虽然系统会被动地诊断问题，但不会自动修改代码。

要启用此功能（允许 Agent 修改自身后端代码），请在 `backend/.env` 中设置：

```env
ENABLE_SELF_EVOLUTION=True
```

> **⚠️ 警告**: 启用此选项意味着 Agent 拥有修改核心代码库的权限。建议仅在受控环境（如开发分支或沙盒）中开启，并确保 Git 版本控制处于活动状态以便回滚。

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
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# fastapi run --reload app/main.py
```

**启动 Celery Worker (研究/异步任务必需):**
```bash
# 在新终端中执行
cd backend
source .venv/bin/activate
# 使用脚本运行 (推荐)
./scripts/start_worker.sh
# 或者手动运行
uv run celery -A app.celery_app worker -l info -P solo -Q celery
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

### 5. LSP 配置 (LSP Configuration)

EvoLoop 使用 **LSP (Language Server Protocol)** 为 Agent 提供深度代码智能（跳转定义、错误检查）。

- **Python**: 依赖 `pyright`。已包含在后端依赖中 (`pyproject.toml`)，无需额外配置。
- **TypeScript/JavaScript**: 依赖 `Node.js` 和 `npm`。
  - 系统会在首次运行时自动下载并配置 `typescript-language-server` 到本地缓存目录，无需全局安装。
  - 请确保 `node` 和 `npm` 命令在系统的 `PATH` 中可用。

- **后端文档**: 请参阅 [backend/README.md](./backend/README.md)
- **前端文档**: 请参阅 [frontend/README.md](./frontend/README.md)

## 📄 许可证 (License)

本项目采用 MIT 许可证。详情请参阅 [LICENSE](./LICENSE) 文件。
