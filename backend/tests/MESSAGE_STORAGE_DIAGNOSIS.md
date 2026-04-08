# 消息存储机制诊断报告

## 🔴 核心问题 (已修复)

### 1. `persist_message_task` 缺少 `is_visible` 参数
**位置**: `backend/app/core/engine/tasks.py:329`

**错误信息**:
```
TypeError: persist_message_task() got an unexpected keyword argument 'is_visible'
```

**原因**: 
- `MessageHandler._persist_to_db()` 在调用任务时传入了 `is_visible` 参数
- 但 `persist_message_task` 函数签名中没有这个参数
- 导致 Huey 执行任务时抛出 TypeError，消息无法入库

**修复**:
```python
# 添加 is_visible 参数
def persist_message_task(
    ...
    category: str | None = None,
    is_visible: bool = True,  # 新增
):
```

---

## 🟡 次要问题 (已修复)

### 2. `on_tool_start` 被注释掉
**位置**: `backend/app/core/callbacks/database_logger.py`

**影响**: 
- 工具名称无法被正确追踪
- 回退为 `unknown_tool`
- 不影响入库，但影响调试

**修复**: 取消注释 `on_tool_start` 方法

---

### 3. 日志不足
**位置**: `backend/app/core/messaging/handler.py`

**修复**: 将关键日志提升为 INFO 级别:
- AI 消息分类和持久化决策
- 工具消息分类和持久化决策  
- 持久化任务提交
- 跳过持久化的原因

---

## ✅ 验证测试

运行测试确认修复:
```bash
cd backend
python -c "
from app.core.engine.tasks import persist_message_task
import inspect
sig = inspect.signature(persist_message_task)
assert 'is_visible' in sig.parameters
print('✅ persist_message_task has is_visible parameter')
"
```

---

## 📊 消息存储流程 (修复后)

```
1. Agent 生成 AI 消息
   ↓
2. DatabaseCallbackHandler.on_llm_end() 被调用
   ↓
3. MessageHandler.handle_ai_message()
   - 分类为 ASSISTANT_RESPONSE / ASSISTANT_TOOL_CALL
   - should_persist = True
   ↓
4. MessageHandler._persist_to_db()
   - 检查 content/thinking 不为空
   - 调用 get_scheduler().send_task("engine_persist_message", ...)
   ↓
5. Huey 执行 persist_message_task()
   - ✅ 接受 is_visible 参数
   - 写入 Message 表

工具消息流程类似
```

---

## 🔍 如何验证修复

### 1. 检查日志输出
重启应用后，观察日志中是否有:
```
[UnifiedHandler] AI message classified as: assistant_response, persist=True
[UnifiedHandler] Persisting ai message (seq=X, cat=assistant_response)
[Huey] Task engine_persist_message executed successfully
```

### 2. 检查数据库
```sql
SELECT * FROM messages 
WHERE thread_id = 'your-thread-id' 
ORDER BY sequence_number DESC 
LIMIT 10;
```

### 3. 检查 Huey 日志
```
huey - INFO - Executing app.infrastructure.queue.huey_queue.engine_persist_message: xxx
```

不应再出现:
```
TypeError: persist_message_task() got an unexpected keyword argument 'is_visible'
```

---

## 📝 修复的文件清单

1. `backend/app/core/engine/tasks.py`
   - 添加 `is_visible: bool = True` 参数
   - 修改 visibility 计算逻辑使用传入的参数

2. `backend/app/core/callbacks/database_logger.py`
   - 取消注释 `on_tool_start` 方法

3. `backend/app/core/messaging/handler.py`
   - 添加 INFO 级别的调试日志

---

## ⚠️ 如果问题仍然存在

检查以下方面:

1. **Huey Consumer 是否运行？**
   ```bash
   ps aux | grep huey
   ```

2. **数据库连接是否正常？**
   检查 `session_scope()` 是否抛出异常

3. **消息内容是否为空？**
   如果 `content` 和 `thinking` 都为空，消息会被跳过

4. **去重机制是否触发？**
   2 秒内相同内容的消息会被视为重复
