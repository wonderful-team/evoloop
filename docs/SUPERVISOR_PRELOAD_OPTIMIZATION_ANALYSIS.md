# Supervisor 前置优化分析报告

## 当前架构分析

### Supervisor 调用链
```
用户请求 → Graph.invoke() → Supervisor.__call__() → 
  1. EvoContextMiddleware.hydrate() 
  2. _build_context()
  3. SupervisorPromptBuilder.build()
  4. AgentEngine.run_node() → LLM 调用
```

### 各阶段耗时分析

| 阶段 | 当前实现 | 可优化性 | 风险等级 |
|------|---------|---------|---------|
| EvoContextMiddleware.hydrate() | 分层缓存，静态数据 5min TTL | ⚠️ 中 | 低 |
| tool_manager.get_node_tools() | 每次动态构建 | ✅ 高 | 低 |
| skill_discovery.get_active_skills_list() | 内存缓存(O(1)) | ✅ 已优化 | 无 |
| SupervisorPromptBuilder.build() | 每次渲染 Jinja2 模板 | ✅ 高 | 中 |
| AgentEngine.run_node() | LLM 调用 | ❌ 不可优化 | - |

---

## 可前置优化项（按收益排序）

### 1. 工具注册表预热 (高收益/低风险)

**现状问题：**
```python
# manager.py::get_node_tools()
def get_node_tools(self, node_name: str, state: AgentState | None = None) -> list[BaseTool]:
    # 每次调用都重新构建工具列表
    tools = _legacy_get_node_tools(node_name)  # 遍历所有注册工具
    # ... 动态 MCP 工具加载
```

**优化方案：**
```python
# 在 ToolManager 中添加启动时预热
class ToolManager:
    def __init__(self):
        self._node_tools_cache: dict[str, list[BaseTool]] = {}
        
    async def warmup(self):
        """启动时预热所有节点工具"""
        nodes = ["supervisor", "worker", "finish", "aggregator"]
        for node in nodes:
            self._node_tools_cache[node] = await self._build_node_tools(node)
            
    def get_node_tools(self, node_name: str, state: AgentState | None = None) -> list[BaseTool]:
        # 基础工具从缓存获取
        base_tools = self._node_tools_cache.get(node_name, [])
        
        # 只处理动态 MCP 工具增量
        if state:
            dynamic_tools = self._get_dynamic_mcp_tools(state)
            return base_tools + dynamic_tools
        return base_tools
```

**预期收益：** 减少每次 Supervisor 调用 10-30ms 工具构建时间

---

### 2. Jinja2 模板预编译缓存 (高收益/中风险)

**现状问题：**
```python
# supervisor_builder.py::build()
return render_template("agents/supervisor.prompt.j2", **template_vars)

# 每次调用都重新解析和渲染模板
```

**优化方案：**
```python
# 在应用启动时预编译模板
class TemplateCache:
    """预编译模板缓存"""
    _compiled_templates: dict[str, Template] = {}
    
    @classmethod
    def warmup(cls):
        """启动时预编译关键模板"""
        critical_templates = [
            "agents/supervisor.prompt.j2",
            "agents/worker.prompt.j2",
            "agents/finish.prompt.j2",
        ]
        for tpl_path in critical_templates:
            cls._compiled_templates[tpl_path] = env.get_template(tpl_path)
            
    @classmethod
    def render(cls, template_path: str, **kwargs) -> str:
        template = cls._compiled_templates.get(template_path)
        if template:
            return template.render(**kwargs)
        return render_template(template_path, **kwargs)  # 回退
```

**预期收益：** 减少每次 Prompt 构建 20-50ms 模板解析时间

---

### 3. System Config 内存缓存 (中收益/低风险)

**现状问题：**
```python
# 每次调用都查询数据库
user_lang = SystemConfigService.get_language_preference()
```

