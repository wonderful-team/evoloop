# Memory 工具链深度分析报告

## 概览

当前 memory 相关工具分布在 4 个文件中：

| 文件 | 工具/函数 | 类型 | YAML配置 |
|------|-----------|------|----------|
| `memory_tools.py` | `search_history`, `save_preference`, `add_concept`, `find_related_episodes` | **@evoloop_tool** | ✅ Worker |
| `memory_search.py` | `search_chat_history` | **@evoloop_tool** | ❌ 未配置 |
| `memory_mgmt.py` | `compress_history` | **@evoloop_tool** | ❌ 未配置 |
| `memory.py` | `*_impl` 函数 | 内部实现 | N/A |

---

## 🔴 关键问题

### 问题 1：工具调用工具（设计缺陷）

**代码路径：** `memory_tools.py:57-60`

```python
# search_history (工具)
return await search_chat_history.ainvoke(
    {"query": query, "limit": limit},
    config=config
)
```

**问题分析：**
- `search_history` 是一个 `@evoloop_tool` 工具（暴露给 LLM）
- 它内部调用了另一个 `@evoloop_tool` 工具 `search_chat_history`
- 这是**工具调用工具**的反模式

**后果：**
1. 不必要的性能开销（工具序列化/反序列化）
2. LLM 理论上可能直接调用 `search_chat_history`（如果被发现）
3. 调试困难（堆栈跟踪更深）
4. 两个工具的功能几乎完全相同（重复）

---

### 问题 2：重复工具（功能完全相同）

| 工具A | 工具B | 重叠度 |
|-------|-------|--------|
| `search_history` (memory_tools.py) | `search_chat_history` (memory_search.py) | **95%** |

**功能对比：**

| 特性 | `search_history` | `search_chat_history` |
|------|------------------|----------------------|
| 搜索对话历史 | ✅ | ✅ |
| 自动获取 thread_id | ✅ | ✅ |
| 参数: query | ✅ | ✅ |
| 参数: limit | ✅ | ✅ |
| 参数: thread_id | ❌ | ✅ (可选) |
| YAML配置 | ✅ Worker | ❌ 未配置 |

**结论：** 两个工具功能几乎完全相同，应该合并。

---

### 问题 3：孤儿工具（注册但未使用）

**`compress_history`** (`memory_mgmt.py`)

```python
@evoloop_tool(
    name_map={"zh": "压缩历史", "en": "Compress History"}
)
async def compress_history(...)
```

**状态：**
- ✅ 被 `@evoloop_tool` 装饰 → 会被注册
- ✅ 在 `tools/__init__.py` 中被导入
- ❌ **未在 `agent_main.yaml` 任何节点中配置**

**后果：**
- 工具被注册但永远不会被分配给任何节点
- 代码冗余，维护负担
- LLM 无法使用（虽然注册了，但不在节点工具列表中）

---

### 问题 4：实现分散

**概念记忆功能分散在3个地方：**

```
memory_tools.py:add_concept()          → 添加单个概念 (YAML配置)
knowledge.py:memorize_concepts()       → 批量添加概念 (YAML配置)  
memory.py:add_concept_impl()           → 实际实现
```

**问题：**
- `add_concept` 和 `memorize_concepts` 功能重叠
- Agent 困惑：什么时候用单个，什么时候用批量？
- 实际上 `memorize_concepts` 是异步任务，`add_concept` 是同步执行

---

## 🟢 建议清理方案

### 方案概述

```
清理前 (5个工具 + 2个内部函数):
├─ search_history (工具) ──────┐
├─ search_chat_history (工具) ─┤ 重复！
├─ compress_history (工具) ────┤ 孤儿！
├─ save_preference (工具) ─────┤
├─ add_concept (工具) ─────────┤
├─ find_related_episodes (工具)┤
├─ memorize_concepts (工具) ───┤ 功能重叠
└─ *_impl (内部函数)

清理后 (4个工具):
├─ search_history (工具) ──────┤ 保留，修复实现
├─ save_preference (工具) ─────┤ 保留
├─ add_concept (工具) ─────────┤ 保留（Finish节点改用此工具）
└─ find_related_episodes (工具)┤ 保留
```

---

## 🔧 具体实施步骤

### Step 1: 修复 `search_history` 实现

**当前代码：**
```python
# memory_tools.py
from app.domain.tools.memory_search import search_chat_history

async def search_history(...):
    return await search_chat_history.ainvoke(...)  # ❌ 工具调用工具
```

