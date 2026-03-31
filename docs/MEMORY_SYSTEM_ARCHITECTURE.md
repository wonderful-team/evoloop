# EvoLoop 记忆系统全景架构分析

## 1. 系统概览：三层记忆架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENT COGNITIVE STACK                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 1: BRAIN (双脑认知系统)                                                │
│  ┌─────────────┐  ┌─────────────┐                                            │
│  │  FAST BRAIN │  │  SLOW BRAIN │                                            │
│  │   (SSM)     │  │   (LLM)     │  ← LightningKernel                         │
│  └─────────────┘  └─────────────┘                                            │
│         │                │                                                   │
│         └────────┬───────┘                                                   │
│                  ▼                                                           │
│  ┌─────────────────────────────────────┐                                     │
│  │     Brain FileSystem Memory         │                                     │
│  │  ├─ sys/identity.md    (系统身份)   │                                     │
│  │  ├─ working/focus.md   (核心记忆)   │                                     │
│  │  ├─ working/task.md    (当前任务)   │                                     │
│  │  └─ knowledge/journal.md (情景记忆) │                                     │
│  └─────────────────────────────────────┘                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 2: MEMORY (持久化记忆系统)                                             │
│  ┌─────────────────────────────────────────────────────────────┐             │
│  │              MemoryManager (统一外观)                        │             │
│  │  ┌──────────────┬──────────────┬──────────────┬───────────┐ │             │
│  │  │  short_term  │  long_term   │ preferences  │   graph   │ │             │
│  │  │   (SQLite)   │   (Neo4j)    │   (Neo4j)    │  (Neo4j)  │ │             │
│  │  └──────────────┴──────────────┴──────────────┴───────────┘ │             │
│  └─────────────────────────────────────────────────────────────┘             │
├─────────────────────────────────────────────────────────────────────────────┤
│  LAYER 3: ATLAS (空间记忆系统)                                                │
│  ┌─────────────────────────────────────────┐                                 │
│  │          AtlasEngine                    │                                 │
│  │  应用 UI 空间地图 (Neo4j)                │                                 │
│  │  ├─ App States (窗口/页面)               │                                 │
│  │  ├─ UI Elements (按钮/输入框)            │                                 │
│  │  └─ Transitions (状态转换)               │                                 │
│  └─────────────────────────────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 各层详细解析

### 2.1 Layer 1: BRAIN - 双脑认知系统

**设计理念：** 模仿人类的双系统思维（System 1 快思考 + System 2 慢思考）

#### 核心组件

| 组件 | 类型 | 职责 |
|------|------|------|
| `LightningKernel` | 内核 | 协调快/慢脑，管理 ReAct 循环 |
| `SSMDriver` | 快脑 | 快速推理，低成本，本地执行 |
| `LLMDriver` | 慢脑 | 深度推理，高成本，远程调用 |
| `BrainFileSystem` | 文件系统 | 记忆持久化存储 |

#### 记忆区域（MemoryZone）

| 区域 | 文件 | 用途 | 类比人脑 |
|------|------|------|---------|
| `SYS` | identity.md | 系统身份、性格定义 | 自我认知 |
| `SYS` | tools.md | 可用工具定义 | 技能记忆 |
| `SYS` | rules.md | 行为规则 | 习得规则 |
| `WORKING` | current_task.md | 当前任务上下文 | 工作记忆 |
| `WORKING` | scratchpad.md | 临时笔记 | 便签纸 |
| `KNOWLEDGE` | journal.md | 历史事件日志 | 情景记忆 |
| `KNOWLEDGE` | projects/ | 项目知识 | 领域知识 |
| `KNOWLEDGE` | users/ | 用户画像 | 社交记忆 |

#### Brain 层工具

| 工具 | 文件 | 功能 |
|------|------|------|
| `recall_memory` | brain/tools/retrieval.py | 检索 journal + graph |
| `update_focus` | brain/tools/management.py | 更新 working/focus.md |
| `memorize` | brain/tools/management.py | 追加到 knowledge/journal.md |

