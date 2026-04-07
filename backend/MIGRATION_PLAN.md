# EvoLoop 动态协议加载 - 安全迁移实施计划

## 项目概述

将静态 System Prompt 改为动态 Skill 加载机制，预期 Documenter 场景减少 70KB 上下文，生产延迟降低 50%。

---

## 风险评估矩阵

| 风险项 | 影响 | 概率 | 缓解策略 |
|--------|------|------|----------|
| 意图匹配错误 | Worker 缺少必要协议 | 中 | 1. 灰度发布 2. 快速回滚 3. 匹配置信度阈值 |
| Worker 启动失败 | 任务无法执行 | 低 | 1. 保留原 prompt 作为 fallback 2. 详细日志 3. 自动降级 |
| 性能退化 | 延迟增加 | 低 | 1. Skill 预加载 2. 缓存机制 3. 实时性能监控 |
| 数据不一致 | 协议内容错误 | 低 | 1. 内容校验 2. 版本控制 3. A/B 对比测试 |

---

## 阶段规划

### Phase 0: 准备与基础设施 (Day 1-2)

#### 0.1 创建功能开关
```python
# app/core/config.py 新增
class FeatureFlags:
    """功能开关配置"""
    DYNAMIC_PROTOCOL_LOADING = os.getenv("DYNAMIC_PROTOCOL_LOADING", "false").lower() == "true"
    PROTOCOL_LOADER_CACHE_TTL = int(os.getenv("PROTOCOL_LOADER_CACHE_TTL", "300"))  # 5分钟
    PROTOCOL_MATCHER_THRESHOLD = float(os.getenv("PROTOCOL_MATCHER_THRESHOLD", "0.7"))  # 置信度阈值
```

#### 0.2 创建 Skill 目录结构
```bash
mkdir -p app/config/skills/protocols/{desktop,mobile,browser}
touch app/config/skills/protocols/__init__.py
```

#### 0.3 创建监控指标
```python
# app/core/monitoring/protocol_loader_metrics.py
from prometheus_client import Counter, Histogram, Gauge

protocol_load_duration = Histogram(
    'protocol_load_duration_seconds',
    'Time spent loading protocol skills',
    ['protocol_name']
)

protocol_match_accuracy = Gauge(
    'protocol_match_accuracy',
    'Accuracy of protocol matching',
    ['scenario']
)

prompt_size_savings = Counter(
    'prompt_size_savings_bytes',
    'Bytes saved by dynamic loading',
    ['role_name']
)
```

**验收标准**:
- [ ] 功能开关可以正常读取环境变量
- [ ] 目录结构创建完成
- [ ] 监控指标可以在 Prometheus 中看到

---

### Phase 1: Skill 提取与验证 (Day 2-4)

#### 1.1 提取 Desktop Automation Skill

**源文件**: `app/config/templates/agents/worker.prompt.j2` (Line 183-337)

**创建文件**: `app/config/skills/protocols/desktop/SKILL.md`

```markdown
---
name: Desktop Automation Protocol
namespace: protocols
type: system_prompt_injection
trigger_patterns:
  - "打开 {app}"
  - "点击"
  - "桌面"
  - "截图"
  - "Mac"
  - "快捷键"
required_capabilities:
  - macos
required_tools:
  - desktop_control
  - open_app
  - screenshot
version: 1.0.0
---

## 🖥 Desktop Automation Protocol

(从 worker.prompt.j2 复制过来的 150 行内容...)
```

#### 1.2 提取 Mobile Automation Skill

**源文件**: `app/config/templates/agents/worker.prompt.j2` (Line 338-352)

**创建文件**: `app/config/skills/protocols/mobile/SKILL.md`

#### 1.3 提取 Browser Automation Skill

**源文件**: `app/config/templates/agents/worker.prompt.j2` (Line 173-182)

**创建文件**: `app/config/skills/protocols/browser/SKILL.md`

#### 1.4 创建 Protocol Loader

