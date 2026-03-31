# Facade 工具深度分析：不是所有的 Facade 都有害

## 核心观点

> **Facade 本身不是罪，不合理的 Facade 才是问题。**

判断 Facade 是否有害的标准：**action 之间是否属于同一业务领域，Agent 是否能自然理解。**

---

## 一、Facade 模式的双面性

### 1.1 什么是 Facade 工具？

```python
# Facade 工具特征：通过 action 参数提供多种功能
@evoloop_tool
async def tool_name(
    action: Literal["action_a", "action_b", "action_c"],
    ...
)
```

### 1.2 好的 Facade vs 坏的 Facade

| 维度 | 好的 Facade | 坏的 Facade |
|------|-------------|-------------|
| **业务相关性** | action 属于同一领域 | action 业务无关 |
| **参数一致性** | 参数结构相似 | 参数差异很大 |
| **认知自然度** | Agent 容易理解 | 需要额外记忆 |
| **示例** | 文件操作（读/写/删） | 代码探索（搜索/分析/语义）|

---

## 二、当前系统 Facade 分析

### 2.1 已处理的坏 Facade ✅

#### explore_codebase（已删除）
```python
# 坏的 Facade - action 业务无关
explore_codebase(
    action: Literal[
        "search_symbol",      # 查找符号定义
        "search_text",        # 文本搜索
        "semantic_code_search", # 语义搜索
        "analyze_impact"      # 影响分析
    ]
)

# 问题：
# - "search_symbol" 和 "analyze_impact" 是完全不同的操作
# - 一个是查找，一个是分析
# - Agent 需要记忆 4 个 action 的映射
```

**重构后（好的拆分）：**
```python
find_symbol(name)          # 单一职责
search_code(pattern)       # 单一职责
ask_codebase(question)     # 单一职责
analyze_impact(symbol)     # 单一职责
```

#### consult_lsp（已删除）
```python
# 坏的 Facade - action 差异大，参数不同
consult_lsp(
    action: Literal["check_errors", "find_definition", "hover"],
    file_path: str,
    line: int | None,       # 只有 find_definition 和 hover 需要
    character: int | None    # 只有 find_definition 和 hover 需要
)

# 问题：
# - check_errors 不需要 line/character
# - find_definition 需要 line/character
# - 参数使用不一致， confusing
```

**重构后（好的拆分）：**
```python
check_types(file_path)     # 只需文件路径
find_symbol(name)          # 只需符号名
inspect_symbol(name)       # 只需符号名
```

---

### 2.2 可能合理的 Facade（待评估）

#### desktop_control / mobile_control / browser_control

```python
# 当前的 Facade 形式
desktop_control(
    action: Literal["click", "type", "scroll", "screenshot", "find_element"]
)
```

**评估：**

| action | 业务领域 | 参数 | 评估 |
|--------|----------|------|------|
| click | UI 操作 | x, y | ✅ 相关 |
| type | UI 操作 | text | ✅ 相关 |
| scroll | UI 操作 | direction | ✅ 相关 |
| screenshot | UI 操作 | 无 | ✅ 相关 |
| find_element | UI 查询 | selector | ⚠️ 查询 vs 操作？|

**结论：** 
- 前 4 个属于"UI 操作"领域 ✅
- `find_element` 是查询，不是操作，可能应该独立
- 整体可以保留，但考虑拆分 `find_element`

**Agent 认知：**
```
Agent: 我需要控制桌面
       → desktop_control(action="click")  # 自然
       → desktop_control(action="type")   # 自然
       
Agent: 我需要找元素
       → desktop_control(action="find_element")  # 稍微有点怪，但可以接受
       → find_ui_element(selector="...")         # 更自然？
```

---

#### manage_directory

```python
manage_directory(
    action: Literal["create", "delete", "rename", "list"],
    path: str
)
```

**评估：**

| action | 业务领域 | 评估 |
|--------|----------|------|
| create | 目录管理 | ✅ 相关 |
| delete | 目录管理 | ✅ 相关 |
| rename | 目录管理 | ✅ 相关 |
| list | 目录查询 | ⚠️ 已有 list_directory？|