---

### 2.2 Layer 2: MEMORY - 持久化记忆系统

**设计理念：** 分层存储，不同记忆类型用最适合的存储引擎

#### MemoryManager 架构

```
MemoryManager (统一外观)
│
├─ short_term: IShortTermMemory      → SQLite (sql_short_term.py)
│   └─ 对话历史、消息上下文
│
├─ long_term: ILongTermMemory        → Neo4j (neo4j_long_term.py)
│   ├─ Concept (概念图谱)
│   ├─ Episode (经验片段)
│   └─ 向量搜索
│
├─ preferences: IPreferenceStore     → Neo4j (neo4j_preferences.py)
│   └─ 用户偏好、分层覆盖 (global → project)
│
└─ graph: IGraphNavigator            → Neo4j (neo4j_graph.py)
    └─ 代码库图谱、目录结构、依赖关系
```

#### 数据结构

**Concept（概念）**
```python
class Concept:
    name: str              # 概念名称
    description: str       # 概念描述
    project_id: int        # 所属项目
    related_files: list    # 关联文件
```

**Episode（经验）**
```python
class Episode:
    goal: str              # 任务目标
    result: str            # 执行结果
    plan_summary: str      # 计划摘要
    error_msg: str         # 错误信息
    project_id: int        # 所属项目
```

#### Memory 层工具（当前混乱状态）

| 工具 | 位置 | 状态 | 问题 |
|------|------|------|------|
| `search_history` | memory_tools.py | ✅ Worker | 调用 search_chat_history |
| `save_preference` | memory_tools.py | ✅ Worker | 正常 |
| `add_concept` | memory_tools.py | ✅ Worker | 正常 |
| `find_related_episodes` | memory_tools.py | ✅ Worker | 正常 |
| `search_chat_history` | memory_search.py | ❌ 孤儿 | 重复工具 |
| `compress_history` | memory_mgmt.py | ❌ 孤儿 | 未配置 |
| `memorize_concepts` | knowledge.py | ✅ Finish | 功能与 add_concept 重叠 |

---

### 2.3 Layer 3: ATLAS - 空间记忆系统

**设计理念：** 为 UI 自动化构建"肌肉记忆"

#### AtlasEngine 架构

```
AtlasEngine
│
├─ Ingestion (摄入)
│   └─ on_ui_tree_observed()          ← EventBus 监听
│       ├─ 动态应用检测                ← DynamicAppTriage
│       ├─ 基础设施提取                ← 仅存储静态 UI
│       └─ 完整地图存储                ← 静态应用全量存储
│
├─ Storage (存储)
│   └─ Neo4jAtlasStore
│       ├─ App 节点
│       ├─ State 节点 (窗口/页面)
│       ├─ Element 节点 (UI 元素)
│       └─ Transition 关系 (状态转换)
│
└─ Retrieval (检索)
    ├─ query_app_atlas()              ← 查询应用地图
    ├─ get_app_strategy()             ← 获取交互策略
    └─ list_apps()                    ← 列出已知应用
```

#### Atlas 层工具

| 工具 | 位置 | 用途 |
|------|------|------|
| `query_app_atlas` | atlas.py | 查询应用 UI 地图 |
| `list_app_atlas` | atlas.py | 列出所有已知应用 |

---

## 3. 记忆流与调用关系

### 3.1 对话历史搜索流程

```
Agent 调用 search_history(query)
         │
         ▼
┌──────────────────┐
│  memory_tools.py │ ← 工具层
│  search_history  │ ─────┐
└──────────────────┘      │
         │                │
         ▼                │
┌──────────────────┐      │ (不应该这样！)
│ memory_search.py │      │
│ search_chat_history     │
└──────────────────┘      │
         │                │
         ▼                ▼
┌──────────────────┐
│   MemoryManager  │ ← 外观层
│  search_messages │
└──────────────────┘
         │
         ▼
┌──────────────────┐
│ SqlShortTermMemory│ ← 实现层
│  search_messages │
└──────────────────┘
```

