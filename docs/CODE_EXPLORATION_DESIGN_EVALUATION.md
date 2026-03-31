# 代码探索工具设计层面深度评估

## 核心问题：抽象层次混乱

当前代码探索工具的设计违反了**单一抽象层次原则**（Single Level of Abstraction Principle）。

Agent 被迫在三个不同抽象层次之间做选择：
- **业务语义层**：`find_definition(symbol_name)`
- **Facade 层**：`explore_codebase(action="search_symbol", query=...)`
- **技术实现层**：`consult_lsp(action="find_definition", line=..., char=...)`

---

## 一、理想 vs 现实

### 1.1 Agent 的期望（理想）

```
Agent: 我需要找到 UserService 的定义
System: （自动选择最佳方式）
        - 先在 Knowledge Graph 查
        - 如果没找到，用 LSP 查
        - 如果还没找到，用 Grep 查
Agent: （得到结果，不关心怎么找到的）
```

### 1.2 当前的现实（混乱）

```
Agent: 我需要找到 UserService 的定义
       等等，我有三个选择：
       
       A. find_definition("UserService")
          - 用 Graph 还是 Grep？不清楚
          - 这个最简单，就选这个？
       
       B. explore_codebase(action="search_symbol", query="UserService")
          - Facade 工具，看起来高级
          - 但 action 参数是什么？search_symbol vs search_text？
       
       C. consult_lsp(action="find_definition", file_path="...", line=..., char=...)
          - LSP 好像很专业
          - 但需要行号和列号，我怎么知道？
       
Agent: （困惑 5 秒钟，随机选一个）
```

**这是典型的选择悖论**（Paradox of Choice）：
- 更多选择 ≠ 更好体验
- 3 个工具做同一件事 → Agent 选择困难 → 效率下降

---

## 二、设计原则违背分析

### 2.1 违背：单一抽象层次原则

**原则：** 同一层级的工具应该提供相同抽象层次的接口。

**当前状态：**
```
Layer 1 (语义): find_definition(symbol_name)
Layer 2 (Facade): explore_codebase(action="...", query="...")
Layer 3 (技术): consult_lsp(action="...", line=..., char=...)
```

**问题：** Agent 被迫理解三个不同层次的概念。

**正确设计：**
```
Layer 1 (语义): 
  - find_definition(symbol_name)
  - search_code(pattern)
  - analyze_dependencies(symbol)
  
（底层自动选择最佳技术实现：Graph/LSP/Grep）
```

### 2.2 违背：最少知识原则（迪米特法则）

**原则：** Agent 不应该知道系统如何实现功能。

**当前：**
```python
# Agent 需要知道 LSP 协议的存在
consult_lsp(action="find_definition", ...)

# Agent 需要知道 Facade 的 action 映射
explore_codebase(action="search_symbol", ...)
```

**正确：**
```python
# Agent 只需要知道"我要找定义"
find_definition(symbol_name="UserService")
# 系统自动在 Graph/LSP/Grep 中选择
```

### 2.3 违背：命令-查询分离（CQS）

**原则：** 代码探索是纯查询操作，不应该暴露实现细节。

**当前问题：**
- `consult_lsp` 暴露了 LSP 协议的复杂性
- `explore_codebase` 的 Facade 模式增加了不必要的间接层

---

## 三、重构方案

### 方案：统一代码探索层（Unified Code Exploration Layer）

**核心理念：**
> Agent 说**要找什么**，系统决定**怎么找**。

#### 3.1 新的工具集（6个语义化工具）

