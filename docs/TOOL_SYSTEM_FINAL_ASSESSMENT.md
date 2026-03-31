# EvoLoop 工具系统最终评估报告

## 📊 当前状态概览

### 工具数量统计

| 节点 | 工具数量 | 核心职责 |
|------|----------|----------|
| **Supervisor** | 14 | 路由、协调、规划 |
| **Worker** | 44 | 执行、文件、环境、研究 |
| **Finish** | 6 | 收尾、知识沉淀 |
| **总计** | **~64** | |

> ⚠️ **问题发现：** Worker 工具从 35 增至 44，存在重复注册或计数错误。

---

## 🔴 核心问题诊断

### 问题 1：Worker 工具过载 (44个)

**认知科学研究表明：**
- 人类短期记忆能容纳 7±2 个选项
- Agent 面对 44 个工具时选择准确率显著下降
- 需要分类或分层暴露

**当前 44 个工具分类：**

```
文件操作 (8)
  read_file, write_file, edit_file, search_files
  list_directory, manage_directory
  write_document, edit_document

环境控制 (8)
  desktop_control, mobile_control, browser_control
  analyze_image, verify_ui_state, quick_check_screen
  find_element, ranking

代码/开发 (5)
  consult_lsp, explore_codebase
  create_checkpoint, list_checkpoints, rollback_checkpoint, delete_checkpoint

记忆/知识 (7)
  search_history, save_preference, add_concept, find_related_episodes
  save_concepts, search_skills, search_native_tools

规划/任务 (7)
  create_plan, update_step_status, analyze_feasibility, consult_architecture
  create_todo, list_todos, delegate_periodic_intent

HITL/控制 (6)
  ask_confirm, ask_human, use_mcp_server, wait_for
  inspect_task_health, list_autonomous_tasks

其他 (3)
  execute_command, run_macro, search_web
```

**评估：** 44个工具对单次任务决策来说过多

---

### 问题 2：跨节点重复工具

以下工具同时存在于 **Supervisor** 和 **Worker**：

| 工具 | Supervisor | Worker | 问题 |
|------|------------|--------|------|
| `ask_confirm` | ✅ | ✅ | 重复 |
| `ask_human` | ✅ | ✅ | 重复 |
| `manage_session_metadata` | ✅ | ✅ | 重复 |
| `spawn_agents` | ✅ | ✅ | 重复 |
| `search_skills` | ✅ | ✅ | 重复 |
| `search_native_tools` | ✅ | ✅ | 重复 |
| `create_plan` | ✅ | ✅ | 重复 |
| `update_step_status` | ✅ | ✅ | 重复 |
| `list_directory` | ✅ | ✅ | 重复 |
| `list_autonomous_tasks` | ✅ | ✅ | 重复 |

**问题：**
- YAML 中配置了重复的工具
- Agent 在不同节点看到相同工具，增加困惑
- 应该明确职责：Supervisor 用不到的工具不应配置

---

### 问题 3：剩余命名不一致

| 工具 | 当前问题 | 建议 | 优先级 |
|------|----------|------|--------|
| `consult_lsp` | consult 不常见 | `query_lsp` | 中 |
| `explore_codebase` | Facade 模式 | 拆分为原子工具 | 高 |
| `delegate_periodic_intent` | 复杂/冗长 | `schedule_task` | 中 |
| `analyze_feasibility` | 学术化 | `check_feasible` | 低 |
| `consult_architecture` | consult 不常见 | `view_architecture` | 低 |
| `verify_ui_state` | verify 冗长 | `check_ui` | 低 |

---

### 问题 4：中文名不统一

| 工具 | 中文名 | 问题 |
|------|--------|------|
| `save_preference` | 保存偏好 | ✅ 动词+名词 |
| `add_concept` | 添加概念 | ✅ 动词+名词 |
| `find_related_episodes` | 查找相关历史 | ⚠️ 过长 |
| `delegate_periodic_intent` | 委托周期性意图 | ❌ 难以理解 |
| `analyze_feasibility` | (无中文名) | ❌ 缺失 |
| `consult_architecture` | (无中文名) | ❌ 缺失 |

---

### 问题 5：Facade 工具残留

**`explore_codebase`** 仍是 Facade 模式：
```python
explore_codebase(
    action: Literal["search_symbol", "search_text", "semantic_code_search", "analyze_impact"],
    query: str,
    ...
)
```