```python
# app/core/protocols/loader.py
import hashlib
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import yaml

logger = logging.getLogger(__name__)

@dataclass
class ProtocolSkill:
    name: str
    namespace: str
    version: str
    trigger_patterns: list[str]
    required_capabilities: list[str]
    required_tools: list[str]
    instructions: str
    content_hash: str  # 用于缓存校验

class ProtocolSkillLoader:
    """协议 Skill 加载器，带缓存机制"""
    
    _cache: dict[str, ProtocolSkill] = {}
    _cache_timestamp: dict[str, float] = {}
    
    def __init__(self, cache_ttl: int = 300):
        self.cache_ttl = cache_ttl
        self.skills_dir = Path("app/config/skills/protocols")
    
    async def load(self, protocol_name: str) -> Optional[ProtocolSkill]:
        """加载协议 Skill，优先使用缓存"""
        
        # 检查缓存
        if self._is_cache_valid(protocol_name):
            logger.debug(f"Using cached protocol: {protocol_name}")
            return self._cache[protocol_name]
        
        # 从磁盘加载
        skill_path = self.skills_dir / protocol_name / "SKILL.md"
        if not skill_path.exists():
            logger.error(f"Protocol skill not found: {skill_path}")
            return None
        
        try:
            content = skill_path.read_text(encoding='utf-8')
            skill = self._parse_skill(content)
            
            # 更新缓存
            self._cache[protocol_name] = skill
            self._cache_timestamp[protocol_name] = time.time()
            
            logger.info(f"Loaded protocol skill: {protocol_name} (v{skill.version})")
            return skill
            
        except Exception as e:
            logger.error(f"Failed to load protocol {protocol_name}: {e}")
            return None
    
    def _parse_skill(self, content: str) -> ProtocolSkill:
        """解析 SKILL.md 文件"""
        # 分离 frontmatter 和 content
        if content.startswith('---'):
            _, frontmatter, instructions = content.split('---', 2)
            metadata = yaml.safe_load(frontmatter)
        else:
            metadata = {}
            instructions = content
        
        # 计算内容 hash
        content_hash = hashlib.md5(instructions.encode()).hexdigest()
        
        return ProtocolSkill(
            name=metadata.get('name', 'Unknown'),
            namespace=metadata.get('namespace', 'protocols'),
            version=metadata.get('version', '1.0.0'),
            trigger_patterns=metadata.get('trigger_patterns', []),
            required_capabilities=metadata.get('required_capabilities', []),
            required_tools=metadata.get('required_tools', []),
            instructions=instructions.strip(),
            content_hash=content_hash
        )
    
    def _is_cache_valid(self, protocol_name: str) -> bool:
        """检查缓存是否有效"""
        if protocol_name not in self._cache:
            return False
        
        timestamp = self._cache_timestamp.get(protocol_name, 0)
        return (time.time() - timestamp) < self.cache_ttl
    
    async def preload_all(self) -> None:
        """预加载所有协议 Skill"""
        for protocol_dir in self.skills_dir.iterdir():
            if protocol_dir.is_dir():
                await self.load(protocol_dir.name)
```

**验收标准**:
- [ ] 3个协议 Skill 文件创建完成
- [ ] ProtocolSkillLoader 可以正确加载和缓存
- [ ] 单元测试通过 (test_protocol_loader.py)

---

### Phase 2: Protocol Matcher 开发 (Day 4-6)

#### 2.1 创建意图匹配器

