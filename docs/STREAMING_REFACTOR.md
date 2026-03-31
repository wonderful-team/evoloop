# Phase 3 流式输出重构文档

## 重构目标

将独立的 `EnhancedStreamManager` 与现有的 `TransparentCallbackHandler` 整合，消除冗余，实现结构化的流事件系统。

## 重构前的问题

```
问题1: EnhancedStreamManager 发布到错误的频道
  - 发布到: chat:{thread_id}:stream
  - 但前端只监听: chat:{thread_id}:events
  - 结果: 事件进入黑洞

问题2: 前端添加了未使用的 onStream 回调
  - ChatConnection.ts 添加了 onStream 处理
  - 但后端没有正确发送 stream 事件
  - 结果: 代码冗余

问题3: 两个系统独立运行，没有协同
  - TransparentCallbackHandler: 处理 LangChain 回调
  - EnhancedStreamManager: 独立的流管理
  - 结果: 重复发布，状态不一致
```

## 重构后的架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Unified Streaming Architecture                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  TransparentCallbackHandler (Phase 3 Refactored)                  │
│  ├── __init__: 初始化 _stream_manager (EnhancedStreamManager)     │
│  ├── on_tool_start()                                              │
│  │   ├── 调用 monitor.add_step()          # 现有活动跟踪         │
│  │   └── 调用 _stream_manager.tool_start() # 结构化流事件        │
│  ├── on_tool_end()                                                │
│  │   ├── 调用 monitor.update_step()       # 更新活动状态         │
│  │   └── 调用 _stream_manager.tool_complete()                   │
│  ├── on_tool_progress()  # 新增                                   │
│  │   └── 调用 _stream_manager.tool_progress()                   │
│  └── on_tool_error()                                              │
│      └── 调用 _stream_manager.tool_complete(success=False)      │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  EnhancedStreamManager (Phase 3 Refactored)                       │
│  ├── _publish()                                                   │
│  │   ├── 发布到: chat:{thread}:stream    # 前端 SSE 消费        │
│  │   └── 调用 _sync_to_activity()         # 同步到活动监视器     │
│  ├── _sync_to_activity()  # 新增                                  │
│  │   ├── tool_start  → monitor.add_step()                       │
│  │   ├── tool_progress → monitor.update_step()                  │
│  │   └── tool_complete → monitor.update_step()                  │
│  ├── tool_start(tool_name, params)                                │
│  ├── tool_progress(tool_name, message, progress)                  │
│  └── tool_complete(tool_name, result, success)                    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  SSE Endpoint (stream.py) - Phase 3 Updated                       │
│  ├── 订阅: chat:{thread_id}:events   (现有事件)                  │
│  ├── 订阅: chat:{thread_id}:stream   (新增结构化事件)            │
│  └── 转发: stream 事件 → SSE event: stream                       │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (ChatConnection.ts)                                     │
│  ├── 监听: event: token     → onToken()                          │
│  ├── 监听: event: activity  → onActivity()                       │
│  ├── 监听: event: stream    → onStream()  # Phase 3 新增         │
│  └── store: _processStreamEvent()                                 │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## 关键改动

### 1. Backend: EnhancedStreamManager

**Before**: 发布到错误的 `stream` 频道，没有同步到 activity_monitor

**After**:
```python
async def _publish(self, event: StreamEvent):
    # 1. 发布到 stream 频道 (前端 SSE 消费)
    await self.monitor.client.publish(
        f"chat:{self.thread_id}:stream",
        event.to_json()
    )
    
    # 2. 同步到 activity_monitor (步骤跟踪)
    await self._sync_to_activity(event)

async def _sync_to_activity(self, event: StreamEvent):
    # 将流事件同步到现有活动系统
    if event.type == "tool_start":
        await self.monitor.add_step(...)
    elif event.type == "tool_progress":
        await self.monitor.update_step(...)
```

### 2. Backend: TransparentCallbackHandler

**Before**: 独立管理步骤，没有流事件

