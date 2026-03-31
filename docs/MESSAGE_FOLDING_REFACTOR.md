# 消息折叠优化方案

## 背景

当前工具消息折叠存在双端维护问题：
- **后端**: 修复孤儿消息、保证顺序
- **API**: 返回扁平消息列表
- **前端**: 再次扫描、匹配、折叠

## 优化目标

后端API直接返回折叠格式，前端删除折叠逻辑。

## 方案：API层折叠

### 优点
- 不改数据库存储结构
- 不改LangChain执行流程
- 可渐进式实施（添加?fold=true参数）
- 风险最小

### 实施步骤

#### Step 1: 后端 - 添加消息折叠工具

**文件**: `backend/app/core/engine/message_utils.py`

```python
async def fold_messages(messages: list[BaseMessage]) -> list[dict]:
    """
    将扁平消息列表折叠为嵌套格式。
    
    Input: [AIMessage, ToolMessage, AIMessage, ToolMessage]
    Output: [
        {
            role: "ai",
            content: "...",
            tool_calls: [...],
            steps: [
                {tool: "read_file", output: "...", status: "done"}
            ]
        }
    ]
    """
    result = []
    i = 0
    
    while i < len(messages):
        msg = messages[i]
        
        if isinstance(msg, AIMessage):
            # 收集此AI消息的工具执行结果
            steps = []
            tool_calls = msg.tool_calls or []
            
            # 遍历后续的 ToolMessage
            j = i + 1
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                tool_msg = messages[j]
                # 匹配 tool_call_id
                tool_call = next(
                    (tc for tc in tool_calls if tc.get("id") == tool_msg.tool_call_id),
                    None
                )
                
                steps.append({
                    "id": f"step-{tool_msg.tool_call_id}",
                    "tool": tool_msg.name or tool_call.get("name") if tool_call else "unknown",
                    "input": tool_call.get("args") if tool_call else {},
                    "output": tool_msg.content,
                    "status": "done",
                    "tool_call_id": tool_msg.tool_call_id
                })
                j += 1
            
            result.append({
                "id": f"msg-{msg.id}" if hasattr(msg, "id") else f"msg-{i}",
                "role": "ai",
                "content": msg.content,
                "thinking": getattr(msg, "thinking", None),
                "tool_calls": tool_calls,
                "steps": steps,  # 嵌套的工具结果
                "timestamp": getattr(msg, "created_at", None)
            })
            
            i = j  # 跳过已处理的 ToolMessage
            
        elif isinstance(msg, ToolMessage):
            # 孤儿 ToolMessage，单独处理
            result.append({
                "id": f"orphan-{msg.tool_call_id}",
                "role": "tool",
                "tool": msg.name or "unknown",
                "output": msg.content,
                "tool_call_id": msg.tool_call_id,
                "orphan": True
            })
            i += 1
            
        elif isinstance(msg, HumanMessage):
            result.append({
                "id": f"msg-{msg.id}" if hasattr(msg, "id") else f"msg-{i}",
                "role": "user",
                "content": msg.content,
                "timestamp": getattr(msg, "created_at", None)
            })
            i += 1
            
        else:
            i += 1
    
    return result
```

#### Step 2: 后端 - API添加折叠支持

**文件**: `backend/app/api/routes/conversations.py`

```python
@router.get("/{thread_id}/messages")
async def get_conversation_messages(
    thread_id: str,
    fold: bool = Query(False, description="Return folded format with nested steps"),
):
    """Get conversation messages."""
    messages = await get_messages_from_db(thread_id)
    
    if fold:
        # 新格式：折叠嵌套
        from app.core.engine.message_utils import fold_messages
        folded = await fold_messages(messages)
        return {"messages": folded, "format": "folded"}
    else:
        # 旧格式：扁平列表（兼容）
        return {"messages": messages, "format": "flat"}
```

#### Step 3: 前端 - 逐步迁移

**文件**: `frontend/packages/desktop/src/stores/chatStore.ts`

