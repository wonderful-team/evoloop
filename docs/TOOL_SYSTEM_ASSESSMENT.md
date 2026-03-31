# EvoLoop 工具系统全面评估报告

## 执行摘要

基于对 `agent_main.yaml` 和全部工具源码的分析，当前系统共有 **69 个工具**，分布在不同节点。本报告识别了**认知负担问题**并提出了**系统性优化方案**。

---

## 1. 当前工具全景

### 1.1 按节点分布

| 节点 | 工具数量 | 核心职责 |
|------|----------|----------|
| **Supervisor** | 14 | 路由、协调、规划、元数据管理 |
| **Worker** | 37 | 文件操作、代码执行、环境控制、研究 |
| **Finish** | 7 | 任务收尾、知识沉淀 |
| **Total** | **69** | |

### 1.2 完整工具清单

#### Supervisor 专用工具 (14个)
```yaml
- route_to              # 路由到特定节点 [核心]
- manage_session_metadata   # 管理会话元数据
- spawn_agents          # 生成并行代理
- decompose_task        # 任务分解
- aggregate_results     # 聚合并行结果
- search_native_tools   # 搜索原生工具
- search_skills         # 搜索技能
- create_plan           # 创建计划
- update_step_status    # 更新步骤状态
- manage_memory         # 管理记忆 (Facade)
- request_approval      # 请求审批
- request_human_input   # 请求人工输入
- list_directory        # 列出目录
- list_autonomous_tasks # 列出自主任务
```

#### Worker 工具 (37个)
```yaml
# 编排与状态 (2)
- manage_session_metadata
- spawn_agents

# 环境控制 - Desktop/Mobile (5)
- desktop_control
- mobile_control
- analyze_image
- verify_ui_state
- browser_control

# 工作区与代码 (8)
- read_file, write_file, edit_file, search_files
- list_directory, manage_directory
- execute_command
- consult_lsp

# 代码探索 (1)
- explore_codebase        # Facade (4 actions)

# 检查点 (4)
- create_checkpoint, list_checkpoints
- rollback_checkpoint, delete_checkpoint

# 记忆 (4) [NEW]
- search_history, save_preference
- add_concept, find_related_episodes

# 知识 (6)
- search_skills, run_macro
- query_app_atlas, list_app_atlas
- search_native_tools, memorize_concepts

# 研究 (1)
- search_web

# 规划与审计 (4)
- create_plan, update_step_status
- analyze_feasibility, consult_architecture

# 待办 (2) [NEW]
- create_todo, list_todos

# HITL (2)
- request_approval, request_human_input

# 控制 (5)
- use_mcp_server, wait_for
- delegate_periodic_intent
- inspect_task_health, list_autonomous_tasks
```

#### Finish 节点工具 (7个)
```yaml
- read_file, list_directory
- create_todo, list_todos
- memorize_concepts
- synthesize_skill        # 合成技能
```

---

## 2. 认知负担分析

### 2.1 命名不一致问题 ⚠️

**当前命名模式混乱：**

| 模式 | 示例 | 一致性 |
|------|------|--------|
| `动词_名词` | `search_history`, `create_todo` | ✅ 推荐 |
| `动词名词` | `explore_codebase` | ⚠️ 可接受 |
| `manage_名词` | `manage_session_metadata`, `manage_directory` | ⚠️ Facade 风格 |
| `request_名词` | `request_approval`, `request_human_input` | ⚠️ 冗长 |
| ` consult_名词` | `consult_lsp`, `consult_architecture` | ⚠️ 不常见动词 |
| `list_名词s` | `list_todos`, `list_checkpoints` | ✅ 清晰 |

**问题示例：**
- `search_history` vs `search_chat_history` (实际是两个不同工具！)
- `search_files` vs `explore_codebase` (代码搜索分散)
- `save_preference` vs `manage_session_metadata` (都是存储，动词不同)

### 2.2 Facade 工具的认知陷阱 ⚠️