```python
# 1. 查找定义（替代 find_definition + explore_codebase(action="search_symbol") + consult_lsp(action="find_definition")）
@evoloop_tool
async def find_symbol(name: str) -> str:
    """
    Find the definition of a symbol (class, function, variable).
    
    Backend priority:
    1. Knowledge Graph (fastest, most accurate)
    2. LSP (real-time, language-aware)
    3. Grep (fallback, always available)
    
    Args:
        name: Symbol name (e.g., "UserService", "process_data")
    
    Returns:
        Definition location(s) with file path and line number
    """
    # 自动选择最佳后端
    # 对 Agent 透明

# 2. 搜索代码（替代 explore_codebase(action="search_text") + search_files）
@evoloop_tool  
async def search_code(pattern: str, scope: str | None = None) -> str:
    """
    Search for code patterns using regex or semantic matching.
    
    Args:
        pattern: Search pattern (regex supported)
        scope: Optional file pattern (e.g., "*.py", "src/services/")
    
    Returns:
        Matching code snippets with context
    """

# 3. 语义搜索（替代 explore_codebase(action="semantic_code_search")）
@evoloop_tool
async def ask_codebase(question: str) -> str:
    """
    Ask a natural language question about the codebase.
    
    Examples:
        "How does authentication work?"
        "Where is the database connection configured?"
    
    Returns:
        Relevant code snippets and explanations
    """
    # 使用 Vector DB + LLM

# 4. 影响分析（替代 explore_codebase(action="analyze_impact")）
@evoloop_tool
async def analyze_impact(symbol: str) -> str:
    """
    Analyze what would be affected by changing a symbol.
    
    Args:
        symbol: The symbol to analyze (e.g., "UserService.update")
    
    Returns:
        List of files and code locations that depend on this symbol
    """
    # 使用 Knowledge Graph 的依赖关系

# 5. 类型检查（替代 consult_lsp(action="check_errors")）
@evoloop_tool
async def check_types(file_path: str | None = None) -> str:
    """
    Check for type errors and code issues.
    
    Args:
        file_path: Optional specific file. If None, checks all modified files.
    
    Returns:
        List of errors and warnings with severity
    """
    # 自动使用 LSP，但 Agent 不知道

# 6. 查看类型（替代 consult_lsp(action="hover")）
@evoloop_tool
async def inspect_symbol(symbol: str, file_path: str | None = None) -> str:
    """
    Show detailed information about a symbol (type, docs, usage).
    
    Equivalent to IDE's "hover" or "go to definition + peek info".
    
    Args:
        symbol: Symbol name
        file_path: Optional hint about which file (for disambiguation)
    """
    # 内部使用 LSP hover + Graph metadata
```

#### 3.2 工具对比

| 旧工具 | 新工具 | 改进 |
|--------|--------|------|
| `find_definition` | `find_symbol` | 统一命名 |
| `explore_codebase(action="search_symbol")` | `find_symbol` | 消除 Facade |
| `explore_codebase(action="search_text")` | `search_code` | 语义清晰 |
| `explore_codebase(action="semantic_code_search")` | `ask_codebase` | 自然语言 |
| `explore_codebase(action="analyze_impact")` | `analyze_impact` | 保留，更好文档 |
| `consult_lsp(action="check_errors")` | `check_types` | 语义化 |
| `consult_lsp(action="find_definition")` | `find_symbol` | 统一入口 |
| `consult_lsp(action="hover")` | `inspect_symbol` | 语义化 |
| `search_files` | `search_code` | 统一 |

#### 3.3 工具数量变化

**当前：**
```
- find_definition
- explore_codebase (4个action)
- consult_lsp (3个action)
- search_files
总计: 4个工具，但 explore_codebase 和 consult_lsp 是 Facade
```

**重构后：**
```
- find_symbol
- search_code
- ask_codebase
- analyze_impact
- check_types
- inspect_symbol
总计: 6个清晰的语义化工具
```

---

## 四、实现架构

### 4.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│  AGENT LAYER (6个语义化工具)                                  │
│  ├─ find_symbol(name)                                        │
│  ├─ search_code(pattern)                                     │
│  ├─ ask_codebase(question)                                   │
│  ├─ analyze_impact(symbol)                                   │
│  ├─ check_types(file?)                                       │
│  └─ inspect_symbol(symbol)                                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  STRATEGY LAYER (自动选择最佳后端)                            │
│  ├─ GraphQueryEngine (Knowledge Graph)                      │
│  ├─ LSPClient (Language Server)                             │
│  └─ GrepEngine (Text Search)                                │
│                                                              │
│  智能选择逻辑：                                               │
│  1. Graph 有数据？→ 用 Graph (最快)                          │
│  2. 文件已打开/有 LSP？→ 用 LSP (最准)                        │
│  3. 否则 → Grep (兜底)                                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  IMPLEMENTATION LAYER (具体实现)                              │
│  ├─ Neo4j Graph DB                                           │
│  ├─ LSP Servers (Pyright, tsserver, etc.)                   │
│  └─ ripgrep / grep                                           │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 智能选择示例