```python
# app/core/protocols/matcher.py
import re
import logging
from typing import List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class MatchResult:
    protocol_name: str
    confidence: float  # 0.0 - 1.0
    matched_keywords: List[str]
    reason: str

class ProtocolMatcher:
    """协议匹配器 - 分析用户意图匹配所需协议"""
    
    # 关键词权重配置
    KEYWORD_PATTERNS = {
        "desktop": {
            "keywords": {
                "打开": 0.8, "点击": 0.9, "桌面": 0.9, "Mac": 0.8, "macOS": 0.8,
                "截图": 0.7, "快捷键": 0.8, "聚焦": 0.6, "切换": 0.5,
                "WeChat": 0.6, "Chrome": 0.5, "微信": 0.6, "谷歌浏览器": 0.5,
                "桌面控制": 0.9, "GUI": 0.8, "坐标": 0.7
            },
            "required_capabilities": ["macos"],
            "required_tools": ["desktop_control", "open_app", "screenshot"]
        },
        "mobile": {
            "keywords": {
                "手机": 0.9, "Android": 0.9, "点击": 0.7, "滑动": 0.8,
                "App": 0.7, "扫码": 0.9, "闲鱼": 0.8, "淘宝": 0.8,
                "抖音": 0.8, "微信": 0.7, "截图": 0.6, "移动": 0.8,
                "ADB": 0.9, "设备": 0.6, "屏幕": 0.5
            },
            "required_capabilities": ["android"],
            "required_tools": ["mobile_control", "list_devices"]
        },
        "browser": {
            "keywords": {
                "浏览器": 0.9, "网页": 0.9, "打开网站": 0.9, "搜索": 0.7,
                "点击链接": 0.8, "导航": 0.8, "访问": 0.7, "URL": 0.8,
                "Chrome": 0.7, "Safari": 0.7, "网页截图": 0.8,
                "DOM": 0.9, "元素": 0.7, "选择器": 0.8
            },
            "required_capabilities": [],
            "required_tools": ["browser_control", "navigate", "click"]
        },
        "code": {
            "keywords": {
                "代码": 0.9, "文件": 0.8, "编辑": 0.9, "修改": 0.9,
                "修复": 0.9, "实现": 0.9, "重构": 0.9, "写": 0.7,
                "bug": 0.9, "功能": 0.7, "函数": 0.8, "类": 0.8,
                "测试": 0.7, "运行": 0.6, "命令": 0.6
            },
            "required_capabilities": [],
            "required_tools": ["read_file", "edit_file", "execute_command"]
        }
    }
    
    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold
    
    async def match(
        self, 
        user_intent: str, 
        available_capabilities: dict
    ) -> List[MatchResult]:
        """
        分析用户意图，返回匹配的协议列表
        
        Args:
            user_intent: 用户输入/意图描述
            available_capabilities: 当前环境可用能力 { "macos": True, "android": False }
        
        Returns:
            按置信度排序的匹配结果列表
        """
        results = []
        intent_lower = user_intent.lower()
        
        for protocol, config in self.KEYWORD_PATTERNS.items():
            # 1. 检查环境能力是否满足
            if not self._check_capabilities(config["required_capabilities"], available_capabilities):
                logger.debug(f"Skipping {protocol}: required capabilities not met")
                continue
            
            # 2. 计算匹配得分
            score, matched_keywords = self._calculate_score(intent_lower, config["keywords"])
            
            # 3. 生成匹配理由
            reason = self._generate_reason(protocol, matched_keywords, score)
            
            if score > 0:
                results.append(MatchResult(
                    protocol_name=protocol,
                    confidence=score,
                    matched_keywords=matched_keywords,
                    reason=reason
                ))
        
        # 按置信度排序
        results.sort(key=lambda x: x.confidence, reverse=True)
        
        # 过滤低于阈值的
        filtered = [r for r in results if r.confidence >= self.threshold]
        
        # 如果没有高置信度匹配，但有多个中置信度，全部返回
        if not filtered and results:
            # 返回前 2 个，让 Worker 自行判断
            return results[:2]
        
        return filtered
    
    def _calculate_score(
        self, 
        intent: str, 
        keywords: dict[str, float]
    ) -> Tuple[float, List[str]]:
        """计算匹配得分"""
        matched = []
        total_score = 0.0
        
        for keyword, weight in keywords.items():
            if keyword.lower() in intent:
                matched.append(keyword)
                total_score += weight
        
        # 归一化得分 (0-1)
        max_possible_score = sum(keywords.values())
        normalized_score = min(total_score / max_possible_score * 2, 1.0)  # *2 是因为通常只匹配部分关键词
        
        return normalized_score, matched
    
    def _check_capabilities(
        self, 
        required: List[str], 
        available: dict
    ) -> bool:
        """检查环境能力是否满足"""
        return all(available.get(cap, False) for cap in required)
    
    def _generate_reason(
        self, 
        protocol: str, 
        keywords: List[str], 
        score: float
    ) -> str:
        """生成匹配理由（用于日志和调试）"""
        if score >= 0.8:
            return f"Strong match: detected {len(keywords)} keywords ({', '.join(keywords[:3])})"
        elif score >= 0.5:
            return f"Medium match: detected {len(keywords)} keywords ({', '.join(keywords[:2])})"
        else:
            return f"Weak match: detected {len(keywords)} keywords"


class ConservativeProtocolMatcher(ProtocolMatcher):
    """保守模式匹配器 - 用于灰度发布阶段"""
    
    def __init__(self):
        super().__init__(threshold=0.8)  # 更高的阈值
    
    async def match(self, user_intent: str, available_capabilities: dict) -> List[MatchResult]:
        """保守匹配：如果不确定，返回 code 协议作为安全选项"""
        results = await super().match(user_intent, available_capabilities)
        
        # 如果没有高置信度匹配，默认返回 code
        if not results:
            logger.info(f"No high-confidence match for intent, defaulting to 'code': {user_intent[:50]}")
            return [MatchResult(
                protocol_name="code",
                confidence=0.5,
                matched_keywords=[],
                reason="No strong match detected, defaulting to code (conservative mode)"
            )]
        
        return results
```

