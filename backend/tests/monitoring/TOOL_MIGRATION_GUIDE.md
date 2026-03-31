# 工具系统迁移指南

本文档记录 EvoLoop 工具系统的变更和映射关系，用于测试场景更新。

## 变更概览

| 旧工具名称 | 新工具名称 | 状态 | 说明 |
|-----------|-----------|------|------|
| `bash` | `execute_command` | ✅ 重命名 | 功能相同，名称更清晰 |
| `consult_lsp` | - | ⚠️ 移除 | 功能拆分为 6 个语义化工具 |
| `explore_codebase` | - | ⚠️ 移除 | 功能被新工具替代 |
| `grep_files` | `search_code` | ✅ 重命名 | 功能增强 |
| `list_files` | `list_directory` | ✅ 重命名 | 名称更准确 |
| `file_system` | `manage_directory` | ✅ 重命名 | 专注目录管理 |
| `preview_edit` | - | ⚠️ 移除 | 整合为 `edit_file(dry_run=True)` |
| `manage_memory` | - | ⚠️ 移除 | 拆分为具体工具 |
| `manage_todo` | - | ⚠️ 移除 | 拆分为 `create_todo` / `list_todos` |
| `request_approval` | `ask_confirm` | ✅ 重命名 | 语义更清晰 |
| `request_human_input` | `ask_human` | ✅ 重命名 | 更简洁 |

## 新工具详解

### 1. 代码探索工具（替代 consult_lsp）

```python
# 旧方式
consult_lsp(action="check_errors", file_path="src/main.py")
consult_lsp(action="find_definition", file_path="src/main.py", line=10, character=5)
consult_lsp(action="hover", file_path="src/main.py", line=10, character=5)

# 新方式
check_types(file_path="src/main.py")
find_symbol(name="UserService")
inspect_symbol(name="process_data")
search_code(pattern="def process_")
ask_codebase(question="How does authentication work?")
analyze_impact(symbol="UserService")
```

### 2. 文件操作工具

```python
# 读取文件
read_file(path="src/main.py")

# 编辑文件（自动类型检查）
edit_file(
    path="src/main.py",
    target="old_code",
    replacement="new_code",
    verify_types=True  # 默认开启
)

# 搜索代码（替代 grep_files）
search_code(pattern="axios", scope="*.ts")

# 目录操作
list_directory(path="src/")
manage_directory(path="temp/", action="create")
```

### 3. 知识管理工具（替代 manage_memory）

```python
# 旧方式
manage_memory(action="save_preference", ...)
manage_memory(action="search_history", ...)

# 新方式
save_preference(key="theme", value="dark")
search_history(query="authentication")
add_concept(name="依赖注入", description="...")
save_concepts(concepts=[...])
find_related_episodes(query="database")
```

### 4. 任务管理工具（替代 manage_todo）

```python
# 旧方式
manage_todo(action="create", ...)
manage_todo(action="list", ...)

# 新方式
create_todo(title="修复登录bug", priority="high")
list_todos(status="pending")
```

## 测试场景更新

### 新增测试类别

1. **code_exploration (23 个场景)**
   - 测试 `find_symbol`: 查找符号定义
   - 测试 `search_code`: 搜索代码模式
   - 测试 `ask_codebase`: 语义查询
   - 测试 `analyze_impact`: 影响分析
   - 测试 `check_types`: 类型检查
   - 测试 `inspect_symbol`: 查看符号详情

2. **edit_validation (4 个场景)**
   - 测试编辑后自动类型检查

3. **memory_knowledge (5 个场景)**
   - 测试新的知识管理工具

4. **task_management (4 个场景)**
   - 测试新的任务管理工具

5. **checkpoint (4 个场景)**
   - 测试检查点管理工具

### 场景示例映射

| 原场景描述 | 新场景描述 | 预期工具 |
|-----------|-----------|---------|
| "搜索项目中所有用到 axios 的地方" | 相同 | `search_code` |
| "检查这个文件的语法错误" | 相同 | `check_types` |
| "跳转到这个函数的定义" | "查找 UserService 的定义" | `find_symbol` |
| "保存我偏好使用 React" | 相同 | `save_preference` |
| "创建一个任务完成用户模块" | 相同 | `create_todo` |

## 运行测试

```bash
# 测试所有场景（212 个）
python test_with_scenarios.py

# 测试代码探索场景
python test_with_scenarios.py --category code_exploration

# 测试编辑验证场景
python test_with_scenarios.py --category edit_validation

# 限制每个类别测试数量
python test_with_scenarios.py --max 5

# 从指定位置开始
python test_with_scenarios.py --start 50
```

## 统计信息

```
总计场景: 212 条话术/场景
- 基础场景: 82 个
- 新工具场景: 40 个
- 多轮对话: 66 轮
- 边界/特殊: 24 个
```

## 注意事项

1. **verify_types 默认开启**: `edit_file` 现在默认进行类型检查
2. **dry_run 模式**: 原 `preview_edit` 功能已整合到 `edit_file(dry_run=True)`
3. **语义化工具**: 新工具名称更直观，Agent 更容易理解
4. **自动后端选择**: `find_symbol` 等工具自动选择 Graph/LSP/Grep 后端
