# 文件操作工具澄清：它们从来就不是 Facade

## 澄清误解

**文件操作工具（read_file, write_file, edit_file）一直都是原子化的，从来就不是 Facade 模式。**

---

## 当前文件操作工具状态

```python
# 文件操作工具 - 从来都是原子化的 ✅

# backend/app/domain/tools/files/read_file.py
@evoloop_tool
async def read_file(path: str, ...) -> str:
    """Read file contents."""
    # 单一职责：读取文件

# backend/app/domain/tools/files/write_file.py  
@evoloop_tool
async def write_file(path: str, content: str, ...) -> str:
    """Write file contents."""
    # 单一职责：写入文件

# backend/app/domain/tools/files/edit_file.py
@evoloop_tool
async def edit_file(path: str, target: str, replacement: str, ...) -> str:
    """Edit file contents."""
    # 单一职责：编辑文件
```

**这些工具从来就不是 Facade，所以不存在"拆分文件操作工具"这回事。**

---

## 对比：文件操作 vs Facade

### 文件操作工具（好的原子化设计）

```python
# 3个独立工具，每个做一件事
read_file(path="...")
write_file(path="...", content="...")
edit_file(path="...", target="...", replacement="...")

# 如果这是 Facade，会是什么样子：
file_manager(action="read", path="...")
file_manager(action="write", path="...", content="...")
file_manager(action="edit", path="...", target="...", replacement="...")
```

**幸运的是，我们从来就不是第二种设计。**

---

## 真正被拆分的 Facade

### ❌ explore_codebase（有害的 Facade）- 已拆分

```python
# 拆分前（坏的 Facade）
explore_codebase(
    action: Literal[
        "search_symbol",      # ❌ 查找定义
        "search_text",        # ❌ 文本搜索  
        "semantic_code_search", # ❌ 语义搜索
        "analyze_impact"      # ❌ 影响分析
    ]
)
# 问题：这些 action 业务领域完全不同

# 拆分后（好的原子化）
find_symbol(name="...")        # ✅ 查找定义
search_code(pattern="...")     # ✅ 代码搜索
ask_codebase(question="...")   # ✅ 语义查询
analyze_impact(symbol="...")   # ✅ 影响分析
```

### ❌ consult_lsp（有害的 Facade）- 已拆分

```python
# 拆分前（坏的 Facade）
consult_lsp(
    action: Literal["check_errors", "find_definition", "hover"],
    file_path: str,
    line: int | None,        # ❌ 有的 action 需要
    character: int | None     # ❌ 有的 action 不需要
)

# 拆分后（好的原子化）
check_types(file_path="...")   # ✅ 只需文件路径
find_symbol(name="...")        # ✅ 只需符号名
inspect_symbol(name="...")     # ✅ 只需符号名
```

---

## 文件操作工具 vs 代码探索工具对比

| 工具组 | 设计模式 | 状态 | 说明 |
|--------|----------|------|------|
| **文件操作** | 原子化工具 | ✅ 从来就很好 | read_file, write_file, edit_file 各自独立 |
| **代码探索** | 有害的 Facade | ✅ 已拆分 | explore_codebase → 4个原子工具 |
| **LSP 查询** | 有害的 Facade | ✅ 已拆分 | consult_lsp → 3个原子工具 |

---

## 为什么文件操作不需要拆分？

因为它们**从来就不是 Facade**：

1. **没有 action 参数**
   ```python
   read_file(path="...")  # ✅ 没有 action 参数
   # 而不是：
   file_manager(action="read", path="...")  # ❌ 这才是 Facade
   ```

2. **单一职责**
   - read_file 只做一件事：读取
   - write_file 只做一件事：写入
   - edit_file 只做一件事：编辑

3. **参数一致**
   - 都有 `path` 参数
   - 其他参数与各自职责匹配

---

## 总结

| 问题 | 答案 |
|------|------|
| 文件操作工具是 Facade 吗？ | **不是**，从来就不是 |
| 文件操作工具需要拆分吗？ | **不需要**，它们已经是好的原子化设计 |
| explore_codebase 是 Facade 吗？ | **是**，有害的 Facade |
| explore_codebase 需要拆分吗？ | **已拆分**，现在好了 |
| consult_lsp 是 Facade 吗？ | **是**，有害的 Facade |
| consult_lsp 需要拆分吗？ | **已拆分**，现在好了 |

**文件操作工具是系统的优秀设计范例，不需要任何改动。**
