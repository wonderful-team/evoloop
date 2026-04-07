# 基于 Skill 的动态协议加载架构提案

## 提案概述

将固定的 System Prompt 中的 Desktop/Mobile/Browser 协议改为**动态 Skill 加载**机制，由 Supervisor 根据用户意图判断需要哪些协议，只加载必要的技能。

---

## 当前架构 vs 提案架构

### 当前架构 (静态加载)

```
User Request
    ↓
Supervisor (130KB System Prompt 包含所有协议)
    ↓
分析意图 → Route_to Worker
    ↓
Worker (130KB System Prompt 同样包含所有协议)
    ↓
Execute

问题：
- Documenter 任务也携带 Desktop/Mobile 协议 (浪费 55KB)
- 每轮请求都重复传输无用协议
- System Prompt 静态不可变
```

### 提案架构 (动态加载)

```
User Request
    ↓
Supervisor (60KB 精简 System Prompt)
    ↓
分析意图 → 决定需要哪些 Skills
    ↓
Route_to Worker (agent_config.system_instructions + 动态 skills)
    ↓
Worker (60KB Base + 按需加载 Skills)
    ↓
Execute

优势：
- Documenter: 60KB Base + 0KB Skills = 60KB
- Desktop: 60KB Base + 40KB Desktop Skill = 100KB
- Mobile: 60KB Base + 15KB Mobile Skill = 75KB
```

---

## 详细设计

### 1. Skill 格式扩展

```yaml
# skills/roles/desktop_automation/SKILL.md
---
name: Desktop Automation Protocol
description: macOS/Windows desktop control, GUI interaction, keyboard shortcuts
namespace: protocols
type: system_prompt_injection  # 新类型：系统提示词注入
trigger_patterns:
  - "Open {app} on Mac"
  - "Control desktop"
  - "GUI automation"
  - "Click/type on screen"
required_capabilities:
  - macos  # 需要 macOS 环境
  - desktop_control  # 需要 desktop_control 工具
---

# Desktop 协议内容 (当前 40KB 的内容)
## 🖥 Desktop Automation Protocol
...
```

### 2. Supervisor 路由时动态注入

```python
# supervisor.py 路由逻辑
async def route_to_worker(self, user_intent: str, context: dict):
    # 1. 分析用户意图，确定需要哪些协议
    required_protocols = await self._analyze_required_protocols(user_intent)
    
    # 2. 获取协议内容
    protocol_blocks = []
    for protocol in required_protocols:
        skill = await skill_manager.get_skill(f"protocols/{protocol}")
        if skill:
            protocol_blocks.append(skill.instructions)
    
    # 3. 构建动态 system_instructions
    dynamic_instructions = f"""
    ## Your Role: {worker_role}
    {base_instructions}
    
    ## Specialized Protocols
    {'\n\n'.join(protocol_blocks)}
    """
    
    # 4. 路由到 Worker，携带动态指令
    return await self.route_to(
        target="worker",
        agent_config={
            "system_instructions": dynamic_instructions,
            "authorized_tools": self._get_tools_for_protocols(required_protocols)
        }
    )
```

### 3. 协议匹配逻辑

```python
class ProtocolMatcher:
    """匹配用户意图到所需协议"""
    
    PATTERNS = {
        "desktop": {
            "keywords": ["打开", "点击", "桌面", "Mac", "Windows", "截图", "快捷键"],
            "tools": ["desktop_control", "open_app", "screenshot"],
            "required_capabilities": ["macos", "windows"]
        },
        "mobile": {
            "keywords": ["手机", "Android", "点击", "滑动", "App", "扫码"],
            "tools": ["mobile_control", "list_devices"],
            "required_capabilities": ["android"]
        },
        "browser": {
            "keywords": ["浏览器", "网页", "打开网站", "搜索", "点击链接"],
            "tools": ["browser_control", "navigate", "click"],
            "required_capabilities": []
        },
        "code": {
            "keywords": ["代码", "文件", "编辑", "修改", "修复", "实现"],
            "tools": ["read_file", "edit_file", "execute_command"],
            "required_capabilities": []
        }
    }
    
    async def match(self, user_intent: str, available_capabilities: dict) -> list[str]:
        """
        返回需要的协议列表
        例如：["code"] 或 ["browser", "desktop"] (跨应用工作流)
        """
        matched = []
        intent_lower = user_intent.lower()
        
        for protocol, config in self.PATTERNS.items():
            # 1. 检查关键词匹配
            keyword_match = any(kw in intent_lower for kw in config["keywords"])
            
            # 2. 检查环境能力是否满足
            capability_match = all(
                available_capabilities.get(cap) 
                for cap in config["required_capabilities"]
            )
            
            if keyword_match and capability_match:
                matched.append(protocol)
        
        return matched
```

---

## 实施路径

### Phase 1: 提取 Skill (1-2 天)

1. **创建新 Skill 目录结构**
```
app/config/skills/protocols/
├── desktop_automation/
│   ├── SKILL.md (40KB Desktop 协议)
│   └── metadata.yaml
├── mobile_automation/
│   ├── SKILL.md (15KB Mobile 协议)
│   └── metadata.yaml
├── browser_automation/
│   ├── SKILL.md (5KB Browser 协议)
│   └── metadata.yaml
└── base_worker/
    └── SKILL.md (60KB 精简基础协议)
```

2. **迁移协议内容**
```python
# 从 worker.prompt.j2 提取 Desktop 部分
# 转换为 SKILL.md 格式
```

### Phase 2: 修改路由逻辑 (2-3 天)