**优化方案：**
```python
# 已在 main.py lifespan 中初始化，但可以做本地缓存
class SystemConfigCache:
    """配置本地缓存，监听变更事件刷新"""
    _cache: dict[str, Any] = {}
    _last_refresh: float = 0
    
    @classmethod
    async def warmup(cls):
        """启动时加载所有配置到内存"""
        cls._cache = await cls._load_all_configs()
        cls._last_refresh = time.time()
        
    @classmethod
    def get(cls, key: str, default=None):
        # 内存读取 O(1)
        return cls._cache.get(key, default)
```

**预期收益：** 消除每次数据库查询 5-10ms

---

### 4. 异步队列预加载动态上下文 (中收益/中风险)

**现状问题：**
```python
# middleware.py::hydrate()
# 每次 Supervisor 调用都执行：
- 内存搜索 (Neo4j/SQLite)
- 环境状态获取
- Plugin 注册
```

**优化方案：**
```python
class AsyncContextPrefetcher:
    """后台预取上下文数据"""
    
    def __init__(self):
        self._prefetch_queue = asyncio.Queue()
        self._prefetch_cache: dict[str, Any] = {}
        
    async def start_worker(self):
        """启动后台预取 worker"""
        while True:
            thread_id = await self._prefetch_queue.get()
            # 异步预取该线程可能需要的上下文
            data = await self._prefetch_context(thread_id)
            self._prefetch_cache[thread_id] = data
            
    async def _prefetch_context(self, thread_id: str):
        """预取上下文（预测用户下一步可能需要的数据）"""
        return {
            "concepts": await memory_manager.long_term.get_recent_concepts(),
            "telemetry": get_awakened_state(),
            "skills": await skill_discovery.get_active_skills_list(),
        }
        
    def mark_active_thread(self, thread_id: str):
        """标记活跃线程，触发预取"""
        self._prefetch_queue.put_nowait(thread_id)

# 在 WebSocket 连接建立时触发预取
prefetcher.mark_active_thread(thread_id)
```

**预期收益：** 减少首次调用 50-100ms（将 IO 移至后台）

---

### 5. LLM 客户端连接池预热 (低收益/低风险)

**现状问题：**
```python
# AgentEngine.run_node()
llm = LLMFactory.create_llm(model_name=model, temperature=temperature)
# 每次调用都新建客户端
```

**优化方案：**
```python
class LLMClientPool:
    """LLM 客户端连接池"""
    _pools: dict[str, Any] = {}
    
    @classmethod
    def warmup(cls):
        """启动时预热常用模型客户端"""
        for model in ["default", "fast", "vision"]:
            cls._pools[model] = LLMFactory.create_llm(model_name=model)
            
    @classmethod
    def get(cls, model: str = None, temperature: float = 0.7):
        # 从池获取并调整参数
        client = cls._pools.get(model or "default")
        # 克隆并设置 temperature
        return client.with_temperature(temperature)
```

**预期收益：** 减少 LLM 初始化 20-30ms

---

## 实施建议（分阶段）

### Phase 1: 低风险快速收益（1-2 天）
1. **工具注册表预热** - 纯内存缓存，风险极低
2. **System Config 本地缓存** - 配置变更通过事件刷新

### Phase 2: 中等风险（3-5 天）
3. **Jinja2 模板预编译** - 需要测试模板渲染一致性
4. **LLM 客户端池** - 需要验证并发安全性

### Phase 3: 架构优化（1-2 周）
5. **异步上下文预取** - 需要设计线程活跃度检测机制

---

## 当前已优化的点

✅ **已在前置启动阶段完成：**
- `skill_discovery._sync_system_skills()` - 技能同步
- `skill_discovery.get_active_skills_list()` - 技能索引预热
- `memory_manager.initialize()` - 内存服务初始化
- `awaken()` - 环境感知初始化
- `GraphBuilder().build()` - 图结构预构建

---

## 监控建议

建议添加以下指标来验证优化效果：

```python
# 在 Supervisor.__call__ 中添加计时
supervisor_timing = {
    "hydrate_ms": 0,
    "build_context_ms": 0,
    "prompt_build_ms": 0,
    "llm_call_ms": 0,
    "total_ms": 0
}
```
