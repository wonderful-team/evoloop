# 协议优化 V2 - 架构分析

## 当前架构状态

### 1. Tool Authorization 链

```
Supervisor (agent_main.yaml)
    ↓
route_to(authorized_tools=[...])  ← Supervisor 应该在这里指定
    ↓
SignalDispatcher._handle_route_to()
    ↓
execution_ticket["agent_config"]["tools"] = authorized_tools
    ↓
WorkerNode.__call__()
    ↓
tool_manager.get_node_tools("worker", state)
    ↓ [ToolManager 第98-104行]
if dynamic_tools:  # 如果有授权工具列表
    过滤工具，只保留 allowed 列表中的
    ↓
WorkerPromptBuilder.build()
    ↓
检查 authorized_tools 决定协议标志
    ↓
worker.prompt.j2 条件渲染
```

### 2. 关键代码位置

**ToolManager 过滤逻辑** (`app/core/tools/manager.py:98-104`):
```python
# Strict Supervisor Allowlist Enforcement
if dynamic_tools and node_name != "supervisor":
    allowed = set(dynamic_tools)
    combined_map = {k: v for k, v in combined_map.items() if k in allowed}
```

**WorkerPromptBuilder 协议判断** (`app/core/engine/prompts/worker_builder.py`):
```python
authorized_tools = self.agent_config.get("tools", [])
has_desktop_tool = any(t in authorized_tools for t in ["desktop_control", "open_app"])
has_mobile_tool = any(t in authorized_tools for t in ["mobile_control", "list_devices"])
has_browser_tool = "browser_control" in authorized_tools
```

**Template 条件渲染** (`app/config/templates/agents/worker.prompt.j2`):
```jinja2
{%- if has_browser_tool %}
## 🌐 Browser Automation Protocol
...
{%- endif %}
{%- if has_desktop_tool %}
## 🖥 Desktop Automation Protocol
...
{%- endif %}
{%- if has_mobile_tool %}
## 📱 Mobile Automation Protocol
...
{%- endif %}
```

## 问题诊断

### 您日志中显示的问题

从您提供的日志可以看到 Worker System Prompt 包含了：
- Browser Automation Protocol
- Mobile Automation Protocol

这意味着：
1. `has_browser_tool = True`
2. `has_mobile_tool = True`（因为 `has_android` 为 True）

### 根因分析

**可能性 1**: Supervisor 没有传入 `authorized_tools`
- 如果 `authorized_tools` 为 `None` 或空列表
- `ToolManager` 不会进行过滤（`if dynamic_tools` 条件不满足）
- Worker 获得所有工具 → 渲染所有协议

**可能性 2**: Supervisor 传入了完整的工具列表
- 即使纯代码任务，Supervisor 也可能授权了所有工具
- 这可能是因为系统设计如此，或者 Supervisor 没有正确判断任务类型

## 验证方法

### 1. 查看日志（已添加）

现在 Worker 启动时会输出：
```
[WorkerPromptBuilder] Protocol flags: browser=X, desktop=X, mobile=X | authorized_tools=[...]
```

观察实际传入的 `authorized_tools` 是什么。

### 2. 检查 Supervisor 行为

查看 Supervisor 的日志，看它调用 `route_to` 时传入的 `authorized_tools`：
```
[Dispatcher] ✅ Routing to: worker | Reason: ...
```

后面应该能看到 `authorized_tools` 的内容。

## 解决方案

### 方案 A: 如果 Supervisor 没有传入 `authorized_tools`

需要修改 Supervisor 的 prompt，确保它总是传入最小化的工具列表。

当前 Supervisor prompt 已经说了：
```
When calling `route_to("worker", ...)`, you MUST specify `authorized_tools`.
```

但可能 LLM 没有遵守。可以添加更强制性的约束。

### 方案 B: 在 Worker 中强制过滤（当前已实现）

Worker 已经在 `ToolManager` 中根据 `authorized_tools` 过滤工具。

如果 `authorized_tools` 正确传入，系统会工作正常。

### 方案 C: 添加默认工具集（备选）

如果 Supervisor 没有传入 `authorized_tools`，Worker 可以使用默认的最小工具集：

```python
# 在 WorkerNode.__call__ 中
if not agent_config.get("tools"):
    # 默认只授权代码工具
    agent_config["tools"] = [
        "read_file", "write_file", "edit_file", "multiedit_file", 
        "apply_patch_file", "execute_command", "list_directory"
    ]
```

## 当前部署状态

✅ **已完成**:
- `worker.prompt.j2` 使用 `has_browser_tool` / `has_desktop_tool` / `has_mobile_tool` 进行条件渲染
- `worker_builder.py` 基于 `authorized_tools` 计算这些标志
- 添加了调试日志

⏳ **待验证**:
- Supervisor 是否正确传入 `authorized_tools`
- 纯代码任务是否不再加载 Browser/Mobile 协议

## 下一步

1. **部署并观察日志** - 查看实际传入的 `authorized_tools`
2. **如果 Supervisor 没有传入** - 需要修复 Supervisor 的 prompt 或逻辑
3. **如果传入正确但协议仍加载** - 检查 ToolManager 的过滤逻辑

---

**结论**: 当前架构已经支持基于授权工具的协议加载。问题可能在于 Supervisor 是否正确使用了 `authorized_tools` 参数。
