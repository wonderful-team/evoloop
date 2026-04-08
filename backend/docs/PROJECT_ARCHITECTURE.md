# EvoLoop 项目管理系统架构梳理

> 本文档全面梳理 EvoLoop 项目管理系统的整体架构，包含目录结构、核心模块、API 路由、数据库模型等关键信息。

---

## 一、项目概述

EvoLoop 是一个 AI 驱动的项目管理与开发助手系统，支持以下核心能力：
- **AI 对话与任务执行** - 基于 LangGraph 的智能体系统
- **项目管理** - 需求管理、任务跟踪、子任务分解
- **代码库管理** - 代码索引、符号检索、变更分析
- **技能学习** - Human-in-the-Loop 技能习得与复用
- **Wiki 生成** - 自动化文档生成
- **多环境控制** - 浏览器、桌面、移动设备控制

### 运行模式

| 模式 | 数据库 | 任务队列 | 适用场景 |
|------|--------|----------|----------|
| Embedded | SQLite | Huey | 单机/本地运行 |
| Full | PostgreSQL | Celery + Redis | 分布式部署 |

---

## 二、目录结构

```
app/
├── api/                    # API 层 - FastAPI 路由
│   ├── routes/            # 路由定义 (30+ 个模块)
│   └── dependencies/      # 依赖注入
├── core/                  # 核心层 - 业务核心逻辑
│   ├── engine/           # LangGraph 智能体引擎
│   ├── memory/           # 记忆系统 (Hot/Warm/Cold)
│   ├── context/          # 上下文管理
│   ├── environment/      # 环境感知 (Android/Desktop)
│   ├── events/           # 事件系统
│   ├── learning/         # 技能学习系统
│   ├── execution/        # 执行层 (Sandbox/Terminal)
│   ├── file/             # 文件操作
│   ├── atlas/            # Atlas 感知系统
│   ├── evocloud/         # EvoCloud 云服务集成
│   ├── voice/            # 语音处理 (STT/TTS)
│   └── vision/           # 视觉处理 (截图/录屏)
├── domain/               # 领域层 - 业务领域逻辑
│   ├── project/          # 项目管理 (需求/任务)
│   ├── codebase/         # 代码库管理
│   ├── wiki/             # Wiki 生成
│   ├── planning/         # 规划系统
│   ├── testing/          # 测试相关
│   ├── tools/            # 领域工具
│   └── knowledge/        # 知识管理
├── infrastructure/       # 基础设施层
│   ├── database/         # 数据库 (SQL/Graph/Vector)
│   ├── queue/            # 任务队列 (Huey/Celery)
│   ├── llm/              # LLM 客户端
│   ├── embeddings/       # 向量嵌入
│   ├── cache/            # 缓存系统
│   └── config/           # 配置服务
├── models/               # 数据模型 - SQLModel/SQLAlchemy
├── services/             # 服务层
├── tasks/                # 后台任务
└── utils/                # 工具函数

config/                   # 配置文件
├── agents/              # 智能体配置
├── skills/              # 技能定义
└── templates/           # 提示词模板
```

---

## 三、核心模块详解

### 3.1 API 层 (`app/api/`)

| 路由文件 | 路径前缀 | 核心功能 |
|----------|----------|----------|
| `agent.py` | `/chat`, `/webhook` | AI 对话主入口 |
| `projects.py` | `/projects` | 项目管理 (CRUD/设置) |
| `project_requirements.py` | - | 需求管理 (分模块) |
| `subtasks.py` | - | 子任务管理 (树形结构) |
| `conversations.py` | `/conversations` | 对话历史管理 |
| `files.py` | `/files` | 文件操作 |
| `learning.py` | `/learning` | 技能学习 |
| `wiki.py` | `/wiki` | Wiki 生成 |
| `memory.py` | `/memory` | 记忆管理 |
| `member.py` | `/member` | 会员/订阅权益 |
| `devices.py` | `/devices` | 设备管理 |
| `mcp.py` | `/mcp` | MCP 服务器管理 |
| `audio.py` | `/audio` | 语音处理 |
| `stream.py` | - | SSE 流式输出 |

### 3.2 核心引擎 (`app/core/engine/`)