**问题：** 工具层存在不必要的中介调用

### 3.2 概念记忆流程

```
Agent 调用 add_concept(name, description)
         │
         ▼
┌──────────────────┐
│  memory_tools.py │
│    add_concept   │
└──────────────────┘
         │
         ▼
┌──────────────────┐
│    memory.py     │ ← 内部实现层
│ add_concept_impl │
└──────────────────┘
         │
         ▼
┌──────────────────┐
│   MemoryManager  │
│ long_term.store  │
└──────────────────┘
         │
         ▼
┌──────────────────┐
│ Neo4jLongTermMemory
│  store_concept   │
└──────────────────┘
```

### 3.3 Brain 记忆流程

```
Agent 调用 memorize(content)
         │
         ▼
┌──────────────────────────┐
│ brain/tools/management.py │
│         memorize          │
└──────────────────────────┘
         │
         ▼
┌──────────────────────────┐
│   BrainFileSystem        │
│   append_file("knowledge/ │
│          journal.md")     │
└──────────────────────────┘
```

### 3.4 上下文注入流程

```
Context Hydration
         │
         ▼
┌──────────────────────────┐
│  MemoryContextPlugin     │
│    (memory_plugin.py)    │
│                          │
│  ├─ 读取 journal.md      │
│  │   → ctx.metadata[     │
│  │     "episodic_memory_ │
│  │        raw"]          │
│  │                       │
│  └─ 读取 focus.md        │
│      → ctx.metadata[     │
│        "core_memory_raw"]│
└──────────────────────────┘
         │
         ▼
┌──────────────────────────┐
│      Prompt Template     │
│  (supervisor.prompt.j2)  │
│                          │
│  ├─ EPISODIC MEMORY      │
│  │  {{ episodic_memory }}│
│  │                       │
│  └─ CORE MEMORY          │
│     {{ core_memory }}     │
└──────────────────────────┘
```

---

## 4. 当前问题全景

### 4.1 架构层面问题

| 问题 | 严重程度 | 描述 |
|------|----------|------|
| 双记忆系统并存 | 🔴 高 | Brain 文件系统 与 Memory 数据库 并存，职责不清 |
| 工具重复 | 🔴 高 | search_history vs search_chat_history |
| 孤儿工具 | 🟡 中 | compress_history 注册但未配置 |
| 跨层调用混乱 | 🟡 中 | Brain 的 memorize 与 Memory 的 add_concept 功能重叠 |

### 4.2 设计层面问题

| 问题 | 描述 | 建议 |
|------|------|------|
| Brain 记忆无法查询 | journal.md 是追加日志，只能 grep | 建立索引或定期导入 Neo4j |
| Memory 无法更新 | Brain 有 update_focus，Memory 缺少对应概念 | 统一概念 |
| Atlas 孤立 | Atlas 是独立系统，与其他记忆层无联动 | 考虑关联 (如 concept ↔ UI element) |

### 4.3 实现层面问题

| 问题 | 位置 | 修复方案 |
|------|------|----------|
| 工具调用工具 | memory_tools.py:57-60 | 直接调用 MemoryManager |
| 重复工具 | memory_search.py | 删除，合并到 search_history |
| 孤儿工具 | memory_mgmt.py | 启用或删除 |
| 命名不一致 | memorize vs add_concept | 统一命名 |

---

## 5. 理想架构建议

### 5.1 职责重新划分

