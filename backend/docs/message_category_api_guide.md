# 消息分类 API 接口指南

## 消息分类体系

系统使用 `category` 字段对消息进行分类，共有 9 种类别：

### 用户可见类别（前端展示）

| category | role | 说明 | 存储字段 |
|----------|------|------|---------|
| `user` | human | 用户输入 | content |
| `assistant_response` | ai | AI 最终回复 | content |
| `assistant_tool_call` | ai | AI 调用可见工具 | content + tool_calls |
| `tool_output` | tool | 可见工具执行结果 | content |
| `internal_reasoning` | ai | AI 思考过程 | thinking |
| `error` | ai | 系统错误消息 | content |

### 内部处理类别（前端不展示）

| category | 说明 | 是否入库 |
|----------|------|---------|
| `internal_tool_call` | 内部工具调用 | ❌ 不入库 |
| `internal_system` | 系统事件 | ❌ 不入库 |
| `internal_llm_json` | 内部 LLM JSON 响应 | ❌ 不入库 |

## API 响应字段说明

### GET /conversations/{thread_id}/messages

返回消息列表，自动排除不入库的类别。

#### 前端类型映射

```json
{
  "role": "ai",
  "category": "internal_reasoning",
  "thinking": "思考内容...",
  "content": ""
}
```

#### 错误消息示例

```json
{
  "role": "ai",
  "category": "error",
  "content": "Worker execution failed: ...",
  "thinking": null
}
```

## 前端适配建议

### 1. 消息渲染策略

```typescript
// 根据 category 渲染不同样式
const renderMessage = (msg: Message) => {
  switch (msg.category) {
    case 'internal_reasoning':
      return <ThinkingCard content={msg.thinking} />;
    case 'error':
      return <ErrorAlert content={msg.content} />;
    case 'assistant_tool_call':
      return <ToolCallCard toolCalls={msg.tool_calls} />;
    default:
      return <MessageBubble content={msg.content} role={msg.role} />;
  }
};
```

### 2. 思考过程显示

- `internal_reasoning` 使用 `thinking` 字段内容
- 建议默认折叠，可展开查看
- 显示在关联的 AI 消息之前或作为子元素

### 3. 错误消息显示

- `error` 类别消息使用错误样式（红色/警告）
- 建议显示在对话中但明显区分
- 提供重试或查看详情的选项

### 4. 工具调用显示

- `assistant_tool_call` 显示工具调用卡片
- `tool_output` 作为子元素折叠显示
- 点击可展开查看详细输入/输出

## 向后兼容性

- 旧消息可能没有 `category` 字段（为 `null`）
- API 默认将 `null` 视为可见消息
- 前端应该处理 `category` 缺失的情况