#### 2.2 创建集成模块

```python
# app/core/protocols/__init__.py
"""
动态协议加载系统

使用方法:
    from app.core.protocols import ProtocolLoader, ProtocolMatcher
    
    # 加载协议
    loader = ProtocolLoader()
    desktop_skill = await loader.load("desktop")
    
    # 匹配协议
    matcher = ProtocolMatcher()
    protocols = await matcher.match("打开 Chrome 浏览器", {"macos": True})
"""

from .loader import ProtocolSkillLoader, ProtocolSkill
from .matcher import ProtocolMatcher, ConservativeProtocolMatcher, MatchResult

__all__ = [
    "ProtocolSkillLoader",
    "ProtocolSkill", 
    "ProtocolMatcher",
    "ConservativeProtocolMatcher",
    "MatchResult"
]
```

**验收标准**:
- [ ] ProtocolMatcher 单元测试覆盖 90%+
- [ ] 测试用例覆盖常见意图匹配场景
- [ ] 匹配准确性在测试集上达到 85%+

---

### Phase 3: Worker Prompt 精简 (Day 6-8)

#### 3.1 创建新的精简 Worker Prompt

```jinja2
{# app/config/templates/agents/worker_v2.prompt.j2 #}
## Your Role: {{ role_name }}
{{ instructions }}

{% if plan -%}
## 📋 Active Plan
**{{ plan.title }}** — {{ 'APPROVED' if plan.approved else 'PENDING APPROVAL' }}
{%- for s in plan.steps %}
{{ s.index }}. {{ '✅' if s.status == 'done' else '⏳' }} {{ s.title }}
{%- endfor %}
{%- endif %}

## 🧠 Execution Protocol
- **Action-Oriented**: Use your Thinking space for brief reasoning, then call the appropriate tool immediately.
- **Purposeful Tooling**: Every tool call must have a clear intent.
- **Adaptive Strategy**: If a tool call does not produce the expected result, analyze why and adjust your approach.
{% if is_subtask %}
- **Single-Shot Alignment**: Since you are a sub-agent, focus on fulfilling YOUR specific Mission Ticket criteria.
{% endif %}
- **Blackboard Management**: You can update the shared state (Blackboard) by including '[BLACKBOARD: key=value]' in your thinking or response.

## 📚 Memory Usage Guidelines
When using remembered information from `recall` or `search_history`:
- **Memories capture past state**: They reflect what was true when saved, not necessarily now
- **Always verify before recommending**: If a memory names a specific file, function, or pattern, verify it still exists
- **Trust current state over memory**: If a memory conflicts with what you see in files, trust the files

### 🎯 Role-Based Tool Priority
{# 移除了详细的 Desktop/Mobile/Browser 协议，改为通用指引 #}
- **Primary**: Use tools relevant to your mission:
  - For coding/file tasks: `read_file`, `write_file`, `edit_file`, `execute_command`
  - For web tasks: `browser_control`, `read_url_content`
  - For mobile tasks: `mobile_control`, `analyze_image`
  - For search tasks: `search_web`
- **Secondary (All roles)**: `search_skills`, `recall`, `search_history`, `save_preference`

  **Memory Tools:**
  - `remember(content, context)`: Save important information
  - `recall(query)`: Search previously remembered information
  - `search_history(query)`: Find earlier messages in current conversation

{# 动态协议注入点 #}
{% if dynamic_protocols %}
## 📖 Specialized Protocols
{% for protocol in dynamic_protocols %}
---
{{ protocol.instructions }}
---
{% endfor %}
{%- endif %}

{{ environment_block }}
{% include 'fragments/blackboard.j2' %}

## ⚙️ System Info
Project ID: {{ project_id }}
{%- if sys_info.cwd %}
CWD: {{ sys_info.cwd }}
{%- endif %}

{# 移除了详细的 Desktop/Mobile/Browser 协议部分 #}

## 🛠 Operation Protocol
1. **Understand**: Read the Mission Ticket and identify required outcomes.
2. **Check for Learned Skills**: **RECOMMENDED** — Call `search_skills` for your **Mission Goal**.
3. **Consult Knowledge**: Review any matched SOPs.
4. **Observe & Act**: Use tools via the formal function calling system.
5. **Verify**: Confirm the desired transition.

## ✅ Completion Verification Protocol
After EVERY tool execution, you MUST check against the **Acceptance Criteria** in your Mission Ticket:
1. **Did the action satisfy the criteria?**
   - YES → Provide final answer as plain text **IMMEDIATELY**
   - NO → Proceed to next step with a different approach

{%- if knowledge_blocks %}
## 📚 Application Knowledge
{% for block in knowledge_blocks %}
{{ block }}
{% endfor %}
{%- endif %}

## 📝 Final Reporting
Once the criteria in the Mission Ticket are met:
- **DO NOT** generate a detailed summary report
- **DO** provide a brief confirmation (1-2 sentences max)

## 🧭 Reading Your Mission Ticket
The Supervisor has handed you an **ExecutionTicket**. It contains:
- `topic` / `reason` — the core objective in plain language.
- `focus_paths` — 1–3 files/directories identified as critical.
- `acceptance_criteria` — measurable outcomes that define "done".
```