**修改为：**
```python
# memory_tools.py
from app.core.memory import memory_manager  # 直接调用底层
from app.utils import ContentFormatter

async def search_history(query: str, limit: int = 10, ...):
    """Search conversation history..."""
    ctx = ContextManager.current()
    thread_id = ctx.thread_id
    
    results = await memory_manager.search_messages(query, thread_id, limit)
    if not results:
        return ContentFormatter.chat_search_results(query, [])
    return ContentFormatter.chat_search_results(query, results)
```

---

### Step 2: 删除 `memory_search.py`

**操作：**
```bash
rm backend/app/domain/tools/memory_search.py
```

**更新 `tools/__init__.py`：**
```python
# 删除此行
from app.domain.tools import memory_search
```

**影响：**
- `search_chat_history` 工具被删除
- `search_history` 功能不变（已修复实现）

---

### Step 3: 删除 `memory_mgmt.py`（或启用）

**选项A：删除（推荐）**
```bash
rm backend/app/domain/tools/memory_mgmt.py
```

**更新 `tools/__init__.py`：**
```python
# 删除此行
from app.domain.tools import memory_mgmt
```

**选项B：启用（如需使用 compress_history）**
在 `agent_main.yaml` 的 supervisor 节点添加：
```yaml
- compress_history
```

---

### Step 4: 统一概念记忆工具

**当前状态：**
- `add_concept` - 同步添加单个概念
- `memorize_concepts` - 异步批量添加（Celery任务）

**建议：** 保留两者但明确分工

| 工具 | 场景 | 保留/删除 |
|------|------|----------|
| `add_concept` | Worker 实时添加概念 | ✅ 保留 |
| `memorize_concepts` | Finish 节点批量沉淀知识 | ✅ 保留（但需重命名） |

**重命名建议：**
```python
# 当前
memorize_concepts(concepts: list)  # Finish节点

# 建议改为
save_concepts(concepts: list)      # 与 save_preference 命名一致
```

**更新 `agent_main.yaml`：**
```yaml
finish:
  tools:
    # - memorize_concepts  # ❌ 删除
    - add_concept          # ✅ 复用 Worker 工具（如果功能满足）
    # 或
    - save_concepts        # ✅ 如果保持异步批量特性
```

---

### Step 5: 更新 `memory.py` 文档

**当前注释过时：**
```python
"""
Memory tool implementations - internal use only.
These functions are used by the manage_memory facade tool.  # ❌ facade 已删除
"""
```

**更新为：**
```python
"""
Memory tool implementations - internal use only.
These functions are used by atomic memory tools (search_history, save_preference, etc.).
They are NOT exposed as standalone tools.
"""
```

---

## 📊 清理前后对比

| 指标 | 清理前 | 清理后 |
|------|--------|--------|
| Memory 相关工具文件 | 4个 | 2个 (`memory_tools.py`, `memory.py`) |
| @evoloop_tool 工具数 | 7个 | 4-5个 |
| 孤儿工具 | 2个 (`search_chat_history`, `compress_history`) | 0个 |
| 功能重复 | 高 | 无 |
| Agent 认知负担 | 高（多个相似工具） | 低（清晰分工） |

---

## ⚠️ 注意事项

1. **`search_chat_history` 的 thread_id 参数**
   - `search_chat_history` 支持手动传入 `thread_id`
   - `search_history` 自动从 context 获取
   - 清理后如果需要跨线程搜索功能，需要给 `search_history` 添加 `thread_id` 可选参数

2. **`compress_history` 功能**
   - 如果未来需要历史压缩功能，可以重新实现
   - 当前代码返回 `COMPRESSION_SIGNAL`，需要 Supervisor 特殊处理
   - 确认无此需求后再删除

3. **`memorize_concepts` 异步特性**
   - 当前实现使用 Celery 异步任务
   - `add_concept` 是同步执行
   - Finish 节点如果需要异步批量处理，保留 `memorize_concepts`（重命名为 `save_concepts`）

---

## ✅ 实施检查清单

- [ ] 修改 `memory_tools.py:search_history` - 直接调用 memory_manager
- [ ] 删除 `memory_search.py`
- [ ] 从 `tools/__init__.py` 删除 `memory_search` 导入
- [ ] 决定 `compress_history` 命运（删除或启用）
- [ ] 如需删除，删除 `memory_mgmt.py` 并从 `__init__.py` 移除
- [ ] 如需启用，添加到 `agent_main.yaml` supervisor 节点
- [ ] 更新 `memory.py` 文档注释
- [ ] 验证 `agent_main.yaml` 配置
- [ ] 运行测试验证功能正常
