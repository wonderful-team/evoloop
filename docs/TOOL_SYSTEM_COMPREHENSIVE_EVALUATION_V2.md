# EvoLoop 工具系统全面评估报告 V2

## 执行摘要

基于代码探索重构后的状态，工具系统仍有优化空间。**核心问题：Worker 47个工具仍然超载，搜索类工具过多，跨节点重复仍然存在。**

---

## 1. 当前状态快照

### 1.1 工具分布

| 节点 | 工具数 | 核心职责 |
|------|--------|----------|
| **Supervisor** | 9 | 路由、规划、协调 ✅ 合理 |
| **Worker** | 47 | 执行、文件、代码、环境 ⚠️ 超载 |
| **Finish** | 6 | 收尾、知识沉淀 ✅ 合理 |
| **总计** | **51** unique tools | |

### 1.2 Worker 工具分类详情

```
[CODE] 10个工具 ⚠️
  - find_symbol, search_code, ask_codebase (✅ 新的统一层)
  - search_history, search_skills, search_native_tools, search_web (⚠️ 搜索类过多)
  - analyze_feasibility, consult_architecture, analyze_impact (✅ 分析类)
  - check_types, inspect_symbol (✅ 检查类)
  
[FILE] 5个工具 ✅
  - read_file, write_file, edit_file
  - list_directory, manage_directory

[ENV] 5个工具 ✅
  - desktop_control, mobile_control, browser_control
  - analyze_image, verify_ui_state

[PLAN] 7个工具 ⚠️ 略多
  - create_plan, create_todo, update_step_status
  - create_checkpoint, list_checkpoints, rollback_checkpoint, delete_checkpoint

[MEMORY] 4个工具 ✅
  - save_preference, add_concept
  - save_concepts, find_related_episodes

[HITL] 4个工具 ✅
  - ask_confirm, ask_human
  - inspect_task_health, list_autonomous_tasks

[ORCH] 2个工具 ✅
  - manage_session_metadata, spawn_agents

[OTHER] 10个工具 ⚠️ 杂项过多
  - execute_command, run_macro, wait_for
  - use_mcp_server, delegate_periodic_intent
  - list_app_atlas, query_app_atlas
  - ...
```

---

## 2. 核心问题诊断

### 2.1 问题 1：搜索类工具过多 (7个)

**当前搜索工具：**
| 工具 | 搜索对象 | 问题 |
|------|----------|------|
| `search_history` | 对话历史 | ✅ 独特 |
| `search_skills` | 技能库 | ✅ 独特 |
| `search_native_tools` | 原生工具 | ⚠️ 低频 |
| `search_web` | 网页 | ✅ 独特 |
| `search_code` | 代码 | ✅ 新工具 |
| `ask_codebase` | 代码库(语义) | ✅ 新工具 |
| `find_symbol` | 符号 | ✅ 新工具 |

**问题：** Agent 面对 7 个搜索工具，选择困难。

**优化建议：**
```python
# 统一为 4 个搜索入口
search_history(query)        # 对话历史（不变）
search_knowledge(query)      # 合并 skills + native_tools
search_web(query)            # 网页搜索（不变）
search_code(query/pattern)   # 合并 code + symbol + ask_codebase
```

---

### 2.2 问题 2：跨节点重复仍然严重

**重复出现在 Supervisor + Worker 的工具：**

| 工具 | Supervisor | Worker | 必要性 |
|------|------------|--------|--------|
| `create_plan` | ✅ | ✅ | Worker 不需要 |
| `search_skills` | ✅ | ✅ | 两者都需要 ✅ |
| `ask_confirm` | ✅ | ✅ | 两者都需要 ✅ |
| `ask_human` | ✅ | ✅ | 两者都需要 ✅ |
| `manage_session_metadata` | ✅ | ✅ | Supervisor 不需要 |
| `spawn_agents` | ✅ | ✅ | Supervisor 专属 |

**问题：** Supervisor 配置了太多执行类工具。

---

### 2.3 问题 3："列出"类工具过多 (6个)

| 工具 | 列出对象 |
|------|----------|
| `list_directory` | 文件目录 |
| `list_todos` | 待办事项 |
| `list_checkpoints` | 检查点 |
| `list_app_atlas` | 应用图谱 |
| `list_autonomous_tasks` | 自主任务 |
| `find_related_episodes` | 相关历史 (find而非list) |

**问题：** 命名不统一 (list_ vs find_)，功能模式相似但分散。

---

### 2.4 问题 4：HITL 工具与检查工具混淆

| 工具 | 类型 | 问题 |
|------|------|------|
| `ask_confirm` | HITL | ✅ 正确 |
| `ask_human` | HITL | ✅ 正确 |
| `inspect_task_health` | 系统检查 | ⚠️ 不是 HITL |
| `list_autonomous_tasks` | 系统查询 | ⚠️ 不是 HITL |
| `check_types` | 代码检查 | ⚠️ 新工具，分类不明 |
| `inspect_symbol` | 代码检查 | ⚠️ 新工具，分类不明 |

**问题：** `inspect_*` 工具命名暗示检查/查看，但与 HITL 的 `ask_*` 混在同一类别。