**After**:
```python
def __init__(self, thread_id: str = None):
    ...
    # Phase 3: 集成 EnhancedStreamManager
    self._stream_manager = EnhancedStreamManager(thread_id) if thread_id else None

async def on_tool_start(self, serialized, input_str, **kwargs):
    # 1. 现有逻辑: 创建活动步骤
    self.tool_task_id = await self.monitor.add_step(...)
    
    # 2. 新增: 发送结构化流事件
    if self._stream_manager:
        await self._stream_manager.tool_start(tool_name, data)

async def on_tool_progress(self, tool_name: str, progress: int, message: str = None):
    """Phase 3: 新增方法，支持工具进度更新"""
    if self._stream_manager:
        await self._stream_manager.tool_progress(tool_name, message, progress)
```

### 3. Backend: SSE Stream Endpoint

**Before**: 只订阅 events 频道

**After**:
```python
# 同时订阅两个频道
await pubsub.subscribe(
    f"chat:{thread_id}:events",
    f"chat:{thread_id}:stream"  # 新增
)

# 处理 stream 事件
if event_type in ["thinking", "tool_start", "tool_progress", ...]:
    yield f"event: stream\ndata: {json.dumps(event_data)}\n\n"
```

### 4. Frontend: ChatConnection + ChatStore

**已有实现** (Phase 3 初期):
```typescript
// ChatConnection.ts
sse.addEventListener("stream", (e) => {
    const data = JSON.parse(e.data);
    this.callbacks?.onStream?.(data);
});

// chatStore.ts
_processStreamEvent: (event: StreamEvent) => {
    // 处理各种流事件类型
    switch (event.type) {
        case 'thinking': ...
        case 'tool_start': ...
        case 'tool_progress': ...
    }
}
```

## 数据流示例

### 工具执行流程

```
1. LangGraph 调用工具
   ↓
2. TransparentCallbackHandler.on_tool_start()
   ├── monitor.add_step()           # 创建活动步骤
   └── _stream_manager.tool_start() # 发送流事件
   ↓
3. EnhancedStreamManager._publish()
   ├── Redis.publish(stream)        # 发布到 stream 频道
   └── _sync_to_activity()          # 同步步骤状态
   ↓
4. SSE Endpoint (stream.py)
   └── 转发为 SSE event: stream
   ↓
5. Frontend (ChatConnection)
   └── onStream() → chatStore._processStreamEvent()
   ↓
6. UI Update
   ├── StreamStatus 组件显示工具状态
   └── 更新进度条和消息
   ↓
7. 工具完成
   TransparentCallbackHandler.on_tool_end()
   └── _stream_manager.tool_complete()
```

## 优点

### 1. 统一的数据流
- 所有流事件通过统一渠道发布
- 前端只需监听一个 stream 事件
- 避免重复数据和不一致

### 2. 向后兼容
- 现有 `activity` 事件继续工作
- 现有 `token` 事件不受影响
- 新增的 `stream` 事件是增量功能

### 3. 职责清晰
- `TransparentCallbackHandler`: LangChain 回调适配
- `EnhancedStreamManager`: 结构化流事件管理
- `activity_monitor`: 持久化步骤状态

### 4. 可扩展性
- 新增事件类型只需添加到 StreamEventType
- 前端自动支持新事件类型
- 工具进度更新变得容易

## 使用示例

### 在工具中发送进度更新

```python
from app.core.callbacks.transparent import TransparentCallbackHandler

async def long_running_tool(params, callback_handler: TransparentCallbackHandler):
    total = 100
    for i in range(total):
        # 执行工作...
        
        # Phase 3: 发送进度更新
        if callback_handler:
            await callback_handler.on_tool_progress(
                tool_name="long_running_tool",
                progress=int((i / total) * 100),
                message=f"Processing {i}/{total}"
            )
```

### 前端消费流事件

```typescript
// 已在 chatStore 中实现
const streamState = useChatStore(state => state.streamState);

// 在组件中显示
<StreamStatus state={streamState} />
```

## 测试验证

```bash
# 后端测试
cd backend
./.venv/bin/python -c "
from app.core.callbacks.transparent import TransparentCallbackHandler
from app.core.streaming import EnhancedStreamManager

handler = TransparentCallbackHandler('test-thread')
assert handler._stream_manager is not None
print('✅ Integration test passed')
"

# 前端类型检查
cd frontend/packages/desktop
npx tsc --noEmit
```

## 后续优化

1. **工具进度粒度**: 为耗时的工具（如 codebase 索引）添加更多进度点
2. **思考过程流式化**: 将 LLM 的 thinking 过程也转为结构化事件
3. **性能优化**: 批量发送高频事件（如 token）减少 Redis 压力