```python
class CodeExplorationEngine:
    """代码探索引擎 - 自动选择最佳后端"""
    
    async def find_symbol(self, name: str) -> str:
        # 1. 尝试 Knowledge Graph (O(1) 复杂度)
        result = await self.graph.find_symbol(name)
        if result:
            return result
        
        # 2. 尝试 LSP (需要文件路径，自动推导)
        file_paths = self._guess_file_paths(name)
        for path in file_paths:
            if self.lsp.is_file_open(path):
                result = await self.lsp.find_definition(path, name)
                if result:
                    return result
        
        # 3. 回退到 Grep (O(n) 复杂度，但总能工作)
        return await self.grep.find_symbol(name)
    
    async def check_types(self, file_path: str | None = None) -> str:
        # 自动选择 LSP（类型检查必须有 LSP）
        if file_path:
            return await self.lsp.check_errors(file_path)
        
        # 如果没有指定文件，检查所有已打开的文件
        return await self.lsp.check_all_open_files()
```

---

## 五、迁移计划

### Phase 1: 删除旧工具
```bash
# 从 agent_main.yaml 移除
- explore_codebase
- consult_lsp
- search_files  # 与 search_code 合并
```

### Phase 2: 创建统一引擎
```python
# 新文件：app/domain/codebase/exploration/engine.py
class CodeExplorationEngine:
    """
    统一的代码探索引擎
    自动在 Graph/LSP/Grep 之间选择最佳后端
    """
    pass
```

### Phase 3: 实现新工具
逐个实现 6 个语义化工具，复用现有实现：
```python
# find_symbol - 复用 find_definition + consult_lsp 的逻辑
# search_code - 复用 search_files 的逻辑
# ask_codebase - 复用 semantic_code_search 的逻辑
# analyze_impact - 复用现有 analyze_impact
# check_types - 复用 consult_lsp(action="check_errors")
# inspect_symbol - 复用 consult_lsp(action="hover")
```

### Phase 4: 更新 Prompts
更新所有 prompt 模板，使用新的工具名：
```yaml
# worker.prompt.j2
- For finding code: `find_symbol`, `search_code`, `ask_codebase`
- For analyzing code: `analyze_impact`, `check_types`, `inspect_symbol`
```

---

## 六、收益评估

### 6.1 认知效率提升

| 指标 | 当前 | 重构后 | 提升 |
|------|------|--------|------|
| 代码探索工具数 | 4 (含2 Facade) | 6 (纯语义化) | 清晰化 |
| Agent 决策复杂度 | 高（需选技术和方式） | 低（只需选目标） | 显著降低 |
| 学习曲线 | 陡峭（需理解 LSP/Facade） | 平缓（只需语义） | 明显改善 |

### 6.2 维护成本降低

- **统一后端选择逻辑**：一处修改，全局生效
- **消除重复代码**：find_definition 和 consult_lsp 的逻辑合并
- **更清晰的测试边界**：每个工具职责单一

### 6.3 可扩展性增强

新增代码探索功能时，只需：
1. 添加新的语义化工具
2. 在 Engine 中添加新的后端选择策略

不需要像现在这样在多个 Facade/工具之间纠结。

---

## 七、总结

### 核心观点

1. **Facade 是反模式（在这个场景）**
   - `explore_codebase` 的 `action` 参数增加了不必要的复杂性
   - 应该直接暴露语义化工具

2. **技术细节不应该暴露**
   - `consult_lsp` 让 Agent 知道 LSP 的存在
   - Agent 应该说 "找定义"，不是 "用 LSP 找"

3. **应该自动选择最佳后端**
   - Graph/LSP/Grep 的选择应该是系统内部决策
   - Agent 不需要知道这个选择过程

### 最终建议

**删除：**
- ❌ `explore_codebase` (Facade 反模式)
- ❌ `consult_lsp` (技术细节暴露)
- ❌ `find_definition` (重命名为 `find_symbol`)
- ❌ `search_files` (重命名为 `search_code`)

**创建：**
- ✅ `find_symbol(name)` - 统一查找定义
- ✅ `search_code(pattern)` - 代码搜索
- ✅ `ask_codebase(question)` - 自然语言查询
- ✅ `analyze_impact(symbol)` - 影响分析
- ✅ `check_types(file?)` - 类型检查
- ✅ `inspect_symbol(symbol)` - 符号详情

**Worker 工具数：44 → 42（净减少 2 个，但语义清晰度大幅提升）**
