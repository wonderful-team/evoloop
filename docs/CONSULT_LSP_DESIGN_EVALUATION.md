# consult_lsp 工具定位深度评估

## 评估结论

**建议：删除 `consult_lsp` 作为 Agent 工具的暴露，将其功能整合到代码探索工具中或作为系统底层能力。**

LSP（Language Server Protocol）是技术实现细节，Agent 不应该直接操作 LSP 协议。

---

## 一、当前混乱的代码探索体系

### 1.1 功能重叠矩阵

查找符号定义，当前有 **3 种方式**：

| 工具 | 位置 | 实现方式 | 调用路径 |
|------|------|----------|----------|
| `find_definition` | `analysis/tools.py:14` | Knowledge Graph + Grep | 直接调用 |
| `explore_codebase(action="search_symbol")` | `facades.py:104` | 调用 find_definition | Facade |
| `consult_lsp(action="find_definition")` | `coding/lsp.py:263` | LSP 协议 | 独立工具 |

**问题：** 三个工具做同一件事，Agent 困惑该用哪个。

### 1.2 当前调用关系图

```
Agent 想查找符号定义
         │
    选择困惑：
    ├─ find_definition("UserService")              # 推荐 ✅
    ├─ explore_codebase(action="search_symbol",   # Facade ⚠️
    │                    query="UserService")
    └─ consult_lsp(action="find_definition",      # LSP ❌
                    file_path="...",
                    line=10, character=5)
```

**Agent 的认知负担：**
- 为什么有 3 个工具做同一件事？
- 什么时候用 LSP？什么时候用 Graph？
- 为什么 LSP 需要行号列号，其他不需要？

---

## 二、consult_lsp 的问题分析

### 2.1 抽象层次错误

**当前设计：**
```python
@evoloop_tool
async def consult_lsp(
    action: Literal["check_errors", "find_definition", "hover"],
    file_path: str,
    line: int | None = None,
    character: int | None = None,
) -> str
```

**问题：** Agent 需要知道：
- LSP 是什么？
- 何时需要 check_errors vs find_definition？
- 如何获取 line 和 character？

**对比：** `find_definition` 只需要符号名：
```python
find_definition(symbol_name="UserService")  # 简单！
```

### 2.2 技术细节暴露

**Agent 调用 consult_lsp 的复杂性：**
```python
# Agent 想查看函数定义
consult_lsp(
    action="find_definition",
    file_path="src/services/user.py",
    line=42,      # Agent 如何知道是第 42 行？
    character=15  # Agent 如何知道是第 15 列？
)
```

**对比 find_definition：**
```python
find_definition(symbol_name="UserService")
# 系统自动在 Graph 中查找，无需位置信息
```

### 2.3 与现有工具冲突

| 功能 | consult_lsp | find_definition | 优劣对比 |
|------|-------------|-----------------|----------|
| 查找定义 | 需要精确位置 | 只需要符号名 | find_definition 更优 |
| 错误检查 | check_errors | 无对应功能 | consult_lsp 独有 |
| 悬停信息 | hover | 无对应功能 | consult_lsp 独有 |

**问题：** 只有 check_errors 和 hover 是 consult_lsp 独有的。

---

## 三、定位建议

### 方案 A：完全删除，功能整合（推荐）

**思路：** 将 LSP 能力整合到更高层次的工具中，不直接暴露给 Agent。

**整合方案：**

```python
# 1. find_definition 增强：内部使用 LSP 作为回退
async def find_definition(symbol_name: str):
    # 1. 先查 Knowledge Graph
    results = await graph.find_symbol(symbol_name)
    if results:
        return results
    
    # 2. LSP 回退（自动定位，无需 Agent 提供行号）
    lsp_results = await lsp_manager.find_symbol_by_name(symbol_name)
    if lsp_results:
        return lsp_results
    
    # 3. Grep 回退
    return grep_search(symbol_name)

# 2. read_file 增强：自动包含错误检查
async def read_file(file_path: str, include_diagnostics: bool = True):
    content = read_file_content(file_path)
    
    if include_diagnostics:
        # 自动调用 LSP 检查错误，无需 Agent 手动调用
        errors = await lsp_manager.check_errors(file_path)
        if errors:
            content += f"\n\n[Diagnostics]: {errors}"
    
    return content
```

**Agent 使用方式：**
```python
# 查找定义 - 系统自动使用最佳后端
find_definition(symbol_name="UserService")

# 读取文件 - 自动包含诊断信息
read_file("src/services/user.py")
```

**优势：**
- ✅ Agent 无需关心 LSP 协议
- ✅ 自动选择最佳实现（Graph/LSP/Grep）
- ✅ 无需提供行号列号
- ✅ 代码读取自动获得错误检查

---

### 方案 B：保留为系统底层能力