基于 LangGraph 的智能体执行引擎：

```
engine/
├── graph_builder.py      # 动态图构建器
├── nodes/               # 图节点实现
│   ├── call_model.py   # 模型调用节点
│   ├── tool_node.py    # 工具执行节点
│   └── router.py       # 路由节点
├── tools/              # 工具注册与管理
├── prompts/            # 提示词模板
├── config/             # 图配置 (YAML)
└── tasks.py            # 后台任务定义
```

**关键组件：**
- `GraphBuilder` - 从 YAML 配置动态构建执行图
- `ToolRegistry` - 工具注册与发现
- `Agent State` - 智能体状态管理

### 3.3 记忆系统 (`app/core/memory/`)

分层记忆架构：

```
memory/
├── interfaces/          # 抽象接口
│   ├── hot.py         # 热记忆 (工作记忆)
│   ├── warm.py        # 温记忆 (短期存储)
│   └── long_term.py   # 长期记忆
├── backends/           # 存储后端
│   ├── sqlite.py      # SQLite 实现
│   └── postgres.py    # PostgreSQL 实现
├── strategies/         # 检索策略
└── memory_container.py # 统一容器
```

### 3.4 项目管理 (`app/domain/project/`)

```
project/
├── requirements/       # 需求管理
│   ├── models.py      # RequirementModule, ProjectRequirementTask
│   ├── service.py     # 业务逻辑
│   └── tools.py       # 需求相关工具
├── sync_tasks.py      # 任务同步
├── sync_service.py    # 项目同步
├── summarizer.py      # 项目摘要
└── discovery_manager.py # 项目发现
```

**核心模型：**
- `RequirementModule` - 需求模块 (功能/技术/修复)
- `ProjectRequirementTask` - 需求任务 (树形结构)
- `Subtask` - 子任务 (支持嵌套)

### 3.5 代码库管理 (`app/domain/codebase/`)

```
codebase/
├── indexing/           # 代码索引
│   ├── manager.py     # 索引管理器
│   └── service.py     # 索引服务
├── analysis/           # 代码分析
├── exploration/        # 代码探索
└── retrieval/          # 代码检索
```

### 3.6 任务队列 (`app/infrastructure/queue/`)

支持三种后端：

```
queue/
├── factory.py          # 工厂模式创建调度器
├── base.py            # 抽象基类
├── huey_queue.py      # Huey + SQLite 实现
├── celery.py          # Celery + Redis 实现
└── local.py           # 本地内存实现 (开发)
```

**使用方式：**
```python
from app.infrastructure.queue import shared_task

@shared_task(name="my_task")
def my_task(args):
    pass

# 发送任务
scheduler.send_task("my_task", kwargs={"arg": "value"})
```

---

## 四、数据库模型

### 4.1 核心实体关系

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│     Project     │────▶│  Requirement    │────▶│  Requirement    │
│                 │     │    Module       │     │     Task        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Conversation  │     │   Codebase      │     │     Subtask     │
│    (Thread)     │     │     Repo        │     │   (树形结构)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│     Message     │
└─────────────────┘
```

### 4.2 主要模型定义

| 模型 | 文件 | 描述 |
|------|------|------|
| `Project` | `app/models/__init__.py` | 项目 |
| `Conversation` | `app/models/conversation.py` | 对话 |
| `Message` | `app/models/conversation.py` | 消息 |
| `RequirementModule` | `app/domain/project/requirements/models.py` | 需求模块 |
| `ProjectRequirementTask` | `app/domain/project/requirements/models.py` | 需求任务 |
| `Subtask` | `app/models/__init__.py` | 子任务 |
| `CodebaseRepo` | `app/models/codebase.py` | 代码库 |
| `LearningEpisode` | `app/models/learning.py` | 学习片段 |
| `Skill` | `app/models/learning.py` | 技能 |

### 4.3 需求任务模型 (新)

```python
class ProjectRequirementTask(Base):
    """需求任务表 - 支持子任务分解"""
    id: int                    # 主键
    project_id: int           # 项目ID
    module_id: int            # 模块ID
    parent_id: int (可选)      # 父任务ID (自关联)
    name: str                 # 任务名称
    status: str               # 状态 (pending/in_progress/completed)
    priority: str             # 优先级 (low/medium/high/critical)
    progress: int             # 进度 0-100
    created_at: datetime
    updated_at: datetime
    started_at: datetime (可选)
    completed_at: datetime (可选)
    
    # 关系
    parent: ProjectRequirementTask
    children: List[ProjectRequirementTask]
