# 所有节点的消息处理分析

## 节点消息处理方式总览

| 节点 | 消息来源 | 处理方式 | 是否经过 smart_window_slice | 特殊处理 |
|------|----------|----------|---------------------------|----------|
| **Supervisor** | state["messages"] | AgentEngine.run_node | ✅ (内部) | 完整历史 |
| **Worker** | state["messages"] | AgentEngine.run_node | ✅ (内部) | 支持保留/重置 |
| **Chat** | state["messages"] | AgentEngine.run_node | ✅ (内部) | 单轮，无工具 |
| **Finish** | state["messages"] | 先 slice → AgentEngine | ✅ (显式) | window_size=10 |
| **Aggregator** | blackboard | 不直接使用 messages | ❌ | 聚合结果 |
| **FinishAuditor** | 参数传入 | 分析 messages，不修改 | ❌ | 审计分类 |

## 详细分析

### 1. Supervisor Node

```python
async def __call__(self, state: AgentState, config: RunnableConfig):
    messages = list(state.get("messages", []))  # 获取完整消息
    
    # ... 处理逻辑 ...
    
    engine_result = await AgentEngine.run_node(
        state=state,  # 包含完整 messages
        config=config,
        system_prompt=dynamic_prompt,
        tools=tools,
        # ...
    )
```

**特点**：
- 接收完整 messages 列表
- 通过 AgentEngine 执行，内部会调用 `smart_window_slice(DEFAULT_WINDOW_SIZE=10)`
- 不主动重置或修改 messages

### 2. Worker Node (修改后)

```python
# 修改后逻辑
if preserve_history:
    messages = list(all_messages) + [HumanMessage(content=mission_msg)]
    logger.info(f"Preserving conversation history ({len(all_messages)} messages)")
else:
    messages = [HumanMessage(content=mission_msg)]

# 通过 AgentEngine 执行
engine_result = await AgentEngine.run_node(
    state=worker_state,  # 包含 messages
    # ...
)
```

**特点**：
- 可选择保留完整历史或重置
- 保留历史时：`messages = all_messages + [new_mission]`
- 通过 AgentEngine 执行，内部会切片

### 3. Chat Node

```python
async def chat_node(state: AgentState, config: RunnableConfig):
    result = await AgentEngine.run_node(
        state=state,  # 完整 state，包含 messages
        config=config,
        system_prompt=system_prompt,
        tools=[],  # Chat 不使用工具
        max_steps=1,  # 单轮
        # ...
    )
```

**特点**：
- 接收完整 state（含 messages）
- 单轮对话（max_steps=1）
- 无工具调用

### 4. Finish Node

```python
async def _execute_audit(self, state: AgentState, config: RunnableConfig):
    messages = state.get("messages", [])
    
    # 显式调用 smart_window_slice
    windowed_messages = smart_window_slice(
        messages, 
        window_size=10,  # 显式指定
        # ...
    )
    
    focused_state = dict(state)
    focused_state["messages"] = windowed_messages
    
    # 传给 AgentEngine
    result = await AgentEngine.run_node(
        state=focused_state,
        # ...
    )
```

**特点**：
- 显式调用 `smart_window_slice(messages, window_size=10)`
- 将切片后的 messages 传给 AgentEngine
- AgentEngine 内部还会再切片一次（但输入已经≤10条）

### 5. Aggregator Node

```python
async def aggregator_node(state: AgentState, config: RunnableConfig):
    blackboard = state.get("blackboard") or {}
    subtask_results = blackboard.get("subtask_results", [])
    # 不直接使用 state["messages"]
```

**特点**：
- 不直接使用 messages
- 从 blackboard 获取 subtask_results
- 生成新的 AIMessage 返回

### 6. FinishAuditor (工具类)

```python
class LayeredAuditor:
    def classify_audit_tier(self, tool_history, messages, blackboard, state):
        # 分析 messages，不修改
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                # 分析内容
```

**特点**：
- 被 Finish 节点调用
- 接收 messages 用于分析
- 不修改 messages，只返回审计决策

## 关键发现

### 1. 消息处理层次

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Graph State (LangGraph)                           │
│  - state["messages"] 完整消息历史                           │
│  - 所有节点共享                                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Node Decision (各节点)                            │
│  - Supervisor: 完整传递                                     │
│  - Worker: 保留或重置                                       │
│  - Finish: 显式切片 (window_size=10)                        │
│  - Aggregator: 不使用                                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: AgentEngine (统一处理)                            │
│  - smart_window_slice(DEFAULT_WINDOW_SIZE=10)               │
│  - 所有节点最终都经过这里                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: LLM                                               │
│  - 实际接收 ≤10 条消息                                      │
└─────────────────────────────────────────────────────────────┘
```

### 2. Finish 节点的特殊性

**问题**：Finish 节点显式调用了 `smart_window_slice(messages, window_size=10)`，然后又传给 AgentEngine，AgentEngine 内部还会再切片一次。

**冗余**：
```python
# Finish 节点
windowed = smart_window_slice(messages, window_size=10)  # 第一次切片
state["messages"] = windowed