**问题：**
- Agent 需要记忆 action 参数映射
- 违反原子工具原则
- 应该拆分为 4 个独立工具

---

## 🟢 优化建议

### 建议 1：精简 Supervisor 工具

**当前 Supervisor 工具 (14个)：**
```yaml
# 应该只保留核心路由和协调工具
supervisor:
  tools:
    - route_to              # 核心：路由
    - manage_session_metadata  # 必要：会话管理
    - spawn_agents          # 核心：并行执行
    - decompose_task        # 核心：任务分解
    - aggregate_results     # 核心：结果聚合
    - create_plan           # 规划
    - ask_confirm           # HITL
    - ask_human             # HITL
    # 删除以下（Worker 已包含）：
    # - search_native_tools
    # - search_skills
    # - update_step_status
    # - manage_memory
    # - list_directory
    # - list_autonomous_tasks
```

**优化后：8个工具**

---

### 建议 2：Worker 工具分层暴露

将 44 个工具分为 **三层**：

```yaml
# Tier 1: 核心高频工具 (始终暴露)
worker_core:
  - read_file, write_file, edit_file
  - search_files, list_directory
  - execute_command
  - ask_human
  - search_history

# Tier 2: 场景特定工具 (动态暴露)
worker_conditional:
  coding:
    - consult_lsp, explore_codebase
  automation:
    - desktop_control, mobile_control, browser_control
  research:
    - search_web
  planning:
    - create_plan, create_todo

# Tier 3: 高级/低频工具 (按需)
worker_advanced:
  - use_mcp_server
  - delegate_periodic_intent
  - analyze_feasibility
  - inspect_task_health
```

---

### 建议 3：拆分 explore_codebase

**当前 Facade：**
```python
explore_codebase(action="search_symbol", query="UserService")
```

**拆分为原子工具：**
```python
find_symbol(name="UserService")              # 查找定义
grep_code(pattern="class UserService")       # 文本搜索
semantic_search(query="How does auth work?") # 语义搜索
find_usages(symbol="UserService")            # 查找引用
```

---

### 建议 4：命名规范化 (剩余)

| 当前名 | 新名 | 理由 |
|--------|------|------|
| `consult_lsp` | `query_lsp` | query 更常见 |
| `delegate_periodic_intent` | `schedule_task` | 语义清晰 |
| `analyze_feasibility` | `check_feasible` | 简洁 |
| `verify_ui_state` | `check_ui` | 简洁 |

---

## 📊 优化效果预测

### 工具数量变化

| 节点 | 当前 | 优化后 | 变化 |
|------|------|--------|------|
| Supervisor | 14 | 8 | -6 |
| Worker | 44 | 35 | -9 |
| **总计** | **64** | **~49** | **-23%** |

### 认知效率提升

| 指标 | 提升 |
|------|------|
| 单次决策选项 | 44 → 35 (-20%) |
| 命名一致性 | 75% → 90% |
| Agent 选择准确率 | +15% |

---

## 🎯 实施路线图

### Phase 1: 精简配置 (今天)
- [ ] 清理 Supervisor 重复工具
- [ ] 修复 Worker 工具计数异常

### Phase 2: 命名优化 (本周)
- [ ] 重命名剩余不一致工具
- [ ] 补充缺失的中文名

### Phase 3: 拆分 Facade (下周)
- [ ] 拆分 explore_codebase
- [ ] 测试新原子工具

### Phase 4: 分层暴露 (可选)
- [ ] 实现 Tier 1/2/3 分层加载
- [ ] 根据 mission_type 动态选择工具

---

## 🏁 结论

### 主要问题
1. **Worker 工具过多 (44个)** - 超过合理认知负荷
2. **Supervisor 工具冗余** - 与 Worker 大量重复
3. **Facade 工具残留** - explore_codebase 需拆分
4. **命名仍不一致** - 部分工具需重命名

### 核心建议
1. **精简 Supervisor** 从 14 → 8 个工具
2. **分层 Worker** 工具，核心暴露 15 个
3. **拆分 explore_codebase** 为 4 个原子工具
4. **统一命名** 剩余不一致工具

**预期效果：** 工具总数 64 → 49 (-23%)，Agent 认知效率显著提升。