```

---

## 五、API 路由详细映射

### 5.1 项目管理 API

```
GET    /api/v1/projects                    # 项目列表
POST   /api/v1/projects                    # 创建项目
GET    /api/v1/projects/{id}               # 项目详情
PUT    /api/v1/projects/{id}               # 更新项目
DELETE /api/v1/projects/{id}               # 删除项目
GET    /api/v1/projects/{id}/status        # 项目状态
POST   /api/v1/projects/{id}/summarize     # 生成摘要
```

### 5.2 需求管理 API

```
GET    /api/v1/project-requirements/{project_id}           # 获取需求
POST   /api/v1/project-requirements/{project_id}/parse     # 解析需求
POST   /api/v1/project-requirements/{project_id}/generate  # 生成需求
DELETE /api/v1/project-requirements/{project_id}/modules/{module_id}  # 删除模块

# 子任务管理
GET    /api/v1/project-requirements/tasks/{task_id}/subtasks     # 获取子任务
POST   /api/v1/project-requirements/tasks/{task_id}/subtasks     # 创建子任务
PUT    /api/v1/project-requirements/subtasks/{subtask_id}        # 更新子任务
DELETE /api/v1/project-requirements/subtasks/{subtask_id}        # 删除子任务
POST   /api/v1/project-requirements/subtasks/{subtask_id}/status # 更新状态
```

### 5.3 AI 对话 API

```
POST   /api/v1/chat                # 发送消息
POST   /api/v1/chat/interrupt      # 中断执行
POST   /api/v1/webhook             # 外部 Webhook
GET    /api/v1/conversations       # 对话列表
GET    /api/v1/conversations/{id}  # 对话详情
```

### 5.4 Wiki API

```
GET    /api/v1/wiki/{project_id}           # 获取 Wiki 页面
POST   /api/v1/wiki/generate              # 生成 Wiki (需要 wiki_generation 权益)
```

### 5.5 会员权益 API

```
GET    /api/v1/member/subscription/benefits    # 获取权益列表
```

**权益代码：**
- `browser_control` - 浏览器控制
- `desktop_control` - 桌面控制
- `mobile_control` - 手机控制
- `voice` - 语音交互
- `skill_learning` - 技能学习
- `wiki_generation` - Wiki 生成
- `gantt` - 甘特图
- `timesheet` - 工时表
- `knowledge_base` - 知识库

---

## 六、后台任务

### 6.1 任务定义 (`app/core/engine/tasks.py`)

| 任务名 | 功能 |
|--------|------|
| `engine_persist_message` | 持久化消息 |
| `engine_persist_file_operation` | 持久化文件操作 |
| `engine_snapshot_steps` | 快照执行步骤 |
| `engine_harvest_concepts` | 概念收获 |
| `engine_record_episode` | 记录学习片段 |
| `engine_prune_checkpoints` | 清理检查点 |
| `engine_git_harvest` | Git 提交分析 |

### 6.2 Wiki 任务 (`app/domain/wiki/tasks.py`)

```python
@shared_task(name="wiki_generate")
def generate_wiki_task(project_id: int, topic: str, force_regenerate: bool = False):
    """后台生成 Wiki 文档"""
```

---

## 七、启动流程

```
1. 数据库初始化
   ├── Embedded: SQLite 创建表
   └── Full: PostgreSQL 创建扩展和表

2. 系统数据初始化
   └── init_data() - 种子数据

3. 配置变更处理器注册

4. 记忆系统初始化
   └── MemoryContainer

5. Agent 唤醒 (Agent Awakening)
   ├── 注册事件处理器
   ├── 环境感知 awaken()
   ├── 启动环境监控
   └── Atlas 配置初始化

6. MCP 服务器配置

7. 技能同步

8. 持久化层
   └── Checkpointer 初始化

