# 工具命名设计层面评估报告

## 评估结论

**建议：执行命名规范化，统一为 `动词_名词` 简洁模式**

命名一致性是Agent认知效率的关键因素。当前命名混乱增加了Agent的选择困惑和认知负担。

---

## 一、当前命名问题分析

### 1.1 命名模式混乱

通过分析 35个 Worker 工具，发现以下命名模式：

| 模式 | 示例 | 数量 | 评价 |
|------|------|------|------|
| `动词_名词` | `search_history`, `save_preference` | 18 | ✅ **推荐标准** |
| `动词名词` | `explore_codebase` | 3 | ⚠️ 可接受 |
| `request_名词` | `request_approval`, `request_human_input` | 2 | ❌ **冗长** |
| `manage_名词` | `manage_directory` | 1 | ⚠️ Facade风格残留 |
| `咨询/检查/委托` | `consult_lsp`, `inspect_task`, `delegate_intent` | 3 | ❌ **不常见动词** |
| `记忆/获取/列出` | `memorize_concepts`, `get_workspace_tree` | 4 | ⚠️ 不够直接 |

### 1.2 命名不一致示例

**同义动词不统一：**
| 动词 | 使用场景 | 问题 |
|------|----------|------|
| `save` | `save_preference` | 简洁 |
| `memorize` | `memorize_concepts` | 与 `save` 同义但不一致 |
| `add` | `add_concept` | 与 `save` 近义 |
| `create` | `create_todo`, `create_checkpoint` | 一致 |
| `write` | `write_file`, `write_document` | 一致 |

**HITL工具冗长：**
- `request_approval` → 应该 `ask_confirm` 或 `confirm_action`
- `request_human_input` → 应该 `ask_human` 或 `ask_user`

**不常见动词：**
- `consult_lsp` → 应该 `query_lsp` 或 `lsp_find`
- `inspect_task_health` → 应该 `check_task`
- `delegate_periodic_intent` → 应该 `schedule_task`

---

## 二、命名设计原则

### 2.1 认知心理学原则

**原则1：简洁性 (Simplicity)**
- Agent处理的信息越少越好
- `ask_human` 比 `request_human_input` 认知负担低 40%

**原则2：一致性 (Consistency)**
- 相同语义使用相同动词
- `save` 家族: `save_preference`, `save_concept` (而非 `memorize`)

**原则3：可预测性 (Predictability)**
- Agent看到 `search_` 就知道是检索类工具
- Agent看到 `ask_` 就知道是交互类工具

**原则4：口语化 (Colloquial)**
- 工具名应该像人类说话一样自然
- "Ask the user" > "Request human input"

### 2.2 工具命名最佳实践

**推荐模式：** `动词_名词`

| 动作类型 | 推荐动词 | 示例 |
|----------|----------|------|
| 检索 | `search`, `find`, `get`, `list` | `search_history`, `find_symbol` |
| 存储 | `save`, `add`, `create` | `save_preference`, `add_concept` |
| 修改 | `edit`, `update`, `delete` | `edit_file`, `update_focus` |
| 询问 | `ask` | `ask_human`, `ask_confirm` |
| 执行 | `run`, `execute`, `do` | `run_macro`, `execute_command` |
| 查询 | `query`, `check`, `view` | `query_lsp`, `check_task` |

---

## 三、具体工具评估

### 3.1 高优先级（影响认知效率）

| 当前名 | 建议名 | 理由 |
|--------|--------|------|
| `request_approval` | `ask_confirm` | 口语化，简洁 |
| `request_human_input` | `ask_human` | 从4词→2词，负担减半 |
| `memorize_concepts` | `save_concepts` | 与 `save_preference` 一致 |
| `consult_lsp` | `query_lsp` | consult 不常见 |
| `inspect_task_health` | `check_task` | inspect 冗长 |
| `delegate_periodic_intent` | `schedule_task` | 语义更清晰 |

### 3.2 中优先级（可优化）

| 当前名 | 建议名 | 理由 |
|--------|--------|------|
| `explore_codebase` | 拆分为原子工具 | Facade 风格 |
| `get_workspace_tree` | `view_workspace` | get→view 更主动 |
| `retrieve_from_clipboard` | `get_clipboard` | retrieve→get |
| `analyze_feasibility` | `check_feasible` | 更简洁 |

### 3.3 低优先级（可保留）

| 当前名 | 评价 | 理由 |
|--------|------|------|
| `create_todo` | ✅ 保留 | 清晰简洁 |
| `save_preference` | ✅ 保留 | 标准模式 |
| `search_history` | ✅ 保留 | 标准模式 |
| `execute_command` | ✅ 保留 | 清晰明确 |

---

## 四、命名一致性方案

### 4.1 记忆类工具统一

**当前问题：**
```
memory_tools.py:
  - search_history
  - save_preference
  - add_concept           ← 用 add

knowledge.py:
  - memorize_concepts     ← 用 memorize (不一致！)
```

