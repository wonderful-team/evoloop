# Worker 工具分层设计

## 核心原则

> Agent 不应该同时看到 47 个工具，就像程序员不应该同时看到 IDE 的所有功能。

分层目标：**核心 15 个，场景 20 个，高级 12 个**

---

## 第一层：核心工具 (Tier 1) - 始终暴露

**原则：** 任何任务都需要的基础能力，15个工具

```yaml
tier_1_core:
  # 文件操作 (5) - 任何任务都需要
  - read_file
  - write_file
  - edit_file
  - list_directory
  - execute_command
  
  # 基础查询 (3) - 高频使用
  - search_history      # 查对话历史
  - search_code         # 查代码
  - search_web          # 查网页
  
  # HITL (2) - 必备
  - ask_human
  - ask_confirm
  
  # 基础探索 (3) - 代码理解
  - find_symbol         # 找定义
  - ask_codebase        # 语义查询
  - analyze_impact      # 影响分析
  
  # 任务管理 (2) - 规划执行
  - create_todo
  - update_step_status
```

**Agent 看到的 Prompt：**
```
Your Core Tools (always available):
📁 Files: read_file, write_file, edit_file, list_directory, execute_command
🔍 Search: search_history, search_code, search_web
💬 Human: ask_human, ask_confirm
🔎 Code: find_symbol, ask_codebase, analyze_impact
✅ Tasks: create_todo, update_step_status
```

---

## 第二层：场景工具 (Tier 2) - 动态暴露

**原则：** 根据 Supervisor 分配的 `mission_type` 动态加载

### 2.1 Coding 场景 (+8个工具)

```yaml
mission_type: "coding"
additional_tools:
  # 代码检查
  - check_types
  - inspect_symbol
  
  # 代码架构
  - consult_architecture
  - analyze_feasibility
  
  # 知识管理
  - save_preference
  - add_concept
  - save_concepts
  - find_related_episodes
```

**Agent 看到的 Prompt：**
```
Mission: Coding Task
Additional Tools Available:
🔍 Code Quality: check_types, inspect_symbol
🏗️ Architecture: consult_architecture, analyze_feasibility
🧠 Knowledge: save_preference, add_concept, save_concepts, find_related_episodes
```

### 2.2 Automation 场景 (+5个工具)

```yaml
mission_type: "automation"
additional_tools:
  - desktop_control
  - mobile_control
  - browser_control
  - analyze_image
  - verify_ui_state
```

### 2.3 Research 场景 (+3个工具)

```yaml
mission_type: "research"
additional_tools:
  - search_skills       # 查技能
  - search_native_tools # 查工具
  - run_macro          # 执行宏
```

### 2.4 Planning 场景 (+4个工具)

```yaml
mission_type: "planning"
additional_tools:
  - create_plan
  - create_checkpoint
  - list_checkpoints
  - rollback_checkpoint
```

---

## 第三层：高级工具 (Tier 3) - 按需请求

**原则：** 低频、复杂或需要特殊权限的工具

```yaml
tier_3_advanced:
  # MCP 扩展
  - use_mcp_server
  
  # 调度/定时
  - delegate_periodic_intent
  
  # 系统监控
  - inspect_task_health
  - list_autonomous_tasks
  
  # Atlas 应用图谱
  - query_app_atlas
  - list_app_atlas
  
  # 检查点管理（删除/高级操作）
  - delete_checkpoint
  
  # 目录管理
  - manage_directory
  
  # 动态工具创建
  - create_python_tool
  
  # 工作区工具
  - get_workspace_tree
  - stash_to_clipboard
  - retrieve_from_clipboard
```

**使用方式：**
```python
# Agent 明确请求
"I need to connect to an external MCP server"
→ System exposes: use_mcp_server

"I want to check system health"
→ System exposes: inspect_task_health, list_autonomous_tasks
```

---

## 完整分层映射

### 按任务类型的工具暴露

| 任务类型 | Tier 1 (核心) | Tier 2 (场景) | Tier 3 (按需) | 总计 |
|----------|---------------|---------------|---------------|------|
| **通用** | 15 | - | - | **15** |
| **Coding** | 15 | +8 | +? | **~20** |
| **Automation** | 15 | +5 | +? | **~18** |
| **Research** | 15 | +3 | +? | **~16** |
| **Planning** | 15 | +4 | +? | **~17** |

**平均暴露工具数：47 → 17 (-64%)**

---

## 实施架构

### 3.1 Supervisor 路由时指定 Tier

```python
# supervisor_node.py
async def route_to_worker(state, config):
    mission_type = analyze_mission(state["messages"])
    
    execution_ticket = {
        "mission_type": mission_type,  # "coding" | "automation" | "research" | ...
        "tier_2_enabled": get_tier_2_tools(mission_type),
        "tier_3_available": True,  # Agent 可以请求
    }
    
    return {
        "next_node": "worker",
        "execution_ticket": execution_ticket
    }
```