9. Graph 构建
   └── GraphBuilder.build()

10. 项目摘要 Worker

11. 文件监控
    ├── Project Discovery Manager
    └── Codebase Indexing Manager

12. EvoCloud 连接
```

---

## 八、关键设计模式

### 8.1 依赖注入

```python
# FastAPI 依赖
from app.api.deps import TokenDep, require_benefit

@router.post("/wiki/generate", dependencies=[Depends(require_benefit("wiki_generation"))])
async def generate_wiki(req: WikiGenerationRequest, _token: TokenDep):
    pass
```

### 8.2 工厂模式

```python
# 任务队列工厂
from app.infrastructure.queue.factory import create_task_scheduler, shared_task

scheduler = create_task_scheduler("huey")  # 或 "celery"

@shared_task(name="my_task")
def my_task():
    pass
```

### 8.3 事件驱动

```python
# 事件发布
from app.core.events.base import event_bus

event_bus.publish("project.switched", {"project_id": id})

# 事件订阅
event_bus.subscribe("project.switched", handler_func)
```

### 8.4 树形结构 (子任务)

```python
class ProjectRequirementTask(Base):
    parent_id = Column(Integer, ForeignKey("project_requirement_tasks.id"), nullable=True)
    parent = relationship("ProjectRequirementTask", remote_side=[id], back_populates="children")
    children = relationship("ProjectRequirementTask", back_populates="parent")
```

---

## 九、配置文件

### 9.1 核心配置 (`app/core/config.py`)

| 配置项 | 说明 |
|--------|------|
| `EMBEDDED_MODE` | 是否嵌入式模式 |
| `TASK_QUEUE_BACKEND` | 任务队列后端 (huey/celery/local) |
| `WORKSPACE_ROOT` | 工作空间根目录 |
| `SQLITE_PATH` | SQLite 数据库路径 |
| `CHECKPOINTER_DATABASE_URI` | Checkpointer 数据库 URI |

### 9.2 智能体配置 (`app/core/engine/config/`)

```yaml
# agent_main.yaml
graph:
  entry_point: "call_model"
  nodes:
    - name: "call_model"
      type: "model"
    - name: "tools"
      type: "tool"
    - name: "router"
      type: "router"
```

---

## 十、开发指南

### 10.1 添加新 API

1. 在 `app/api/routes/` 创建路由文件
2. 在 `app/api/main.py` 注册路由
3. 添加必要的权限检查 (`require_benefit`)

### 10.2 添加新任务

1. 在 `app/core/engine/tasks.py` 定义任务函数
2. 使用 `@shared_task(name="task_name")` 装饰器
3. 通过 `scheduler.send_task("task_name", kwargs={})` 发送任务

### 10.3 添加新模型

1. 在 `app/models/` 或相应 domain 目录创建模型
2. 继承 `Base` 或 `SQLModel`
3. 在 lifespan 中确保表创建

---

## 十一、故障排查

### 11.1 任务队列问题

```bash
# 清空队列
cd /path/to/backend
python -c "from app.infrastructure.queue.huey_queue import get_huey_scheduler; get_huey_scheduler().get_huey().flush()"

# 启动 Worker
evo worker --verbose
```

### 11.2 数据库问题

```bash
# SQLite 数据库位置
~/.evoloop/backend.db
~/.evoloop/task_queue.db
```

### 11.3 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `HueyException: task not found` | 任务名格式错误 | 检查 `__module__` 设置 |
| `403 Forbidden` | 缺少权益 | 检查会员订阅 |
| `InFailedSqlTransaction` | 数据库事务失败 | 检查事务边界 |

---

## 十二、未来规划

### Phase 0.2 - 技能学习系统 ✅
- Human-in-the-Loop 技能习得
- 技能复用与组合

### Phase 1 - 规划系统
- 自动化项目规划
- 资源分配优化

### Phase 2 - 代码库深度集成
- 更强大的代码分析
- 智能重构建议

### Phase 3 - 测试系统
- 自动化测试生成
- 测试覆盖分析

### Phase 4 - Ghost Text ✅
- 行内代码补全

---

**文档版本:** 2025-04-04  
**维护者:** EvoLoop Team