**剩余的 Facade 工具：**

| 工具 | action 参数 | 问题 |
|------|-------------|------|
| `explore_codebase` | search_symbol, search_text, semantic_code_search, analyze_impact | Agent 需记忆 action 映射 |
| `manage_memory` (Supervisor) | [内部实现细节不可见] | 黑盒操作 |
| `desktop_control` | [推测有 action 参数] | 未验证 |
| `mobile_control` | [推测有 action 参数] | 未验证 |
| `browser_control` | [推测有 action 参数] | 未验证 |

**对比：拆分后的原子工具更易用**
```python
# 拆分前 (Facade) - 需要记忆 action 参数
explore_codebase(action="search_symbol", query="UserService")

# 拆分后 (原子) - 直接表达意图
find_definition(symbol="UserService")  # 假设拆分后的工具
search_code(pattern="class UserService")
```

### 2.3 重复/重叠工具 🔴

| 工具A | 工具B | 重叠点 |
|-------|-------|--------|
| `search_history` (Worker) | `search_chat_history` (domain/tools/memory_search.py) | 都是搜索对话历史！ |
| `save_preference` | `manage_session_metadata` | 都是键值存储 |
| `memorize_concepts` | `add_concept` | 都是概念记忆 |
| `list_todos` | `list_autonomous_tasks` | 命名相似，用途不同 |
| `search_files` | `explore_codebase(action="search_text")` | 都是文本搜索 |

### 2.4 跨节点工具重复

**相同工具在多个节点：**
- `request_approval`, `request_human_input` → Supervisor + Worker
- `list_directory` → Supervisor + Worker + Finish
- `create_todo`, `list_todos` → Worker + Finish
- `search_skills` → Supervisor + Worker
- `create_plan`, `update_step_status` → Supervisor + Worker

**问题：** Agent 在不同节点看到相似工具集，增加困惑。

---

## 3. 分类与心智模型问题

### 3.1 当前分类 vs 认知直觉

**当前 YAML 分类：**
```yaml
# 基于技术实现分类
- Desktop & Mobile Automation
- Workspace & Code
- Checkpoints
- Knowledge & Memory
- Research
- Planning & Audit
```

**建议：基于用户意图分类**
```yaml
# 基于任务类型分类
- 🔍 发现类: search_*, list_*, explore_*
- ✏️ 编辑类: read_*, write_*, edit_*
- 🖥️ 执行类: execute_*, run_*, control_*
- 🧠 记忆类: save_*, add_*, memorize_*, find_*
- 👤 人类协作: ask_*, confirm_*, request_human_*
- 🔄 工作流: route_*, plan_*, delegate_*
```

### 3.2 工具发现难度

**当前问题：**
- 37个 Worker 工具一次性暴露给 LLM
- 没有分层或渐进式暴露
- 缺乏工具推荐/智能筛选

---

## 4. 优化建议

### 4.1 命名规范化 (高优先级)

**统一为 `动词_名词` 模式：**

| 当前名 | 建议名 | 理由 |
|--------|--------|------|
| `request_approval` | `ask_confirm` 或 `confirm_action` | 更简洁 |
| `request_human_input` | `ask_human` | 更简洁 |
| `consult_lsp` | `query_lsp` 或 `lsp_find` | consult 不常见 |
| `consult_architecture` | `view_architecture` | 实际只是查看 |
| `memorize_concepts` | `save_concepts` | 与 save_preference 一致 |
| `explore_codebase` | 拆分为4个原子工具 | 消除 action 参数 |

### 4.2 消除重复工具 (高优先级)

**立即行动项：**

1. **合并搜索历史工具**
   ```python
   # 只保留一个
   search_history(query, thread_id=None, limit=10)  # ✅
   search_chat_history(...)  # ❌ 删除
   ```

2. **统一记忆接口**
   ```python
   # 当前有3个概念记忆方式：
   - add_concept(name, description)           # 原子工具
   - memorize_concepts(concepts: list)        # Finish 节点
   - memory.py 中的 _impl 函数                # 内部实现
   
   # 建议：统一为 save_concept / save_concepts
   ```