# AgentEngine 内部
result = smart_window_slice(windowed, window_size=10)  # 第二次切片（无意义）
```

**建议**：Finish 节点可以设置 `skip_window_slice=True` 或直接用 `AgentEngine._execute_react_loop` 绕过。

### 3. Worker 修改的影响

**修改前**：
```python
messages = [HumanMessage(content=mission_msg)]  # 总是重置
```

**修改后**：
```python
if preserve_history:
    messages = all_messages + [new_mission]  # 保留历史
else:
    messages = [mission_msg]  # 重置
```

**影响**：
- ✅ 多轮对话支持：Worker 能看到之前的历史
- ⚠️ Token 风险：如果历史很长，经过 AgentEngine 切片后可能丢失重要信息
- ✅ 统一处理：所有切片逻辑仍在 AgentEngine

## 多轮对话场景下的协作

### 场景：修改刚才的代码

```
User: "创建登录功能" (Round 1)
    ↓
Supervisor → Worker (preserve_history=True)
    ↓
Worker 执行，返回结果
    ↓
...

User: "添加错误处理" (Round 2)  
    ↓
Supervisor → Worker (preserve_history=True)
    ↓
Worker 的 messages = [Round1历史] + [新请求]
    ↓
AgentEngine.smart_window_slice(≤10条)
    ↓
LLM 看到最近10条，包含Round1的关键信息
```

### 场景：跨 Worker 引用

```
User: "创建登录功能"
    ↓
Supervisor → Worker1 (create login)
    ↓
Worker1 完成
    ↓

User: "修改刚才的文件添加OAuth"
    ↓
Supervisor → Worker2 (modify file)
    ↓
Worker2 通过 execution_ticket["context"]["historical_context"] 知道文件路径
    ↓
Worker2 的 messages 可能不包含 Worker1 的完整对话
    ↓
但通过 focus_paths 和 historical_context 获得关键信息
```

## 与 DEFAULT_WINDOW_SIZE 的关系

| 节点 | 自己的处理 | AgentEngine 处理 | 最终给 LLM |
|------|-----------|------------------|-----------|
| Supervisor | 无 | slice(10) | ≤10 条 |
| Worker | 保留/重置决策 | slice(10) | ≤10 条 |
| Chat | 无 | slice(10) | ≤10 条 |
| Finish | slice(10) | slice(10) | ≤10 条（冗余） |
| Aggregator | 生成新消息 | N/A | N/A |

**结论**：
- `DEFAULT_WINDOW_SIZE=10` 是**统一的技术限制**
- 各节点决定是否保留历史，但**最终都被切片到 10 条**
- Finish 节点有冗余切片，可优化
- Worker 的 `preserve_history` 只是决定是否传入完整历史，不影响最终切片

## 建议优化

### 1. 统一消息处理

```python
# 建议添加配置
class NodeConfig:
    preserve_history: bool = True  # 是否保留历史
    window_size: int = DEFAULT_WINDOW_SIZE  # 该节点的窗口大小
    
# 各节点配置
SUPERVISOR_CONFIG = NodeConfig(preserve_history=True)
WORKER_CONFIG = NodeConfig(preserve_history=True)
CHAT_CONFIG = NodeConfig(preserve_history=True, window_size=5)  # Chat 可以更短
FINISH_CONFIG = NodeConfig(preserve_history=False, window_size=10)
```

### 2. 消除 Finish 冗余

```python
# Finish 节点
if skip_engine_slice:
    # 直接调用底层方法，跳过 AgentEngine 的切片
    result = await AgentEngine._execute_react_loop(...)
else:
    result = await AgentEngine.run_node(...)
```

### 3. 分层窗口策略

```python
# Layer 1: Node 层 - 策略决策
# Layer 2: AgentEngine 层 - 统一切片
# Layer 3: LLM 层 - 接收处理

# 不再在 Node 层提取 conversation_history 文本
# 消息本身就是历史载体
```

---

**总结**：所有节点最终都受 `DEFAULT_WINDOW_SIZE=10` 限制，Worker 的 `preserve_history` 只是策略选择，实际切片由 AgentEngine 统一处理。Finish 节点有冗余切片需优化。
