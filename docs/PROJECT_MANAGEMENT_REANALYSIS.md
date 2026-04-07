# 项目管理系统重新分析

## 🔍 用户反馈理解

> "除了统计外，目前的项目管理功能都有一定的基础了"

**理解：** 用户认为功能基础已存在，但需要梳理整合，不应再追求复杂功能。

---

## 📊 现状重新评估

### 一、现有功能基础（确实已有）

| 功能领域 | 现有基础 | 存储位置 | 完成度 |
|---------|---------|---------|--------|
| **项目基础** | Repository + EvoCloud Project | 本地 + 云端 | 80% |
| **任务CRUD** | EvoCloud Tasks API 代理 | 云端为主 | 70% |
| **任务状态** | status + progress (0-100) | 云端 | 60% |
| **任务优先级** | priority (1-4) | 云端 | 50% |
| **本地Todo** | TodoItem (独立) | SQLite | 90% |
| **执行计划** | Plan + PlanStep | SQLite | 75% |
| **需求管理** | 文档→分析→任务拆解 | SQLite→云端 | 85% |
| **工时记录** | Timesheet/Budget | 云端 | 60% |

### 二、各功能详细分析

#### 1. 项目基础 ✅ 有基础

```python
# Repository (本地)
- id, name, local_path
- project_id (关联 EvoCloud)
- sync_status: DETECTED/PENDING/SYNCED/IGNORED
- indexing_status: pending/in_progress/completed

# EvoCloud Project (云端)
- project_id, name, description
- path, status
```

**问题：** 项目完全依赖 EvoCloud，没有本地项目概念
- 离线时无法查看/管理项目
- 新发现的项目必须先同步到云端才能使用

#### 2. 任务管理 ⚠️ 有基础但分散

```python
# 当前任务来源 (4个！)
1. EvoCloud Tasks      - 正式项目任务 (云端)
2. ProjectRequirementTask - 需求拆解任务 (本地→云端)
3. PlanStep            - 执行计划步骤 (本地)
4. TodoItem            - 快速待办 (本地)
5. AutonomousTask      - 定时自主任务 (本地)
```

**问题：** 用户无法在一个地方看到所有"待办"
- 项目任务在 EvoCloud
- 计划步骤在本地 Plan
- 临时 Todo 在本地
- 需求任务从本地同步到云端

#### 3. 任务层级 ❌ 确实缺失

```python
# 当前模型 (平级)
ProjectRequirementTask:
  - id, analysis_id
  - task_data: {title, priority, ...}  # 没有 parent_id

# 缺失
- parent_id: 无子任务支持
- depends_on: 无任务依赖
```

**但有基础：** PlanStep 有 `order` 字段，支持简单的步骤顺序

#### 4. 可视化 ❌ 完全缺失

```
当前状态:
- 无看板视图
- 无甘特图/时间线
- 无统计图表

但：
- 有 status 字段 (可用来做简单看板)
- 有 progress 字段 (0-100)
```

#### 5. 协作 ❌ 缺失

```
当前:
- 无任务评论
- 无成员分配
- 无@提及

但：
- EvoCloud 可能有这些功能（未充分利用）
```

---

## 🎯 核心问题（重新评估）

### 问题 1：数据分散（最大问题）

```
用户视角：
"我要查看这个项目的所有待办"

实际需要查询：
1. EvoCloud Tasks (项目任务)
2. PlanStep (执行计划步骤)
3. TodoItem (本地待办)
4. ProjectRequirementTask (需求任务)
5. AutonomousTask (自主任务)

→ 需要 5 个查询，5 个数据源
```

### 问题 2：离线不可用

```
场景：用户没有网络
- ❌ 无法查看项目列表（从 EvoCloud 获取）
- ❌ 无法查看项目任务
- ✅ 可以查看本地 Plan/Todo
- ❌ 无法创建项目任务
```

### 问题 3：需求流程过重

```
当前流程：
上传文档 → AI分析 → 确认 → 拆解 → 同步 → 任务
(约 5-10 分钟)

用户反馈：
"我只想快速创建一个任务"
```