#### 3.2 创建 Prompt Builder V2

```python
# app/core/engine/prompts/worker_builder_v2.py
import logging
from typing import List, Optional
from app.core.protocols import ProtocolSkillLoader, ProtocolMatcher
from app.utils import render_template

logger = logging.getLogger(__name__)

class WorkerPromptBuilderV2:
    """Worker Prompt 构建器 V2 - 支持动态协议加载"""
    
    def __init__(self):
        self.protocol_loader = ProtocolSkillLoader()
        self.protocol_matcher = ProtocolMatcher()
        self.use_v2 = FeatureFlags.DYNAMIC_PROTOCOL_LOADING
    
    async def build(
        self,
        role_name: str,
        user_intent: str,
        available_capabilities: dict,
        base_context: dict,
    ) -> str:
        """
        构建 Worker System Prompt
        
        如果功能开关关闭，回退到 V1 版本
        """
        if not self.use_v2:
            logger.debug("Using V1 prompt builder (feature flag off)")
            from .worker_builder import WorkerPromptBuilder
            v1_builder = WorkerPromptBuilder()
            return await v1_builder.build(**base_context)
        
        logger.info(f"Building V2 prompt for role: {role_name}")
        
        # 1. 匹配所需协议
        matched_protocols = await self.protocol_matcher.match(
            user_intent, 
            available_capabilities
        )
        
        logger.info(f"Matched protocols: {[p.protocol_name for p in matched_protocols]}")
        
        # 2. 加载协议内容
        dynamic_protocols = []
        for match in matched_protocols:
            skill = await self.protocol_loader.load(match.protocol_name)
            if skill:
                dynamic_protocols.append(skill)
        
        # 3. 渲染模板
        template_vars = {
            **base_context,
            "dynamic_protocols": dynamic_protocols,
            "use_dynamic_loading": True,
        }
        
        prompt = render_template("agents/worker_v2.prompt.j2", **template_vars)
        
        # 4. 记录指标
        original_size = 130000  # ~130KB 原始大小
        new_size = len(prompt.encode('utf-8'))
        savings = original_size - new_size
        
        logger.info(
            f"Prompt size: {new_size/1024:.1f}KB "
            f"(saved {savings/1024:.1f}KB vs V1)"
        )
        
        return prompt
```