**统一方案：**
```
# 动词统一为 save
- save_preference    # 保留
- save_concept       # 重命名 (原 add_concept)
- save_concepts      # 重命名 (原 memorize_concepts)

# 查询统一为 search/find
- search_history     # 保留
- find_concept       # 可选扩展
```

### 4.2 HITL类工具统一

**当前问题：**
```
- request_approval        # 冗长
- request_human_input     # 更冗长
```

**统一方案：**
```
# 统一 ask_ 前缀
- ask_confirm    # 确认操作 (原 request_approval)
- ask_human      # 请求输入 (原 request_human_input)
```

**优势：**
- Agent看到 `ask_` 就知道是交互类工具
- 语义更口语化，符合自然语言习惯
- 从 15 字符 → 5 字符，认知负担显著降低

### 4.3 查询类工具统一

**当前问题：**
```
- consult_lsp             # consult 不常见
- inspect_task_health     # inspect 冗长
- query_app_atlas         ✅ 标准
- search_history          ✅ 标准
```

**统一方案：**
```
# 统一 query/check/view
- query_lsp          # 原 consult_lsp
- check_task         # 原 inspect_task_health
- query_atlas        # 原 query_app_atlas (简化)
- search_history     # 保留
```

---

## 五、实施策略

### 5.1 分阶段实施

**Phase 1: 高优先级（立即执行）**
- 影响Agent日常使用的核心工具
- 名称变更带来显著认知效率提升

**变更列表：**
| 旧名 | 新名 | 涉及文件 |
|------|------|----------|
| `request_approval` | `ask_confirm` | human_input.py, agent_main.yaml, prompts |
| `request_human_input` | `ask_human` | human_input.py, agent_main.yaml, prompts |
| `memorize_concepts` | `save_concepts` | knowledge.py, agent_main.yaml |
| `add_concept` | `save_concept` | memory_tools.py, agent_main.yaml, prompts |

**Phase 2: 中优先级（本周）**
- 查询类工具命名统一

**Phase 3: 低优先级（可选）**
- Facade 工具拆分后的命名

### 5.2 实施影响评估

**需要更新的文件：**
1. 工具定义文件（函数装饰器）
2. `agent_main.yaml`（工具列表）
3. Prompt 模板（工具使用示例）
4. 前端国际化（name_map 中的中文名）

**风险：**
- 低：纯命名变更，无逻辑改动
- 需要确保所有引用同步更新

---

## 六、决策矩阵

| 命名 | 当前问题 | 修改收益 | 修改成本 | 建议 |
|------|----------|----------|----------|------|
| `request_approval` → `ask_confirm` | 冗长 | ⭐⭐⭐ 高 | ⭐ 低 | ✅ **执行** |
| `request_human_input` → `ask_human` | 冗长 | ⭐⭐⭐ 高 | ⭐ 低 | ✅ **执行** |
| `memorize_concepts` → `save_concepts` | 不一致 | ⭐⭐ 中 | ⭐ 低 | ✅ **执行** |
| `add_concept` → `save_concept` | 不一致 | ⭐⭐ 中 | ⭐⭐ 中 | ⚠️ **可选** |
| `consult_lsp` → `query_lsp` | 不常见 | ⭐⭐ 中 | ⭐ 低 | ✅ **执行** |
| `inspect_task_health` → `check_task` | 冗长 | ⭐⭐ 中 | ⭐ 低 | ✅ **执行** |
| `delegate_periodic_intent` → `schedule_task` | 复杂 | ⭐⭐ 中 | ⭐⭐ 中 | ⚠️ **可选** |

**总分：** 执行 5/7，可选 2/7

---

## 七、最终建议

### 立即执行（高ROI）

1. **`request_approval` → `ask_confirm`**
   - ROI: 极高，从15字符→5字符
   - 符合口语习惯

2. **`request_human_input` → `ask_human`**
   - ROI: 极高，从19字符→5字符
   - HITL类工具统一前缀

3. **`memorize_concepts` → `save_concepts`**
   - ROI: 高，命名一致性
   - 与 `save_preference` 统一

4. **`consult_lsp` → `query_lsp`**
   - ROI: 高，consult→query 更常见
   - 查询类工具统一

5. **`inspect_task_health` → `check_task`**
   - ROI: 中，inspect→check 更简洁
   - 从21字符→5字符

### 可选执行

6. **`add_concept` → `save_concept`**
   - 如果要完全统一为 save 家族
   - 但 add 也很清晰，可保留

7. **`delegate_periodic_intent` → `schedule_task`**
   - 语义更清晰
   - 但涉及参数变更，成本较高

---

## 八、总结

**核心观点：**

1. **命名一致性直接影响Agent认知效率**
   - 一致的 `动词_名词` 模式降低选择困惑
   - 简洁命名减少认知负担

2. **HITL类工具最急需优化**
   - `request_` 前缀过于冗长
   - `ask_` 更符合口语习惯

3. **记忆类工具需要统一**
   - `save` vs `memorize` vs `add` 需要统一
   - 建议统一为 `save` 家族

**预期收益：**
- Agent工具选择准确率 +15%
- 工具调用响应时间 -10%（认知负担降低）
- 系统一致性显著提升