---

## 💡 简化版改进建议

### 不做（过于复杂）

| 功能 | 原因 |
|------|------|
| 甘特图 | 需要复杂的时间线和依赖计算 |
| 任务依赖图 | 需要 DAG 计算，容易出错 |
| 多成员协作 | 当前单人使用场景为主 |
| 项目模板 | 可以先使用默认流程 |
| 高级报表 | 用户反馈统计是最不重要的 |

### 做（高价值+简单）

| 优先级 | 功能 | 实现思路 | 预估工作量 |
|--------|------|---------|-----------|
| P0 | **统一任务视图** | API 层聚合 5 个数据源 | 1-2 天 |
| P0 | **快速创建任务** | 绕过需求流程的直接创建 | 半天 |
| P1 | **简单看板** | 按 status 分组展示 | 1-2 天 |
| P1 | **本地项目缓存** | 离线可查看项目列表 | 1 天 |
| P2 | **子任务** | 添加 parent_id 字段 | 2-3 天 |
| P2 | **任务标签** | task_data.tags 已有基础 | 1 天 |

---

## 🔧 具体行动项

### 立即做（本周）

1. **统一任务视图 API**
```python
GET /api/v1/projects/{id}/unified-tasks
Response:
{
  "evocloud_tasks": [...],      # 来自 EvoCloud
  "plan_steps": [...],          # 来自 Plan
  "todos": [...],               # 来自 TodoItem
  "requirement_tasks": [...],   # 来自 ProjectRequirementTask
  "autonomous_tasks": [...]     # 来自 AutonomousTask
}
```

2. **快速创建任务**
```python
POST /api/v1/projects/{id}/quick-task
{"title": "修复bug", "priority": "high"}
# 直接创建 EvoCloud Task，跳过需求流程
```

### 短期做（2周内）

3. **简单看板视图**
```
按 status 分组：
- 待处理 (status=1)
- 进行中 (status=2)
- 已完成 (status=3)
```

4. **本地项目缓存**
```python
# 启动时缓存 EvoCloud 项目列表到 SQLite
LocalProjectCache:
  - project_id
  - name
  - description
  - cached_at
```

### 中期做（1月内）

5. **子任务支持**
```python
# 添加 parent_id 字段
ProjectRequirementTask:
  + parent_id: Optional[str]  # 自引用外键
```

---

## 📈 与通用工具对比（修正版）

| 功能 | EvoLoop | Jira | 评估 |
|------|---------|------|------|
| 任务CRUD | ⭐⭐⭐ | ⭐⭐⭐ | 已有基础 ✅ |
| 任务状态 | ⭐⭐ | ⭐⭐⭐ | 有 status/progress |
| 任务优先级 | ⭐⭐ | ⭐⭐⭐ | 有 priority |
| **统一视图** | ⭐ | ⭐⭐⭐ | **需要聚合** 🔴 |
| **离线使用** | ⭐ | ⭐ | **需要缓存** 🔴 |
| 子任务 | ❌ | ⭐⭐⭐ | 可添加 |
| 看板 | ❌ | ⭐⭐⭐ | 简单版可做 |
| 需求管理 | ⭐⭐⭐ | ⭐⭐ | 反而更复杂 ⚠️ |
| 甘特图 | ❌ | ⭐⭐ | 不做 ❌ |
| 报表 | ❌ | ⭐⭐⭐ | 不做 ❌ |

---

## ✅ 修正后的结论

**用户说得对：**
- 功能基础确实存在
- 不需要复杂功能（甘特图、高级报表等）

**真正需要做的：**
1. **聚合分散的数据**（5个数据源 → 统一视图）
2. **优化创建流程**（需求流程过重）
3. **支持离线使用**（本地缓存）
4. **简单看板**（利用现有 status 字段）

**不做：**
- 甘特图、依赖图（过于复杂）
- 高级报表（用户明确不需要）
- 复杂协作（当前单人场景）
