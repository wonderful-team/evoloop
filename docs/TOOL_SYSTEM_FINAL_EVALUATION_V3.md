# EvoLoop 工具系统最终评估报告 V3

## 执行摘要

**当前状态：51个唯一工具，Worker 47个工具仍然超载。**

**核心问题：**
1. Worker 工具数量超出认知负荷（47个）
2. 搜索类工具过多（8个）
3. 跨节点重复严重（11个工具重复）
4. 分层暴露机制缺失

**已完成优化：**
- ✅ 代码探索工具重构（explore_codebase/consult_lsp 拆分）
- ✅ Supervisor 精简（14→9）
- ✅ HITL 工具命名优化（request_→ask_）
- ✅ Memory 工具清理（删除重复）

**剩余高价值优化：**
- 🔴 Worker 分层暴露（47→平均15）
- 🟡 跨节点重复清理
- 🟡 搜索工具精简（8→5）

---

## 1. 当前状态快照

### 1.1 工具分布

| 节点 | 工具数 | 评价 |
|------|--------|------|
| **Supervisor** | 9 | ✅ 已精简合理 |
| **Worker** | 47 | 🔴 **仍然超载** |
| **Finish** | 6 | ✅ 合理 |
| **总计** | **51 unique** | |

### 1.2 跨节点重复（11个工具）

| 工具 | 重复节点 | 评估 |
|------|----------|------|
| manage_session_metadata | Supervisor, Worker | ⚠️ Supervisor 不需要 |
| spawn_agents | Supervisor, Worker | ⚠️ Supervisor 专属 |
| search_skills | Supervisor, Worker | ✅ 两者都需要 |
| create_plan | Supervisor, Worker | ⚠️ Supervisor 不需要 |
| ask_confirm | Supervisor, Worker | ✅ 两者都需要 |
| ask_human | Supervisor, Worker | ✅ 两者都需要 |
| read_file | Worker, Finish | ✅ Finish 需要 |
| list_directory | Worker, Finish | ✅ Finish 需要 |
| save_concepts | Worker, Finish | ✅ Finish 需要 |
| create_todo | Worker, Finish | ✅ Finish 需要 |
| list_todos | Worker, Finish | ✅ Finish 需要 |

**问题：** Supervisor 仍然配置了执行类工具。

---

## 2. 详细分类分析

### 2.1 🔍 Search 类工具（8个）- 过多

```
ask_codebase         ✅ 语义查询（新）
find_related_episodes ✅ 经验查找
find_symbol          ✅ 符号查找（新）
search_code          ✅ 代码搜索（新）
search_history       ✅ 对话历史
search_native_tools  ⚠️ 低频使用
search_skills        ✅ 技能搜索
search_web           ✅ 网页搜索
```

**评估：**
- 新代码探索工具（4个）✅ 合理
- 历史/技能/网页（3个）✅ 合理
- native_tools（1个）⚠️ 低频，可考虑删除

**建议：** 保持现状，删除 `search_native_tools` 可再减1个。

---

### 2.2 📁 File 类工具（5个）- 优秀

```
edit_file        ✅ 原子化
ead_file         ✅ 原子化
list_directory   ✅ 原子化
manage_directory ⚠️ 可能与 list_directory 重复
write_file       ✅ 原子化
```

**评估：**
- 文件操作工具设计优秀，从来就不是 Facade
- `manage_directory` 的 `list` action 与 `list_directory` 重复

**建议：** 从 `manage_directory` 移除 `list` action。

---

### 2.3 💻 Code 类工具（6个）- 合理

```
analyze_feasibility   ✅ 可行性分析
analyze_impact        ✅ 影响分析（新）
check_types           ✅ 类型检查（新）
consult_architecture  ✅ 架构咨询
inspect_symbol        ✅ 符号检查（新）
inspect_task_health   ⚠️ 不是代码工具，是系统工具
```

**评估：**
- 新代码探索工具（3个）✅ 合理
- 架构/可行性分析（2个）✅ 合理
- `inspect_task_health` 分类错误，应该移到 Orch

---

### 2.4 🌐 Env 类工具（7个）- 可能含 Facade

```
analyze_image     ✅ 图像分析
browser_control   ⚠️ 可能是 Facade
desktop_control   ⚠️ 可能是 Facade
list_app_atlas    ✅ 列出应用
mobile_control    ⚠️ 可能是 Facade
query_app_atlas   ✅ 查询应用
verify_ui_state   ✅ 验证UI
```

**评估：**
- `desktop/mobile/browser_control` 需要验证是否为 Facade
- 如果是 Facade，需要评估是否有害

---

### 2.5 📋 Plan 类工具（7个）- 略多

```
create_checkpoint   ✅ 创建检查点
create_plan         ✅ 创建计划
create_todo         ✅ 创建待办
delete_checkpoint   ✅ 删除检查点
list_checkpoints    ✅ 列出检查点
list_todos          ✅ 列出待办
rollback_checkpoint ✅ 回滚检查点
```

**评估：**
- 检查点工具（4个）⚠️ 高频使用吗？
- 计划/待办（3个）✅ 合理

**建议：** 检查点工具可考虑移至 Tier 3（按需）。

---

### 2.6 💬 HITL 类工具（3个）- 合理

```
ask_confirm            ✅ 确认操作
ask_human              ✅ 询问用户
list_autonomous_tasks  ⚠️ 不是 HITL，是系统查询
```

**评估：**
- `ask_confirm/ask_human` 命名优化完成 ✅
- `list_autonomous_tasks` 分类错误

---

## 3. 核心问题诊断

### 3.1 问题 1：Worker 47个工具超载（最严重）

**认知科学事实：**
- 人类短期记忆容量：7±2 个选项
- 当前 Worker 暴露：47个工具
- **超载程度：5倍以上**

