# 动态协议加载 V2 - 安全方案

## 问题反思

V1 方案的根本缺陷：
1. **硬编码关键词** 无法适应多轮对话的意图演变
2. **剥离现有 Skill 的协议** 破坏了当前能力（如果匹配失败，Worker 看不到协议）
3. **没有利用对话上下文**（已执行的工具、环境状态等）

## 安全方案原则

1. **不破坏现有能力** - Workspace Expert 等 Skill 保留完整协议
2. **零风险回滚** - 新功能是"附加"而非"替换"
3. **基于实际行为** - 用"已使用的工具"而非"关键词"来判断需要哪些协议
4. **渐进式加载** - 对话过程中动态追加协议

## 新方案：基于工具调用的渐进式协议加载

### 核心思路

Worker 开始时只有基础协议。当它**实际调用了某个工具**时，再追加对应的高级协议指导。

```
Round 1: Worker 只有基础协议
   ↓
调用了 desktop_control(action="screenshot")
   ↓
系统追加 Desktop Automation Protocol 到后续 Prompt
   ↓
Round 2: Worker 现在有了 Desktop 协议，能更好地执行
```

### 实现方式

不需要修改 Skill，不需要意图匹配。只需要：

1. **拦截工具调用** - 在 Worker 执行工具时记录
2. **动态追加协议** - 根据已使用的工具，追加对应协议到 Blackboard
3. **Worker 读取 Blackboard** - 在下一轮使用追加的协议

### 代码实现

```python
# app/core/engine/tools/middleware.py

class ProtocolInjectionMiddleware:
    """
    基于工具调用的协议注入中间件
    
    当 Worker 调用特定工具时，自动注入对应的高级协议指导。
    """
    
    # 工具 -> 协议 映射
    TOOL_PROTOCOL_MAP = {
        "desktop_control": "desktop",
        "open_app": "desktop",
        "mobile_control": "mobile",
        "browser_control": "browser",
    }
    
    async def on_tool_call(self, tool_name: str, state: AgentState):
        """工具调用时触发"""
        if tool_name not in self.TOOL_PROTOCOL_MAP:
            return
            
        protocol_name = self.TOOL_PROTOCOL_MAP[tool_name]
        
        # 检查是否已经注入过
        blackboard = state.get("blackboard", {})
        injected_protocols = blackboard.get("injected_protocols", set())
        
        if protocol_name in injected_protocols:
            return
        
        # 加载并注入协议
        from app.core.protocols import ProtocolSkillLoader
        loader = ProtocolSkillLoader()
        skill = await loader.load(protocol_name)
        
        if skill:
            # 追加到 blackboard，Worker 下一轮会看到
            if "dynamic_protocols" not in blackboard:
                blackboard["dynamic_protocols"] = []
            
            blackboard["dynamic_protocols"].append({
                "name": protocol_name,
                "instructions": skill.instructions,
                "injected_at": time.time()
            })
            
            injected_protocols.add(protocol_name)
            blackboard["injected_protocols"] = injected_protocols
            
            logger.info(f"[ProtocolInjection] 已注入 {protocol_name} 协议到 Blackboard")
```

### Worker Prompt 修改

```jinja2
{# worker.prompt.j2 #}

{# 动态追加的协议 #}
{%- if blackboard.dynamic_protocols %}
{% for protocol in blackboard.dynamic_protocols %}
---
{{ protocol.instructions }}
---
{% endfor %}
{%- endif %}

{# 原有的 Knowledge Blocks（包含完整的 Workspace Expert 等）#}
{%- if knowledge_blocks %}
## 📚 Application Knowledge
{% for block in knowledge_blocks %}
{{ block }}
{% endfor %}
{%- endif %}
```

## 优势

1. **不破坏现有能力** - Workspace Expert 等 Skill 完全不变
2. **零风险** - 即使注入失败，Worker 仍然有完整的 Skill 指导
3. **适应多轮对话** - 协议根据实际工具调用追加，不是基于关键词猜测
4. **渐进式** - Worker 越执行，获得的指导越精确
5. **可回滚** - 关闭中间件即可完全恢复原行为

## 启用方式

```bash
# 渐进式协议注入（默认关闭）
export PROGRESSIVE_PROTOCOL_INJECTION=true

# 重启服务
systemctl restart evoloop-backend
```

## 验证方式

查看日志：
```
[Worker] Round 1: 执行 edit_file
[ProtocolInjection] 未触发（非目标工具）

[Worker] Round 2: 执行 desktop_control
[ProtocolInjection] 已注入 desktop 协议到 Blackboard

[Worker] Round 3: 使用追加的 desktop 协议执行
```

## 总结

V2 方案的关键改变：
- **不是预测意图，而是响应行为**
- **不是替换 Skill，而是追加指导**
- **不是静态匹配，而是动态演进**

这个方案安全、渐进、零破坏。