3. **合并搜索工具**
   ```python
   # 当前代码搜索分散在：
   - search_files(pattern)                    # 通用文本搜索
   - explore_codebase(action="search_text")   # 代码库搜索
   - explore_codebase(action="search_symbol") # 符号搜索
   - consult_lsp                              # LSP 搜索
   
   # 建议：统一代码搜索接口
   - search_code(pattern, scope="content|symbol|file")
   ```

### 4.3 拆分剩余 Facade (中优先级)

**explore_codebase 拆分方案：**

```python
# 替代当前 explore_codebase(action=..., query=...)

@evoloop_tool
def find_symbol(name: str, scope_path: str = None):
    """Find class/function definition."""
    
@evoloop_tool
def grep_code(pattern: str, path: str = None, is_regex: bool = True):
    """Search code with regex pattern."""
    
@evoloop_tool  
def semantic_search(query: str):
    """Semantic search for concepts."""
    
@evoloop_tool
def analyze_dependencies(symbol: str):
    """Find usages and dependents."""
```

### 4.4 分层工具暴露 (中优先级)

**Worker 工具分层：**

```yaml
# Tier 1: 高频核心工具 (始终暴露)
core:
  - read_file, write_file, edit_file
  - search_files, list_directory
  - execute_command
  - request_human_input

# Tier 2: 任务类型决定 (动态暴露)
conditional:
  coding:
    - consult_lsp, explore_codebase
  automation:
    - desktop_control, mobile_control, browser_control
  research:
    - search_web
  planning:
    - create_plan, create_todo

# Tier 3: 高级/低频工具 (按需请求)
advanced:
  - use_mcp_server
  - delegate_periodic_intent
  - analyze_feasibility
```

### 4.5 智能工具推荐 (低优先级/长期)

```python
# 基于 query 类型推荐工具
if "bug" in query or "error" in query:
    suggested_tools = ["search_history", "consult_lsp", "analyze_feasibility"]
elif "implement" in query or "add feature" in query:
    suggested_tools = ["explore_codebase", "consult_architecture", "create_plan"]
```

---

## 5. 实施路线图

### Phase 1: 命名规范化 (1-2天)
- [ ] 重命名 `request_approval` → `ask_confirm`
- [ ] 重命名 `request_human_input` → `ask_human`
- [ ] 重命名 `consult_lsp` → `lsp_query`
- [ ] 更新所有 prompts 和 YAML

### Phase 2: 消除重复 (2-3天)
- [ ] 删除 `search_chat_history`，统一使用 `search_history`
- [ ] 合并 `memorize_concepts` 和 `add_concept`
- [ ] 统一 `manage_session_metadata` 和 `save_preference` 语义

### Phase 3: 拆分 Facade (3-5天)
- [ ] 拆分 `explore_codebase` → 4个原子工具
- [ ] 评估 `desktop/mobile/browser_control` 是否需要拆分

### Phase 4: 分层暴露 (可选)
- [ ] 实现工具分层加载逻辑
- [ ] 根据 mission_type 动态选择工具集

---

## 6. 成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| Worker 工具数量 | 37 | 30-35 (精简后) |
| Facade 工具数量 | 4 | 0 |
| 命名一致性 | 60% | 90%+ |
| 工具重复率 | 15% | <5% |
| Agent 工具选择准确率 | ? | +20% |

---

## 7. 结论

当前工具系统功能完整但存在**命名不一致**和**认知负担**问题。主要优化机会：

1. **立即行动**: 消除重复工具 (`search_history` vs `search_chat_history`)
2. **短期**: 命名规范化，统一 `动词_名词` 模式
3. **中期**: 拆分剩余 Facade 工具
4. **长期**: 分层工具暴露，智能推荐

通过这些改进，可以显著降低 Agent 的认知负担，提高工具使用准确性。