---

### 2.5 问题 5：环境控制工具粒度

| 工具 | 控制对象 | 问题 |
|------|----------|------|
| `desktop_control` | 桌面 | Facade 模式？ |
| `mobile_control` | 移动设备 | Facade 模式？ |
| `browser_control` | 浏览器 | Facade 模式？ |

**问题：** 这些可能也是 Facade 工具（需要验证）。

---

## 3. 优化建议

### 3.1 搜索工具统一 (7 → 4)

**方案：**
```yaml
# 删除
- search_native_tools  # 低频，可合并

# 合并 search_skills + search_native_tools → search_knowledge
@evoloop_tool
async def search_knowledge(
    query: str,
    source: Literal["skills", "tools", "both"] = "both"
)

# 合并 search_code + find_symbol + ask_codebase 的入口
# 保持为独立工具但统一分类为 "Code Search"
```

### 3.2 进一步精简 Supervisor (9 → 6)

**当前：**
```yaml
supervisor:
  - route_to              # ✅ 核心
  - manage_session_metadata  # ❌ 移至 Worker
  - spawn_agents          # ✅ 核心
  - decompose_task        # ✅ 核心
  - aggregate_results     # ✅ 核心
  - search_skills         # ✅ 需要
  - create_plan           # ❌ 移至 Worker
  - ask_confirm           # ✅ 需要
  - ask_human             # ✅ 需要
```

**建议：**
```yaml
supervisor:
  - route_to              # 路由（核心）
  - spawn_agents          # 生成代理（核心）
  - decompose_task        # 任务分解（核心）
  - aggregate_results     # 结果聚合（核心）
  - ask_confirm           # HITL确认
  - ask_human             # HITL询问
  # 移除: manage_session_metadata, create_plan → 移至 Worker
  # 移除: search_skills → 如有需要 Worker 可用
```

### 3.3 统一"列出"工具命名

**当前混乱：**
- `list_directory`
- `list_todos`
- `list_checkpoints`
- `list_app_atlas`
- `list_autonomous_tasks`
- `find_related_episodes` (find而非list)

**建议统一：**
```python
# 保持 list_* 命名
list_directory(path)
list_todos(status)
list_checkpoints()
list_app_atlas()
list_autonomous_tasks()

# find → search 统一
find_related_episodes → search_episodes(concept)
```

### 3.4 Worker 工具分层暴露

**当前：** 47个工具一次性暴露
**建议：** 三层暴露

```yaml
# Tier 1: 核心高频 (始终暴露)
worker_core:
  - read_file, write_file, edit_file
  - list_directory, execute_command
  - ask_human, ask_confirm
  - search_history, search_code

# Tier 2: 场景特定 (根据 mission_type 动态暴露)
worker_coding:
  - find_symbol, check_types, inspect_symbol
  - analyze_impact, ask_codebase
  
worker_automation:
  - desktop_control, mobile_control, browser_control
  - analyze_image

worker_research:
  - search_web

# Tier 3: 低频/系统 (按需)
worker_system:
  - use_mcp_server
  - delegate_periodic_intent
  - inspect_task_health
  - list_autonomous_tasks
```

---

## 4. 预期效果

### 4.1 工具数量变化

| 优化项 | 当前 | 优化后 | 变化 |
|--------|------|--------|------|
| Supervisor | 9 | 6 | -3 |
| Worker (Tier 1) | 47 | 15 | 暴露核心 |
| Worker (全量) | 47 | 47 | 不变 |
| **平均暴露** | **47** | **15** | **-68%** |

### 4.2 认知效率提升

| 指标 | 提升 |
|------|------|
| 单次决策选项 | 47 → 15 (-68%) |
| 搜索工具选择 | 7 → 4 (-43%) |
| 命名一致性 | +20% |

---

## 5. 实施优先级

### 🔴 高优先级

1. **搜索工具合并**
   - `search_skills` + `search_native_tools` → `search_knowledge`
   - 减少 1 个工具

2. **Supervisor 精简**
   - 移除 `manage_session_metadata`, `create_plan`
   - 减少 2 个工具

### 🟡 中优先级

3. **Worker 分层暴露**
   - 实现 Tier 1/2/3 动态加载
   - 核心暴露从 47 → 15

4. **命名统一**
   - `find_related_episodes` → `search_episodes`

### 🟢 低优先级

5. **环境控制工具评估**
   - 检查 `desktop/mobile/browser_control` 是否为 Facade
   - 如需拆分，制定拆分方案

---

## 6. 总结

### 当前主要问题
1. **Worker 47个工具超载** - 超过认知负荷
2. **搜索类工具 7个过多** - 选择困难
3. **跨节点重复仍然存在** - Supervisor 不够精简
4. **缺乏分层暴露** - 所有工具一次性暴露

### 核心优化方向
1. **搜索统一** - 7个 → 4个
2. **Supervisor 精简** - 9个 → 6个
3. **Worker 分层** - 核心暴露 15个
4. **命名规范** - list/find 统一

### 建议立即执行
- 高优先级 2 项：搜索合并 + Supervisor 精简
- 预期效果：平均暴露工具 47 → 15 (-68%)
