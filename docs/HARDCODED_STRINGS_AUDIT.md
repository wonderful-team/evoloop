# 硬编码字符串拼接审计报告

## 概述

在两轮模板优化后，通过全面扫描发现仍有 **60+** 处硬编码字符串拼接用于构建用户/LLM 可见的输出内容。这些应该迁移到模板系统。

---

## 🔴 高优先级 - 需要模板化

### 1. Document Reader - 文件内容格式化

**文件**: `backend/app/domain/tools/document_reader.py`

**问题代码**:
```python
# Line 163-166
if lang in ["python", "javascript", "typescript", "c", "cpp", "go", "rust"]:
    return f"# File: {filename}\n\n```{lang}\n{content}\n```"
return f"# File: {filename}\n\n{content}"

# Line 274
return f"# File: {filename}\n\n```{lang}\n{content}\n```"

# Line 338-349 (fallback)
text = []
text.append(f"# Document: {os.path.basename(path)}")
text.append(f"*Metadata: {reader.metadata}*")
text.append(f"*Pages: {start_idx+1} to {end_idx} (Total {total_pages})*")
text.append("---")
...
return "\n\n".join(text)

# Line 355
return f"# Document: {os.path.basename(path)}\n\n" + result.value

# Line 379-391 (fallback)
text = []
text.append(f"# Spreadsheet: {os.path.basename(path)}")
for sheet_name in sheet_names:
    text.append(f"Sheet: {sheet_name}")
    ...
return "\n".join(text)
```

**建议模板**:
- `project/file_content.prompt.j2` - 通用文件内容展示
- `project/document_content.prompt.j2` - 已存在，但 fallback 未使用
- `project/spreadsheet_content.prompt.j2` - Excel 内容展示

---

### 2. Todo 列表格式化

**文件**: `backend/app/domain/tools/manage_todo.py`

**问题代码**:
```python
# Line 137
return "\n".join([f"- [{t.status.value}] {t.title} (ID: {t.id}, Due: {t.due_date})" for t in todos])
```

**建议**: 使用 `project/project_management.prompt.j2` 或创建 `events/todo_list.prompt.j2`

---

### 3. 搜索结果格式化

**文件**: `backend/app/domain/tools/research.py`

**问题代码**:
```python
# Line 102, 107
return "\n---\n".join(results)
```

**文件**: `backend/app/domain/tools/memory_search.py`

**问题代码**:
```python
# Line 64
return f"No results found for '{query}' in the conversation history."

# Line 66-72
output = [f"Search results for '{query}':"]
for msg in results:
    role_label = "User" if msg.type == "human" else "Assistant"
    content_preview = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
    output.append(f"[{role_label}]: {content_preview}")
return "\n\n".join(output)
```

**建议模板**:
- `events/search_results.prompt.j2` - 通用搜索结果
- `events/chat_search_results.prompt.j2` - 聊天记录搜索

---

### 4. Wiki 页面格式化

**文件**: `backend/app/domain/tools/wiki_tools.py`

**问题代码**:
```python
# Line 114
return "📚 **Global Mode**: Wiki requires a project."

# Line 134
return f"Error: Parent page with slug '{parent_slug}' not found."

# Line 145
return f"Successfully {action} Wiki page: {title} ({slug})"
```

---

### 5. Knowledge Harvesting

**文件**: `backend/app/domain/tools/knowledge.py`

**问题代码**:
```python
# Line 56
return f"Successfully dispatched harvesting task for {len(concepts)} concepts: {', '.join(names)}"
```

---

### 6. Scheduler 消息

**文件**: `backend/app/domain/tools/scheduler.py`

**问题代码**:
```python
# Line 40
return f"Error: Skill '{skill_name}' not found. Please ensure the skill exists before scheduling."

# Line 50
return f"Successfully delegated periodic intent. Task ID: {task_id}. Trigger: {trigger}"

# Line 74
return f"Error: Task ID {task_id} not found."
```

---

## 🟡 中优先级 - 建议模板化

### 7. LSP 工具消息

**文件**: `backend/app/domain/tools/coding/lsp.py`

