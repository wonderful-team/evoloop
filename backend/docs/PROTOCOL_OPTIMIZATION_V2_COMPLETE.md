# Worker System Prompt 协议优化 V2 - 完成报告

## 核心改进

**从基于 `role_name` 的判断 → 改为基于 `authorized_tools` 的判断**

### 为什么这样更合理？

1. **`role_name` 是静态标签** - Supervisor 目前给所有任务都分配 "Worker"
2. **`authorized_tools` 是动态决策** - Supervisor 根据用户意图决定授权哪些工具
3. **工具直接反映任务类型** - 授权 `browser_control` 意味着需要做浏览器操作

## 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `app/core/engine/prompts/worker_builder.py` | 新增基于工具的标志计算 |
| `app/config/templates/agents/worker.prompt.j2` | 使用新标志进行条件渲染 |

### 具体修改

**worker_builder.py:**
```python
# 新增：基于授权工具判断需要哪些协议
authorized_tools = self.agent_config.get("tools", [])
has_desktop_tool = any(t in authorized_tools for t in ["desktop_control", "open_app"])
has_mobile_tool = any(t in authorized_tools for t in ["mobile_control", "list_devices"])
has_browser_tool = "browser_control" in authorized_tools

# 传递到模板
template_vars = {
    ...
    "has_desktop_tool": has_desktop_tool,
    "has_mobile_tool": has_mobile_tool,
    "has_browser_tool": has_browser_tool,
}
```

**worker.prompt.j2:**
```jinja2
{# 修改前（基于 role_name）#}
{%- if "Browser" in role_name or "Web" in role_name %}

{# 修改后（基于授权工具）#}
{%- if has_browser_tool %}
```

## 预期效果

### 不同任务类型的协议加载

| 任务类型 | 授权工具 | Desktop | Mobile | Browser |
|----------|----------|---------|--------|---------|
| **纯代码任务** | `read_file`, `edit_file`, `execute_command` | ❌ | ❌ | ❌ |
| **浏览器任务** | `read_file`, `browser_control` | ❌ | ❌ | ✅ |
| **桌面自动化** | `read_file`, `desktop_control` | ✅ | ❌ | ❌ |
| **移动端任务** | `read_file`, `mobile_control` | ❌ | ✅ | ❌ |
| **混合任务** | 所有工具 | ✅ | ✅ | ✅ |

### 大小优化

| 任务类型 | 节省协议 | 估算节省 |
|----------|----------|----------|
| 纯代码任务 | Browser + Desktop | ~45KB |
| 浏览器任务 | Desktop | ~40KB |
| 桌面任务 | Browser | ~5KB |

## 验证方法

查看 Worker 启动日志，确认加载了正确的协议：

```
# 纯代码任务 - 不应有 Browser/Desktop/Mobile 协议
[Worker] 🦎 Hydrating 'Worker'...
[Worker] Protocol flags: browser=False, desktop=False, mobile=False

# 浏览器任务 - 应有 Browser 协议
[Worker] 🦎 Hydrating 'Worker'...
[Worker] Protocol flags: browser=True, desktop=False, mobile=False
```

## 回滚方法

```bash
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend/app/config/templates/agents
cp worker.prompt.j2.backup_20260405 worker.prompt.j2
```

恢复 worker_builder.py：
```bash
git checkout app/core/engine/prompts/worker_builder.py
```

## 优势总结

1. **基于实际决策** - 使用 Supervisor 已经做出的工具授权决策
2. **更准确** - 工具授权反映真实意图，不是猜测
3. **零破坏** - 如果未授权某工具，就不加载对应协议，安全
4. **可扩展** - 未来添加新协议类型很容易

## 注意事项

1. **无需重启** - Jinja2 模板自动热重载
2. **向后兼容** - 如果 `authorized_tools` 为空，所有协议都不加载（安全默认）
3. **监控建议** - 观察是否因为缺少协议导致 Worker 行为异常

---

**实施日期**: 2026-04-05  
**修改者**: Kimi Code CLI  
**状态**: 已完成，基于 `authorized_tools` 的合理方案