1. **Supervisor 添加协议匹配**
```python
# app/core/engine/nodes/supervisor.py

class SupervisorNode:
    async def _route(self, state: State):
        user_intent = state.last_human_message
        
        # 新增：动态协议检测
        protocol_matcher = ProtocolMatcher()
        required_protocols = await protocol_matcher.match(
            user_intent, 
            self.available_capabilities
        )
        
        # 加载协议内容
        skill_loader = SkillLoader()
        protocol_content = await skill_loader.load_protocols(required_protocols)
        
        # 构建动态 system_instructions
        dynamic_prompt = self._build_dynamic_prompt(protocol_content)
        
        # 路由到 Worker
        return await self.route_to_worker(
            agent_config={
                "system_instructions": dynamic_prompt,
                "authorized_tools": self._derive_tools(required_protocols)
            }
        )
```

2. **Worker Prompt 精简**
```jinja2
{# worker.prompt.j2 - 精简版 #}
## Your Role: {{ role_name }}
{{ instructions }}

{# 移除：Desktop/Mobile/Browser 协议 #}
{# 移除：环境信息中的详细应用列表 #}

{{ environment_block_minimal }}  {# 精简版 #}

{# 保留：工具使用指南（通用） #}
## 🛠 Tool Usage Guidelines
...

{# 移除：特定平台的详细协议 #}
```

### Phase 3: 测试验证 (1-2 天)

1. **功能测试**
   - Documenter 任务：确认不加载 Desktop/Mobile
   - Desktop 任务：确认正确加载 Desktop 协议
   - 跨应用任务：确认加载多个协议

2. **性能测试**
   - 测量 System Prompt 大小变化
   - 测量请求延迟变化

---

## 风险分析

### 风险 1: 协议匹配不准确

**场景**: 用户说 "打开 Chrome"，意图不明确
- 可能是 "打开 Chrome 浏览器访问网站" → Browser 协议
- 可能是 "在桌面点击 Chrome 图标" → Desktop 协议

**缓解**:
```python
# 歧义检测
if ambiguity_score > threshold:
    # 询问用户或默认加载最可能的协议
    return ["browser", "desktop"]  # 加载多个，让 Worker 自行判断
```

### 风险 2: 协议加载延迟

**场景**: 动态加载 Skill 需要磁盘/DB读取，增加延迟

**缓解**:
```python
# 预加载 + 缓存
protocol_cache = {}

async def load_protocol(name):
    if name not in protocol_cache:
        protocol_cache[name] = await skill_db.load(name)
    return protocol_cache[name]
```

### 风险 3: 任务中途切换场景

**场景**: 开始时是代码任务，中途用户说 "用 Chrome 测试一下"

**缓解**:
- Worker 可以调用 `search_skills` 动态发现需要的技能
- 或者在 Supervisor 重路由时重新评估协议

### 风险 4: 向后兼容性

**场景**: 现有 Skill 依赖固定的 System Prompt 结构

**缓解**:
- 保持 Base Worker Prompt 的核心结构不变
- 只在末尾追加 Specialized Protocols

---

## 预期效果

### 性能提升

| 角色 | 当前 | 优化后 | 节省 |
|------|------|--------|------|
| Documenter | 130KB | 60KB | 70KB (54%) |
| Browser | 130KB | 65KB | 65KB (50%) |
| Desktop | 130KB | 100KB | 30KB (23%) |
| Mobile | 130KB | 75KB | 55KB (42%) |

### 延迟改善 (生产环境)

| 场景 | 当前延迟 | 预期延迟 | 改善 |
|------|---------|---------|------|
| Documenter 190KB | 4min 8s | ~2min | -50% |
| Documenter 130KB | 2min | ~1min | -50% |

### 质量提升

- **更精准的工具授权**: 不再给 Documenter 授权 desktop_control
- **更专注的上下文**: Worker 只看到相关协议，减少干扰
- **更好的可维护性**: 协议作为独立 Skill，易于更新

---

## 替代方案对比

### 方案 A: 当前提案 (动态 Skill 加载)
- **优点**: 精确控制、可扩展、符合现有 Skill 系统
- **缺点**: 实现复杂、需要修改路由逻辑
- **实施成本**: 3-5 天

### 方案 B: 角色特定模板
- **优点**: 简单、快速实施
- **缺点**: 角色硬编码、不够灵活
- **实施成本**: 1 天

### 方案 C: 用户显式指定模式
- **优点**: 完全精确
- **缺点**: 用户体验差
- **实施成本**: 0.5 天

**推荐**: 方案 A (长期收益最大)

---

## 结论

这个提案**技术上可行**，且与 EvoLoop 现有的 Skill 系统高度契合。

### 核心价值
1. **性能**: Documenter 场景减少 70KB 上下文，延迟降低 50%
2. **精确性**: 只加载必要的协议，减少干扰
3. **可扩展性**: 新协议可作为 Skill 动态添加

### 实施建议
1. **短期** (本周): 实施 Phase 1 (提取 Skill) + 简单匹配逻辑
2. **中期** (下周): 完善 ProtocolMatcher，优化缓存
3. **长期** (下月): 考虑 Worker 动态加载 Skill 的能力

### 关键成功因素
- ProtocolMatcher 的准确性需要大量测试
- 需要保持向后兼容性
- 监控生产环境的实际效果

---

**是否建议实施**: ✅ **强烈推荐**

这是一个架构层面的优化，与 EvoLoop 的 Skill 设计理念高度一致，长期收益巨大。