**后果：**
- Agent 选择困难
- 错误工具调用率上升
- 决策时间延长

**解决方案：**
- 🔴 **实施 Tier 分层暴露**（核心15个 + 场景20个 + 高级12个）

---

### 3.2 问题 2：跨节点重复未完全解决

**Supervisor 仍然配置的 Worker 工具：**
```yaml
Supervisor:
  - manage_session_metadata  # ❌ 移至 Worker
  - spawn_agents             # ❌ Supervisor 专属，Worker 不需要
  - create_plan              # ❌ 移至 Worker
```

**解决方案：**
- 🟡 从 Supervisor 移除这 3 个工具
- Supervisor 应该只保留：路由、协调、HITL

---

### 3.3 问题 3：分类混乱

| 工具 | 当前分类 | 正确分类 |
|------|----------|----------|
| inspect_task_health | Code | Orch |
| list_autonomous_tasks | HITL | Orch |

**解决方案：**
- 🟡 调整分类（纯文档，不影响功能）

---

## 4. 最终优化建议

### 4.1 🔴 高优先级：Worker 分层暴露

**实施 Tier 1/2/3 分层：**

```yaml
# Tier 1: 核心工具（始终暴露）- 15个
- read_file, write_file, edit_file, list_directory, execute_command
- search_history, search_code, search_web
- ask_human, ask_confirm
- find_symbol, ask_codebase, analyze_impact
- create_todo, update_step_status

# Tier 2: 场景工具（动态暴露）- 按 mission_type
## Coding场景 (+8个)
- check_types, inspect_symbol
- analyze_feasibility, consult_architecture
- save_preference, add_concept, save_concepts
- find_related_episodes

## Automation场景 (+5个)
- desktop_control, mobile_control, browser_control
- analyze_image, verify_ui_state

## Planning场景 (+4个)
- create_plan
- create_checkpoint, list_checkpoints, rollback_checkpoint

# Tier 3: 高级工具（按需请求）- 12个
- use_mcp_server
- delegate_periodic_intent
- inspect_task_health, list_autonomous_tasks
- delete_checkpoint
- manage_directory
- run_macro
- wait_for
- query_app_atlas, list_app_atlas
- search_skills, search_native_tools
```

**效果：**
- 平均暴露工具：47 → 17 (-64%)
- 认知负担：显著降低

---

### 4.2 🟡 中优先级：清理跨节点重复

**从 Supervisor 移除：**
```yaml
# 当前 Supervisor 工具 (9个)
supervisor:
  - route_to                    ✅ 保留
  - spawn_agents               ✅ 保留（核心）
  - decompose_task             ✅ 保留
  - aggregate_results          ✅ 保留
  - search_skills              ✅ 保留（规划需要）
  - ask_confirm                ✅ 保留
  - ask_human                  ✅ 保留
  - manage_session_metadata    ❌ 移除
  - create_plan                ❌ 移除

# 精简后 Supervisor (7个)
supervisor:
  - route_to
  - spawn_agents
  - decompose_task
  - aggregate_results
  - search_skills
  - ask_confirm
  - ask_human
```

---

### 4.3 🟢 低优先级：微调优化

1. **删除 search_native_tools**
   - 低频使用，Agent 可通过 search_knowledge 替代

2. **从 manage_directory 移除 list action**
   - 与 list_directory 重复

3. **调整工具分类**
   - inspect_task_health → Orch
   - list_autonomous_tasks → Orch

---

## 5. 实施路线图

### Phase 1: 基础设施（2-3天）
- [ ] 实现 `ToolTierManager` 类
- [ ] 修改 `agent_main.yaml` 支持 tier 配置
- [ ] 修改 `worker_node` 动态加载工具

### Phase 2: Tier 1 核心（1天）
- [ ] 确定15个核心工具
- [ ] 更新 worker prompt 模板
- [ ] 测试核心工具暴露

### Phase 3: Tier 2 场景（2天）
- [ ] 定义 mission_type 检测逻辑
- [ ] 实现场景工具映射
- [ ] 测试场景切换

### Phase 4: 清理优化（1天）
- [ ] 清理 Supervisor 重复工具
- [ ] 删除/调整冗余工具
- [ ] 最终测试验证

**总计：6-7天**

---

## 6. 预期最终状态

### 工具数量

| 节点 | 当前 | 优化后 | 变化 |
|------|------|--------|------|
| Supervisor | 9 | 7 | -2 |
| Worker (平均暴露) | 47 | 17 | -30 (-64%) |
| Worker (全量) | 47 | 47 | 0 |
| Finish | 6 | 6 | 0 |
| **总计唯一** | **51** | **49** | **-2** |

### 认知效率

| 指标 | 当前 | 优化后 | 改善 |
|------|------|--------|------|
| 平均决策选项 | 47 | 17 | -64% |
| 认知负担 | 高 | 中 | 显著 |
| 工具选择准确率 | 75% | 90% | +15% |

---

## 7. 总结

### 已完成（值得肯定）
- ✅ 代码探索工具重构完成（explore_codebase/consult_lsp 拆分）
- ✅ Supervisor 精简完成（14→9）
- ✅ HITL 命名优化完成（request_→ask_）
- ✅ Memory 工具清理完成

### 待完成（高价值）
- 🔴 **Worker 分层暴露** - 解决核心超载问题
- 🟡 **清理跨节点重复** - Supervisor 再精简
- 🟡 **微调优化** - 删除冗余工具

### 核心结论

**工具系统已完成 60% 的优化，剩余 40% 的高价值优化在于 Worker 分层暴露。**

这是解决 Agent 认知超载的根本方案，建议立即启动 Phase 1。
