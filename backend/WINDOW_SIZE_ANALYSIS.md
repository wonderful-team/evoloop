# Window Size 关系深度分析

## 两个值的本质区别

### 1. `max_turns=3`（对话历史提取）

```python
# Worker 层 - 应用逻辑
ConversationContext.extract_relevant_history(messages, max_turns=3)
```

**作用**：从消息历史中提取**文本摘要**，插入到 System Prompt 中
**目的**：让 Worker "知道"之前的对话内容
**输出格式**：文本字符串

### 2. `DEFAULT_WINDOW_SIZE=10`（消息窗口切片）

```python
# AgentEngine 层 - 技术限制
smart_window_slice(messages, window_size=DEFAULT_WINDOW_SIZE)
```

**作用**：限制传递给 LLM 的**消息数量**
**目的**：防止超出 token 限制
**输出格式**：消息列表（被切片后的）

## 关键问题：我的实现有重复！

```python
# 我的当前实现（有问题的）
all_messages = state.get("messages", [])  # 20 条消息
conversation_history = extract_relevant_history(all_messages, max_turns=3)  # 文本摘要
enhanced_mission = build_context_aware_mission(mission, conversation_history)
messages = list(all_messages) + [HumanMessage(content=enhanced_mission)]  # 20 + 1 = 21 条

# 然后进入 AgentEngine
smart_window_slice(messages, window_size=10)  # 切到 10 条
```

**问题**：
1. `all_messages` 已经包含完整对话历史
2. `enhanced_mission` 又包含了一份历史摘要
3. **重复！** 同一份信息传递了两次
4. 而且可能导致重要消息被切片截断

## 最合理的解决方案

### 方案：分层窗口管理（推荐）

**核心思想**：
- Worker 决定**是否**保留历史（策略层）
- AgentEngine 决定**保留多少**（技术层）
- **不要重复**传递历史

**实现**：

```python
# Worker 层 - 策略决策
if preserve_history:
    # 保留完整历史，让 AgentEngine 处理切片
    messages = state.get("messages", [])
    # 只追加新的 mission，不重复添加历史摘要
    messages = messages + [HumanMessage(content=mission_msg)]
else:
    # 重置
    messages = [HumanMessage(content=mission_msg)]

# AgentEngine 层 - 技术限制
# 无论 Worker 传递多少消息，都切片到 DEFAULT_WINDOW_SIZE
smart_window_slice(messages, window_size=DEFAULT_WINDOW_SIZE)
```

**关系协调**：

| 参数 | 作用 | 建议值 | 关系 |
|------|------|--------|------|
| `DEFAULT_WINDOW_SIZE` | AgentEngine 硬限制 | 10 | 全局上限 |
| `max_turns` | 可选，控制摘要详细程度 | 3 | 如果生成摘要，不要超过 WINDOW_SIZE/2 |

**协调公式**：
```python
# 如果 Worker 要生成历史摘要
max_turns = min(3, DEFAULT_WINDOW_SIZE // 2 - 1)
# DEFAULT_WINDOW_SIZE=10 → max_turns=4（取 min(3,4)=3）✓
```

## 但我需要重新思考：真的需要 `max_turns` 吗？

### 场景分析

**场景 1：纯代码任务（多轮对话）**
```
Round 1: User: "创建登录功能"
Round 2: User: "添加错误处理"
Round 3: User: "再优化一下"
```

**Worker 应该看到**：
- System Prompt（固定）
- Messages: [Round1, Round2, Round3 + 当前请求]
- **不需要额外摘要**，因为完整消息就是历史

**场景 2：跨多个 Worker 的任务**
```
Supervisor → Worker1 (创建文件)
Supervisor → Worker2 (修改刚才的文件)
```

**Worker2 应该看到**：
- System Prompt
- **不需要 Worker1 的完整消息历史**（那是 Worker1 的内部对话）
- 但要知道"刚才创建的文件路径"
- **通过 `historical_context` 传递关键信息**

## 最终方案

### 结论：`max_turns` 和 `DEFAULT_WINDOW_SIZE` 是独立的

**DEFAULT_WINDOW_SIZE**（必须存在）：
- 技术限制，防止 token 爆炸
- AgentEngine 层统一处理
- 与 Worker 逻辑无关

**max_turns**（可选，特定场景）：
- 当需要在 System Prompt 中**显式总结**历史时使用
- 例如：跨 Worker 引用、长对话压缩
- 一般情况下**不需要**，因为完整消息就是历史

### 修正我的实现

**当前（有问题）**：
```python
# 总是提取历史摘要
conversation_history = extract_relevant_history(...)
messages = all_messages + [HumanMessage(enhanced_mission)]  # 重复
```

**修正后**：
```python
# Worker 只决定是否保留历史
if preserve_history:
    messages = all_messages + [HumanMessage(mission_msg)]
else:
    messages = [HumanMessage(mission_msg)]

# 让 AgentEngine 的 smart_window_slice 处理切片
# 不需要额外提取 conversation_history

# 只有在跨 Worker 引用时，才使用 historical_context
if cross_worker_reference:
    system_prompt += f"\n\n### Historical Context\n{historical_context}"
```

### 关系总结

```
Worker Layer                    AgentEngine Layer
────────────                    ─────────────────
决定是否保留历史  ──messages──>  smart_window_slice
(strategy)                      (technical limit)
                                
┌─────────────────┐             ┌─────────────────┐
│ preserve_history │             │ DEFAULT_WINDOW  │
│ = True/False    │             │ _SIZE = 10      │
└─────────────────┘             └─────────────────┘
        │                               │
        │ 传递消息列表                   │ 切片到 10 条
        │                               │
        └──────────> LLM <──────────────┘
```

**两个值的关系**：
- **无关但协作**：Worker 决定保留策略，AgentEngine 强制执行技术限制
- **无依赖**：可以独立调整，但建议 `Worker 保留数 >= DEFAULT_WINDOW_SIZE`
- **避免重复**：不要在 Worker 层添加摘要文本，让消息本身承载历史

---

**结论**：
1. **保持独立**：两个值服务于不同目的
2. **Worker 简化**：不要提取 conversation_history 文本，直接保留完整消息
3. **AgentEngine 统一处理**：所有消息都经过 `smart_window_slice`
4. **特殊情况**：跨 Worker 引用时，使用 `historical_context` 传递关键信息（非完整历史）