```
┌─────────────────────────────────────────────────────────────┐
│                      理想记忆架构                             │
├─────────────────────────────────────────────────────────────┤
│  BRAIN LAYER (认知层)                                         │
│  ├─ 职责: 快/慢思维协调，上下文管理，任务执行                   │
│  ├─ 存储: 仅工作记忆 (focus.md, task.md)                      │
│  └─ 工具: update_focus, recall (统一检索入口)                 │
├─────────────────────────────────────────────────────────────┤
│  MEMORY LAYER (持久层)                                        │
│  ├─ 职责: 长期知识存储与检索                                   │
│  ├─ 存储: Neo4j (概念、经验、偏好、代码图谱)                    │
│  ├─ 工具:                                                     │
│  │   ├─ 对话: search_history, save_preference                 │
│  │   ├─ 知识: add_concept, find_episodes                      │
│  │   └─ 代码: consult_architecture, query_graph               │
│  └─ 注意: 删除 journal.md，所有持久记忆统一存 Neo4j            │
├─────────────────────────────────────────────────────────────┤
│  ATLAS LAYER (空间层)                                         │
│  ├─ 职责: UI 自动化空间记忆                                    │
│  ├─ 存储: Neo4j (独立数据库或 schema)                          │
│  ├─ 工具: query_app_atlas, list_app_atlas                     │
│  └─ 未来: 与 concept 关联，支持 "点击设置按钮" 语义指令         │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 工具统一方案

```python
# 删除以下重复/孤儿工具
❌ search_chat_history     # 合并到 search_history
❌ compress_history        # 删除或启用
❌ memorize_concepts       # 合并到 add_concept

# 保留并统一
✅ search_history          # Memory 层: 搜索对话历史
✅ save_preference         # Memory 层: 保存用户偏好
✅ add_concept             # Memory 层: 添加概念 (批量模式支持 list)
✅ find_related_episodes   # Memory 层: 查找相关经验

# Brain 层工具
✅ update_focus            # Brain 层: 更新核心记忆
✅ memorize                # Brain 层: 快速记录到工作记忆
✅ recall_memory           # Brain 层: 统一检索入口 (journal + graph)

# Atlas 层工具
✅ query_app_atlas         # Atlas 层: 查询 UI 地图
✅ list_app_atlas          # Atlas 层: 列出应用
```

### 5.3 数据流向

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   用户输入   │───▶│  Supervisor │───▶│   Worker    │
└─────────────┘    └─────────────┘    └─────────────┘
                            │                 │
                            ▼                 ▼
                   ┌─────────────┐    ┌─────────────┐
                   │  search_    │    │  add_concept│
                   │  history    │    │  save_pref  │
                   └─────────────┘    └─────────────┘
                            │                 │
                            └────────┬────────┘
                                     ▼
                            ┌─────────────┐
                            │ MemoryManager│
                            │  (Neo4j)    │
                            └─────────────┘

┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   任务结束   │───▶│   Finish    │───▶│ add_concept │
└─────────────┘    └─────────────┘    │  (批量)      │
                                      └─────────────┘
                                             │
                                             ▼
                                      ┌─────────────┐
                                      │  concept    │
                                      │   graph     │
                                      └─────────────┘
```

---

## 6. 决策建议

### 短期（本周）

1. **删除重复工具**
   - 删除 `memory_search.py`
   - 修复 `memory_tools.py:search_history` 直接调用 MemoryManager

2. **处理孤儿工具**
   - 决定 `compress_history` 命运（建议删除，如需可在 Neo4j 层实现）
   - 决定 `memory_mgmt.py` 命运

3. **统一概念记忆**
   - 将 `memorize_concepts` 重命名为 `save_concepts`
   - 或统一使用 `add_concept`（支持批量参数）

### 中期（本月）

1. **Brain 与 Memory 整合**
   - 评估是否将 journal.md 迁移到 Neo4j
   - 统一 `memorize` 和 `add_concept` 语义

2. **工具命名规范化**
   - 统一 `动词_名词` 模式

### 长期（下季度）

1. **Atlas 联动**
   - 将 UI 元素与 Concept 关联
   - 支持语义化 UI 操作 ("点击设置按钮")

2. **记忆压缩与总结**
   - 在 Neo4j 层实现对话历史的自动压缩
   - 定期生成 Episode 摘要