```typescript
// 修改 fetchHistory 支持新格式
fetchHistory: async (threadId: string) => {
    const history = await ConversationsService.getConversationMessages({
        threadId,
        fold: true,  // 请求折叠格式
    });
    
    if (history.format === "folded") {
        // 新格式：直接使用，无需折叠
        const formatted: Message[] = history.messages.map((m: any) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            thinking: m.thinking,
            tool_calls: m.tool_calls,
            steps: m.steps || [],  // 直接已有 steps
            timestamp: m.timestamp,
        }));
        set({ messages: formatted });
    } else {
        // 旧格式：保持原有折叠逻辑（兼容期）
        // ... existing code
    }
}

// 删除 _appendMessage 中的折叠逻辑（迁移完成后）
_appendMessage: (rawMsg: any) => {
    // 新格式下，工具消息已嵌套在AI消息中
    // 无需再扫描 backwards 匹配
    
    if (rawMsg.role === "tool") {
        // 孤儿工具消息（不应再出现）
        console.warn("Orphan tool message received:", rawMsg);
        return;
    }
    
    // AI消息已包含 steps
    if (rawMsg.role === "ai") {
        set(state => ({
            messages: [...state.messages, rawMsg]
        }));
    }
}
```

#### Step 4: 前端 - 组件简化

**文件**: `frontend/packages/desktop/src/components/Chat/ChatMessageItem.tsx`

```typescript
// 简化前：需要处理 steps 注入
function ChatMessageItem({ message }) {
    // 之前：需要监听并合并工具结果
    const [localSteps, setLocalSteps] = useState(message.steps || []);
    
    useEffect(() => {
        // 合并实时更新的工具结果
        // ...
    }, [message]);
}

// 简化后：直接使用 message.steps
function ChatMessageItem({ message }) {
    // 后端已提供完整 steps
    const steps = message.steps || [];
    
    return (
        <div>
            <MessageContent content={message.content} />
            {steps.length > 0 && <ExecutionSteps steps={steps} />}
        </div>
    );
}
```

### 数据结构对比

#### Before (扁平)
```json
{
  "messages": [
    {"id": 1, "role": "ai", "content": "I'll help you", "tool_calls": [{"id": "tc1", "name": "read_file"}]},
    {"id": 2, "role": "tool", "content": "file content...", "tool_call_id": "tc1"},
    {"id": 3, "role": "ai", "content": "Now let me edit", "tool_calls": [{"id": "tc2", "name": "edit_file"}]},
    {"id": 4, "role": "tool", "content": "edit done", "tool_call_id": "tc2"}
  ]
}
```

#### After (折叠)
```json
{
  "format": "folded",
  "messages": [
    {
      "id": "msg-1",
      "role": "ai",
      "content": "I'll help you",
      "tool_calls": [{"id": "tc1", "name": "read_file", "args": {"path": "test.py"}}],
      "steps": [
        {"id": "step-tc1", "tool": "read_file", "input": {"path": "test.py"}, "output": "file content...", "status": "done"}
      ]
    },
    {
      "id": "msg-3", 
      "role": "ai",
      "content": "Now let me edit",
      "tool_calls": [{"id": "tc2", "name": "edit_file"}],
      "steps": [
        {"id": "step-tc2", "tool": "edit_file", "output": "edit done", "status": "done"}
      ]
    }
  ]
}
```

### 好处

1. **前端简化**: 删除复杂的折叠逻辑
2. **性能提升**: 避免前端双重遍历
3. **数据一致性**: 后端单一数据源
4. **渐进迁移**: 通过参数控制，风险可控

### 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 前端兼容性问题 | 保留旧格式，通过 `?fold=true` 开关 |
| 后端性能下降 | 折叠计算在API层，可缓存 |
| 数据不一致 | 保留 `tool_call_id` 用于调试 |

### 实施优先级

1. **高**: 添加 `fold_messages()` 工具函数
2. **中**: API添加 `?fold=true` 支持
3. **中**: 前端支持新格式
4. **低**: 完全迁移后删除旧逻辑