**验收标准**:
- [ ] worker_v2.prompt.j2 渲染结果正确
- [ ] 与 V1 对比，Documenter 场景减少 50KB+
- [ ] 功能开关关闭时，正确回退到 V1

---

### Phase 4: Supervisor 集成 (Day 8-10)

#### 4.1 修改 Supervisor 路由逻辑

```python
# app/core/engine/nodes/supervisor.py

class SupervisorNode:
    async def _route_with_protocol_detection(self, state: State):
        """增强版路由：支持动态协议检测"""
        
        user_intent = state.last_human_message
        
        # 获取环境能力
        from app.core.environment import get_awakened_state
        awakened_state = get_awakened_state()
        capabilities = {
            "macos": awakened_state.macos is not None if awakened_state else False,
            "android": bool(awakened_state.android_devices) if awakened_state else False,
        }
        
        # 使用 V2 Builder（如果开启）
        if FeatureFlags.DYNAMIC_PROTOCOL_LOADING:
            from app.core.engine.prompts.worker_builder_v2 import WorkerPromptBuilderV2
            
            builder = WorkerPromptBuilderV2()
            dynamic_instructions = await builder.build(
                role_name=self._detect_role(user_intent),
                user_intent=user_intent,
                available_capabilities=capabilities,
                base_context=self._prepare_base_context(state)
            )
            
            # 构建 agent_config
            agent_config = {
                "system_instructions": dynamic_instructions,
                "authorized_tools": await self._derive_authorized_tools(
                    user_intent, capabilities
                )
            }
        else:
            # 回退到原有逻辑
            agent_config = await self._build_agent_config_legacy(state)
        
        # 路由到 Worker
        return await self.route_to_worker(
            target="worker",
            reason=user_intent,
            agent_config=agent_config
        )
```

#### 4.2 添加 A/B 测试逻辑

```python
# app/core/protocols/ab_testing.py
import random
import logging

logger = logging.getLogger(__name__)

class ProtocolLoaderABTest:
    """A/B 测试：动态加载 vs 静态加载"""
    
    def __init__(self, v2_ratio: float = 0.1):
        """
        Args:
            v2_ratio: 使用 V2 的比例 (0.0 - 1.0)
        """
        self.v2_ratio = v2_ratio
    
    def should_use_v2(self, session_id: str) -> bool:
        """根据 session_id 决定是否使用 V2"""
        # 使用哈希确保同一个 session 始终分配到同一组
        hash_val = int(hashlib.md5(session_id.encode()).hexdigest(), 16)
        bucket = hash_val % 100
        
        return bucket < (self.v2_ratio * 100)
    
    async def compare_results(self, session_id: str, v2_result: dict, v1_result: dict):
        """对比 V1 和 V2 的结果"""
        # 记录到监控系统
        logger.info(
            f"A/B Test Result for {session_id}: "
            f"V2_prompt_size={v2_result.get('prompt_size')}, "
            f"V1_prompt_size={v1_result.get('prompt_size')}, "
            f"V2_latency={v2_result.get('latency')}, "
            f"V1_latency={v1_result.get('latency')}"
        )
```

**验收标准**:
- [ ] Supervisor 可以正确调用 V2 Builder
- [ ] A/B 测试逻辑正确工作
- [ ] 灰度发布可以控制 10% 流量

---

### Phase 5: 测试与验证 (Day 10-12)

#### 5.1 单元测试

```python
# tests/unit/core/protocols/test_matcher.py

class TestProtocolMatcher:
    async def test_match_desktop_intent(self):
        matcher = ProtocolMatcher()
        results = await matcher.match(
            "帮我打开 WeChat 并截图",
            {"macos": True, "android": False}
        )
        
        assert len(results) > 0
        assert results[0].protocol_name == "desktop"
        assert results[0].confidence > 0.7
    
    async def test_match_code_intent(self):
        matcher = ProtocolMatcher()
        results = await matcher.match(
            "修复这个 bug",
            {"macos": True, "android": False}
        )
        
        assert any(r.protocol_name == "code" for r in results)

class TestProtocolLoader:
    async def test_load_and_cache(self):
        loader = ProtocolSkillLoader(cache_ttl=300)
        
        # 第一次加载
        skill1 = await loader.load("desktop")
        assert skill1 is not None
        
        # 第二次加载（应该来自缓存）
        skill2 = await loader.load("desktop")
        assert skill2 is skill1  # 同一对象
```