### 3.2 Worker 加载时过滤工具

```python
# worker_node.py
async def worker_node(state, config):
    ticket = state.get("execution_ticket", {})
    mission_type = ticket.get("mission_type", "general")
    
    # 1. 加载 Tier 1 (核心)
    tools = get_tier_1_tools()
    
    # 2. 加载 Tier 2 (场景)
    if mission_type == "coding":
        tools.extend(get_coding_tools())
    elif mission_type == "automation":
        tools.extend(get_automation_tools())
    # ...
    
    # 3. Tier 3 按需加载
    if ticket.get("tier_3_enabled"):
        tools.extend(get_requested_tier_3_tools(ticket))
    
    # 4. 构建 Prompt
    prompt = build_worker_prompt(tools, mission_type)
    
    # 5. 执行
    return await execute_with_tools(state, tools, prompt)
```

### 3.3 Prompt 构建

```jinja2
{# worker.prompt.j2 #}

## Your Tools

### Core Tools (Always Available)
{% for tool in tier_1_tools %}
- {{ tool.name }}: {{ tool.description }}
{% endfor %}

{% if tier_2_tools %}
### Mission-Specific Tools ({{ mission_type }})
{% for tool in tier_2_tools %}
- {{ tool.name }}: {{ tool.description }}
{% endfor %}
{% endif %}

{% if tier_3_available %}
### Advanced Tools (Request if needed)
You can request access to: {{ tier_3_tool_names | join(", ") }}
To request, say: "I need to use [tool_name]"
{% endif %}
```

---

## 分层效果对比

### 当前：47个工具一次性暴露

```
Agent 看到：
📁 read_file, write_file, edit_file, list_directory, manage_directory
🔍 search_history, search_code, search_web, search_skills, search_native_tools
💬 ask_human, ask_confirm
🔎 find_symbol, ask_codebase, analyze_impact, check_types, inspect_symbol
🏗️ consult_architecture, analyze_feasibility
📦 create_todo, list_todos, update_step_status
💾 create_checkpoint, list_checkpoints, rollback_checkpoint, delete_checkpoint
🖥️ desktop_control, mobile_control, browser_control, analyze_image
... 还有 20+ 个工具

Agent: (😵 我该用哪个？)
```

### 分层后：平均17个工具

```
Mission: Coding Task

Your Tools:

Core (Always):
📁 read_file, write_file, edit_file, list_directory, execute_command
🔍 search_history, search_code, search_web
💬 ask_human, ask_confirm
🔎 find_symbol, ask_codebase, analyze_impact
✅ create_todo, update_step_status

Mission-Specific (Coding):
🔍 Code Quality: check_types, inspect_symbol
🏗️ Architecture: consult_architecture, analyze_feasibility
🧠 Knowledge: save_preference, add_concept

Advanced (Request if needed):
You can request: use_mcp_server, delegate_periodic_intent, ...

Agent: (😊 清晰！)
```

---

## 实施路线图

### Phase 1: 基础设施 (2天)
- [ ] 在 `execution_ticket` 中添加 `mission_type` 和 `tier_2_enabled`
- [ ] 创建 `ToolTierManager` 类管理分层
- [ ] 修改 `worker_node` 支持动态工具加载

### Phase 2: Tier 1 核心 (1天)
- [ ] 确定15个核心工具列表
- [ ] 更新 `worker.prompt.j2` 支持分层显示
- [ ] 测试核心工具暴露

### Phase 3: Tier 2 场景 (2天)
- [ ] 定义 `mission_type` 枚举
- [ ] 实现场景工具映射
- [ ] 添加场景检测逻辑

### Phase 4: Tier 3 按需 (1天)
- [ ] 实现工具请求机制
- [ ] Agent 可以请求访问高级工具

---

## 预期收益

| 指标 | 当前 | 分层后 | 改善 |
|------|------|--------|------|
| 平均暴露工具 | 47 | 17 | **-64%** |
| 认知负担 | 高 | 中 | **显著** |
| 工具选择时间 | 长 | 短 | **-50%** |
| 错误工具调用 | 多 | 少 | **-30%** |

---

## 风险与缓解

| 风险 | 缓解方案 |
|------|----------|
| Agent 需要 Tier 3 但未暴露 | Agent 可以主动请求，Supervisor 审批 |
| 场景分类错误 | 默认使用 Tier 1 + 常用 Tier 2 |
| Prompt 复杂 | 清晰的分层标题和说明 |

---

## 结论

分层设计将 Worker 工具从 **47个一次性暴露** 改为 **平均17个分层暴露**：

- **Tier 1 (核心)：** 15个，任何任务都暴露
- **Tier 2 (场景)：** 按 `mission_type` 动态暴露
- **Tier 3 (高级)：** 按需请求

**这是解决 Worker 工具超载的根本方案。**