**问题发现：**
- `list` action 与 `list_directory` 工具重复！

**建议：**
```python
# 方案 A：删除 manage_directory，拆分为原子工具
create_directory(path)
delete_directory(path)
rename_directory(path, new_name)
# list 使用已有的 list_directory

# 方案 B：保留 Facade，但删除 list action
manage_directory(action: Literal["create", "delete", "rename"])
```

---

### 2.3 确定合理的 Facade（应该保留）

#### execute_command（已经是好的 Facade）

```python
execute_command(command: str)
```

**注意：** 这不是 Facade！它看起来是单一职责。

但内部可能执行不同操作：
```bash
# 可以是任何命令
ls -la
git status
npm install
python script.py
```

**评估：** ✅ 应该保留
- 从 Agent 视角，它就是"执行命令"
- 不需要知道内部是 bash 还是其他

---

#### run_macro（可能是好的 Facade）

```python
run_macro(
    skill_name: str | None = None,
    skill_id: int | None = None,
    params: dict | None = None
)
```

**评估：** ⚠️ 需要查看实现
- 如果只是"执行已学习的宏"，是单一职责 ✅
- 如果内部有多种完全不同的执行模式，可能是坏的 Facade

---

## 三、判断 Facade 是否有害的 checklist

### 3.1 有害信号（应该拆分）

- [ ] **action 之间业务无关**
  - 例：`explore_codebase` 的 search_symbol vs analyze_impact
  
- [ ] **参数使用不一致**
  - 某些 action 需要参数 A，某些不需要
  - 例：`consult_lsp` 的 line/character 参数
  
- [ ] **返回值类型差异大**
  - 不同 action 返回完全不同的数据结构
  
- [ ] **Agent 难以选择 action**
  - 需要查阅文档才能决定用哪个 action
  
- [ ] **与其他工具功能重叠**
  - 例：`manage_directory(action="list")` vs `list_directory`

### 3.2 合理信号（可以保留）

- [x] **action 属于同一业务领域**
  - 例：`desktop_control` 的 click/type/scroll 都是 UI 操作
  
- [x] **参数结构一致**
  - 所有 action 使用相似的参数
  
- [x] **Agent 能自然理解**
  - 不需要额外解释就能选择合适的 action
  
- [x] **没有功能重叠**
  - 不与其他独立工具重复

---

## 四、剩余 Facade 处理建议

### 4.1 需要评估的 Facade

```python
# 1. desktop_control / mobile_control / browser_control
#    评估：可能合理，但检查 find_element 是否应该独立

# 2. manage_directory
#    评估：与 list_directory 重复，建议拆分或删除 list action

# 3. run_macro
#    评估：需要查看实现细节
```

### 4.2 处理决策树

```
发现 Facade 工具
       │
       ▼
Action 是否业务相关？
       │
       ├── 否 → 拆分为原子工具 ❌
       │
       └── 是 → 参数是否一致？
               │
               ├── 否 → 拆分为原子工具 ❌
               │
               └── 是 → 是否与其他工具重复？
                       │
                       ├── 是 → 删除重复功能，保留 Facade ⚠️
                       │
                       └── 否 → 保留 Facade ✅
```

---

## 五、总结

### 不是所有 Facade 都有害

**应该拆分的 Facade（有害的）：**
- ✅ `explore_codebase` - 已拆分
- ✅ `consult_lsp` - 已拆分

**可能合理的 Facade（保留的）：**
- ⚠️ `desktop/mobile/browser_control` - 评估中
- ⚠️ `manage_directory` - 可能与 list_directory 重复
- ✅ `execute_command` - 合理的单一职责

### 关键判断标准

1. **业务相关性** - action 是否属于同一领域？
2. **参数一致性** - 是否使用相似的参数？
3. **认知自然度** - Agent 是否能直觉选择？
4. **功能唯一性** - 是否与其他工具重复？

**Facade 不是原罪，不合理的设计才是问题。**