#### 5.2 集成测试

```python
# tests/integration/test_dynamic_protocol_loading.py

class TestDynamicProtocolLoading:
    async def test_documenter_prompt_size(self):
        """验证 Documenter 场景 Prompt 大小减少"""
        builder = WorkerPromptBuilderV2()
        
        prompt = await builder.build(
            role_name="Documenter",
            user_intent="分析这个项目的代码结构",
            available_capabilities={"macos": True, "android": False},
            base_context={...}
        )
        
        size_kb = len(prompt.encode('utf-8')) / 1024
        assert size_kb < 80, f"Prompt too large: {size_kb}KB"
```

#### 5.3 生产环境验证清单

```markdown
## 灰度发布验证清单

### 1. 功能验证
- [ ] Documenter 任务正常执行
- [ ] Desktop 任务正常执行
- [ ] Mobile 任务正常执行（如果有 Android 设备）
- [ ] 跨应用工作流正常

### 2. 性能验证
- [ ] Prompt 大小符合预期 (Documenter < 80KB)
- [ ] 请求延迟降低 30%+
- [ ] 无内存泄漏

### 3. 错误监控
- [ ] 无 Protocol Load 错误
- [ ] 无 Match 错误
- [ ] 无 Template Render 错误

### 4. 回滚准备
- [ ] 确认可以在 5 分钟内回滚
- [ ] 回滚后功能正常
```

---

### Phase 6: 灰度发布与全量 (Day 12-14)

#### 6.1 灰度发布计划

```yaml
# 发布计划
灰度阶段:
  Day 12:
    - 10% 流量使用 V2
    - 监控指标: 延迟、错误率、Prompt 大小
    - 观察时长: 4 小时
    
  Day 13 (如果 Day 12 正常):
    - 50% 流量使用 V2
    - 监控时长: 8 小时
    
  Day 14 (如果 Day 13 正常):
    - 100% 流量使用 V2
    - 持续监控

回滚条件:
  - 错误率 > 1%
  - 延迟增加 > 20%
  - 用户投诉增加
```

#### 6.2 监控 Dashboard

```python
# 关键指标
- protocol_load_duration_seconds (P99 < 100ms)
- protocol_match_accuracy (目标 > 85%)
- prompt_size_savings_bytes (目标 > 50KB)
- worker_prompt_render_duration (P99 < 200ms)
```

**验收标准**:
- [ ] 灰度发布完成，无异常
- [ ] 全量发布完成
- [ ] 监控指标正常

---

## 回滚方案

### 紧急回滚 (发现问题时)

```bash
# 1. 关闭功能开关
export DYNAMIC_PROTOCOL_LOADING=false

# 2. 重启服务
systemctl restart evoloop-backend

# 3. 验证回滚
# - 检查日志确认使用 V1 builder
# - 验证任务正常执行
```

### 代码回滚 (如果代码有问题)

```bash
# 1. 回滚到上一个版本
git revert <commit_hash>

# 2. 重新部署
git push origin main
```

---

## 时间线总结

| 阶段 | 时间 | 产出 |
|------|------|------|
| Phase 0: 准备 | Day 1-2 | 功能开关、监控、目录结构 |
| Phase 1: Skill 提取 | Day 2-4 | 3个 Protocol Skill |
| Phase 2: Matcher | Day 4-6 | ProtocolMatcher + Loader |
| Phase 3: Prompt 精简 | Day 6-8 | worker_v2.prompt.j2 |
| Phase 4: Supervisor 集成 | Day 8-10 | 动态路由 + A/B 测试 |
| Phase 5: 测试 | Day 10-12 | 单元测试 + 集成测试 |
| Phase 6: 发布 | Day 12-14 | 灰度 + 全量 |

**总工期**: 14 天 (含缓冲)

---

## 成功标准

1. **性能**: Documenter 场景 Prompt 从 130KB 降到 < 80KB
2. **延迟**: 生产环境 190KB 请求从 4min 降到 < 2min
3. **稳定性**: 错误率 < 0.1%，无回滚
4. **可维护性**: Protocol 作为独立 Skill 管理

---

**是否需要我开始实施 Phase 0？**
