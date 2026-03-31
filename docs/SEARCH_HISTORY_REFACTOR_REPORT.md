# search_history 修复与 search_chat_history 对比报告

## ✅ 修复完成

### 修复内容

**文件：** `backend/app/domain/tools/memory_tools.py`

**修改1：导入优化**
```python
# 修改前
from app.domain.tools.memory_search import search_chat_history

# 修改后
from app.core.context.manager import ContextManager
from app.core.memory import memory_manager
from app.utils import ContentFormatter
```

**修改2：实现修复**
```python
# 修改前（工具调用工具 - 反模式）
return await search_chat_history.ainvoke(
    {"query": query, "limit": limit},
    config=config
)

# 修改后（直接调用底层实现）
ctx = ContextManager.current()
thread_id = ctx.thread_id

results = await memory_manager.search_messages(query, thread_id, limit)

if not results:
    return ContentFormatter.chat_search_results(query, [])

return ContentFormatter.chat_search_results(query, results)
```

---

## 📊 工具对比分析

### search_history (修复后) vs search_chat_history (待删除)

| 对比维度 | search_history | search_chat_history | 差异分析 |
|----------|----------------|---------------------|----------|
| **文件位置** | memory_tools.py | memory_search.py | 不同文件 |
| **YAML配置** | ✅ Worker节点 | ❌ 未配置 | search_chat_history 孤儿工具 |
| **thread_id 参数** | ❌ 不支持 | ✅ 可选支持 | search_chat_history 更灵活 |
| **自动获取 thread_id** | ✅ | ✅ | 两者都从 Context 获取 |
| **limit 参数** | ✅ | ✅ | 相同 |
| **实现方式** | 直接调用 MemoryManager | 直接调用 MemoryManager | **完全相同！** |
| **格式化输出** | ContentFormatter | ContentFormatter | **完全相同！** |
| **文档质量** | 简洁清晰 | 非常详细 | search_chat_history 文档更优 |

---

## 🔍 关键差异详解

### 差异1：thread_id 参数支持

**search_chat_history：**
```python
async def search_chat_history(query: str, thread_id: Optional[str] = None, limit: int = 10):
    # 支持手动传入 thread_id 搜索其他对话
    if not thread_id:
        ctx = ContextManager.current()
        thread_id = ctx.thread_id
```

**search_history：**
```python
async def search_history(query: str, limit: int = 10, ...):
    # 自动从 context 获取，不支持手动指定
    ctx = ContextManager.current()
    thread_id = ctx.thread_id
```

**评估：** 
- search_history 当前不支持跨对话搜索
- 如需此功能，需给 search_history 添加可选的 `thread_id` 参数

### 差异2：文档详细程度

**search_chat_history 文档优势：**
- 更详细的 KEYWORD EXTRACTION STRATEGY 说明
- 更多使用示例
- 强调 SQL LIKE 匹配（非语义搜索）

**建议：** 将 search_chat_history 的优质文档内容合并到 search_history

---

## 📋 代码实现对比

### search_history (修复后)

```python
@evoloop_tool(
    is_pollable=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.search_history",
    name_map={"zh": "搜索历史", "en": "Search History"}
)
async def search_history(
    query: str,
    limit: int = 10,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """Search conversation history for past decisions or context."""
    if not query:
        return "Error: query is required."
    
    # 直接调用底层实现 ✅
    ctx = ContextManager.current()
    thread_id = ctx.thread_id
    
    results = await memory_manager.search_messages(query, thread_id, limit)
    
    if not results:
        return ContentFormatter.chat_search_results(query, [])
    
    return ContentFormatter.chat_search_results(query, results)
```

### search_chat_history (待删除)

```python
@evoloop_tool(
    is_pollable=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.manage_memory",  # 过时模板
    name_map={"zh": "搜索对话历史", "en": "Search Chat History"}
)
async def search_chat_history(query: str, thread_id: Optional[str] = None, limit: int = 10):
    """Search the conversation history..."""  # 文档更详细
    if not thread_id:
        ctx = ContextManager.current()
        thread_id = ctx.thread_id

    results = await memory_manager.search_messages(query, thread_id, limit)
    
    if not results:
        return ContentFormatter.chat_search_results(query, [])

    return ContentFormatter.chat_search_results(query, results)
```

---

## 🗑️ 删除 search_chat_history 的步骤

### 步骤1：可选增强 search_history

如果需要保留跨对话搜索能力，增强 search_history：

```python
async def search_history(
    query: str,
    limit: int = 10,
    thread_id: str | None = None,  # 添加可选参数
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """..."""
    if not query:
        return "Error: query is required."
    
    ctx = ContextManager.current()
    # 如果未提供 thread_id，使用当前上下文
    target_thread = thread_id or ctx.thread_id
    
    results = await memory_manager.search_messages(query, target_thread, limit)
    ...
```

### 步骤2：合并优质文档

将 search_chat_history 的详细文档内容合并到 search_history

### 步骤3：删除文件

```bash
rm backend/app/domain/tools/memory_search.py
```

### 步骤4：更新导入

```python
# backend/app/domain/tools/__init__.py
# 删除此行
from app.domain.tools import memory_search
```

---

## ✅ 修复验证

### 语法检查
```bash
python3 -m py_compile backend/app/domain/tools/memory_tools.py
# ✅ 通过
```

### 导入检查
```python
# 验证修复后的导入
from app.domain.tools.memory_tools import search_history
# ✅ 成功
```

---

## 🎯 决策建议

| 方案 | 操作 | 影响 |
|------|------|------|
| **A. 直接删除** | 保持 search_history 现状，删除 search_chat_history | 失去跨对话搜索能力 |
| **B. 增强后删除** | 给 search_history 添加 `thread_id` 参数，然后删除 | 功能完全对齐，推荐 |
| **C. 保留两者** | 区分用途 | 增加复杂性，不推荐 |

**推荐：方案 B** - 功能完整且保持工具精简