**思路：** consult_lsp 不作为 Agent 工具，只供其他工具内部调用。

**实现：**
```python
# coding/lsp.py - 移除 @evoloop_tool，改为内部类
class LSPCodeAnalyzer:
    """LSP 代码分析器 - 仅供内部工具使用"""
    
    async def find_definition(self, file_path: str, line: int, char: int):
        # 供 find_definition 工具内部调用
        pass
    
    async def check_errors(self, file_path: str):
        # 供 read_file 工具内部调用
        pass

# analysis/tools.py
@evoloop_tool
async def find_definition(symbol_name: str):
    # 内部使用 LSP 作为回退
    lsp = LSPCodeAnalyzer()
    # ...
```

**Agent 可见工具：**
- ✅ `find_definition` - 符号查找
- ✅ `read_file` - 文件读取（自动错误检查）
- ❌ `consult_lsp` - 删除

---

### 方案 C：重构为语义化工具

**思路：** 保留 LSP 能力，但用更语义化的命名。

**重构：**
```python
# 删除 consult_lsp，改为：

@evoloop_tool
async def check_code_errors(file_path: str):
    """检查代码错误"""
    # 内部使用 LSP
    
@evoloop_tool  
async def show_type_info(file_path: str, symbol_name: str):
    """显示类型信息（替代 hover）"""
    # 内部使用 LSP
```

**对比：**
| consult_lsp (旧) | 新工具 | 改进 |
|------------------|--------|------|
| consult_lsp(action="check_errors") | check_code_errors() | 语义清晰 |
| consult_lsp(action="hover") | show_type_info() | 语义清晰 |
| consult_lsp(action="find_definition") | 删除（已有 find_definition） | 去重 |

---

## 四、设计原则验证

### 4.1 抽象层次原则

**原则：** Agent 工具应该是**业务语义**的，不是**技术实现**的。

| 工具 | 抽象层次 | 评价 |
|------|----------|------|
| `find_definition` | 业务语义 ✅ | "找到这个符号的定义" |
| `consult_lsp` | 技术实现 ❌ | "使用 LSP 协议查询" |

### 4.2 认知负担原则

**原则：** Agent 不应该关心技术细节。

**consult_lsp 的认知负担：**
- 需要理解 LSP 是什么
- 需要知道何时使用 LSP 而非其他工具
- 需要提供精确的行号列号

**find_definition 的认知负担：**
- 只需要提供符号名 ✅

### 4.3 单一职责原则

**原则：** 一个工具做一件事。

**consult_lsp 的问题：**
- 一个工具做 3 件事（check_errors, find_definition, hover）
- 且与其他工具职责重叠

---

## 五、实施建议

### 推荐方案：方案 A + 方案 B 混合

**Phase 1: 删除 consult_lsp 工具暴露**
- 从 `agent_main.yaml` 移除 `consult_lsp`
- 保留 `LSPManager` 类供内部使用

**Phase 2: 整合能力到现有工具**
```python
# find_definition 增强 - 添加 LSP 回退
@evoloop_tool
async def find_definition(symbol_name: str):
    '''
    Find symbol definition using Knowledge Graph, LSP, or Grep.
    Automatically selects the best backend.
    '''
    # 1. Graph
    # 2. LSP (自动定位，无需行号)
    # 3. Grep

# read_file 增强 - 自动错误检查
@evoloop_tool
async def read_file(path: str, show_errors: bool = True):
    '''
    Read file content. Optionally includes LSP diagnostics.
    '''
    content = read_content(path)
    if show_errors:
        diagnostics = await lsp.check_errors(path)
        # 追加到返回内容
```

**Phase 3: 添加语义化类型查询工具（可选）**
```python
@evoloop_tool
async def inspect_type(file_path: str, symbol_name: str):
    '''
    Show type information for a symbol.
    Equivalent to IDE hover.
    '''
    # 内部使用 LSP hover
```

---

## 六、总结

### 核心观点

1. **LSP 是技术实现，不是业务语义**
   - Agent 应该说 "查找定义"，不是 "使用 LSP"

2. **功能重叠导致 Agent 困惑**
   - 3 个工具做同一件事，选择成本高

3. **行号列号要求不合理**
   - Agent 不应该关心代码的物理位置

4. **check_errors 和 hover 应该自动提供**
   - 读取代码时自动检查错误
   - 不需要 Agent 显式调用

### 最终建议

**删除 `consult_lsp` 作为 Agent 工具**，改为：
1. `find_definition` 内部使用 LSP 作为回退
2. `read_file` 自动包含 LSP 错误检查
3. （可选）添加 `inspect_type` 语义化工具

**Worker 工具数：44 → 43**

**Agent 认知负担：显著降低**
- 无需理解 LSP 协议
- 无需提供行号列号
- 代码探索工具统一