**问题代码**:
```python
# Line 245 - 298
return "No errors found."
return "Error: line and character arguments are required for find_definition."
return "No definitions found."
return "No hover information found."
return "Empty hover content."
```

### 8. Git 工具消息

**文件**: `backend/app/domain/tools/git.py`

**问题代码**:
```python
# Line 48
return "Knowledge harvesting initiated in background. I will continue learning from your changes."
```

### 9. Project Tools

**文件**: `backend/app/domain/tools/project_tools.py`

**问题代码**:
```python
# Line 39
return "Error: task_data is not valid JSON."
```

### 10. Workspace Tools

**文件**: `backend/app/domain/tools/workspace_tools.py`

**问题代码**:
```python
# Line 87
return "Please refer to your System Prompt under 'WORKSPACE CLIPBOARD' to see stashed items."
```

### 11. Facades 工具

**文件**: `backend/app/domain/tools/facades.py`

**问题代码**:
```python
# Lines 149-235
return "Error: 'argument' (message) required for commit."
return "Error: 'argument' (branch_name) required."
return "Error: key/value required."
...
```

---

## 🟢 低优先级 - 保持现状或简单处理

### 12. 纯错误消息（可保持现状）

这些主要是简单的错误提示，模板化收益较低：

```python
# checkpoint_tools.py
return "Error: 'name' and 'file_paths' are required."
return "No checkpoints found. Create one with create_checkpoint()."

# ranking.py
return "Error: No Android devices found for ranking."

# find_element.py
return "Error: Platform not specified and could not be resolved from context..."

# read_file.py
return "Error: Missing argument 'path'. usage: read_file(path='...')"

# preview_edit.py
return "Error: 'path' is required."
```

---

## 📊 统计汇总

| 类别 | 文件数 | 硬编码位置数 | 优先级 |
|------|--------|-------------|--------|
| Document Reader | 1 | 15 | 🔴 高 |
| Wiki Tools | 1 | 8 | 🔴 高 |
| Search Results | 2 | 6 | 🔴 高 |
| Todo/Memory | 2 | 4 | 🔴 高 |
| Scheduler | 1 | 5 | 🟡 中 |
| LSP Tools | 1 | 5 | 🟡 中 |
| Facades | 1 | 8 | 🟡 中 |
| 其他 | 5 | 10 | 🟢 低 |
| **总计** | **14** | **61** | - |

---

## 💡 建议的模板规划

### 需要新建的模板

```
backend/app/config/templates/
├── project/
│   ├── file_content.prompt.j2        # 代码文件展示
│   └── spreadsheet_content.prompt.j2 # Excel 内容展示
├── events/
│   ├── todo_list.prompt.j2           # Todo 列表
│   ├── search_results.prompt.j2      # 通用搜索结果
│   └── chat_search_results.prompt.j2 # 聊天记录搜索
└── errors/
    ├── simple_error.prompt.j2        # 简单错误消息
    └── validation_error.prompt.j2    # 参数验证错误
```

### 需要更新的现有模板

- `project/document_content.prompt.j2` - 增强 fallback 支持
- `report/response.prompt.j2` - 添加更多错误类型

---

## 🎯 实施建议

### 阶段一：高优先级（Document Reader）
- 创建 `file_content.prompt.j2`
- 更新 `document_content.prompt.j2` fallback
- 创建 `spreadsheet_content.prompt.j2`

### 阶段二：业务逻辑相关
- Todo 列表模板化
- Wiki 页面格式化模板化
- 搜索结果模板化

### 阶段三：错误消息统一
- 创建错误消息模板
- 统一所有错误消息格式

---

## 📝 代码示例

### 优化前
```python
# document_reader.py
return f"# File: {filename}\n\n```{lang}\n{content}\n```"
```

### 优化后
```python
# document_reader.py
return render_template("project/file_content.prompt.j2", 
                       filename=filename, lang=lang, content=content)
```

```jinja2
{# file_content.prompt.j2 #}
# File: {{ filename }}

```{%- if lang %} {{ lang }}{% endif %}
{{ content }}
```
```
