# 模板引用逻辑优化评估报告（第二轮）

## 概述

本次评估对全库 **120+** 处 `render_template` 调用进行了深入分析，识别出多个可优化模式。经过第一轮优化后，剩余模板引用点按照逻辑模式分类评估。

---

## 🔴 高优先级优化

### 1. Perceptions 模板格式化重复代码

**问题描述**：
多处代码手动构建 `items` 列表字符串后传递给 `vision/perceptions.prompt.j2`：

```python
# wiki_tools.py:56
return render_template("vision/perceptions.prompt.j2", type="wiki_pages", items=[f"{p.title} (slug: {p.slug})" for p in pages])

# browser_controller.py:396
lines = [f"[{i}] {lnk['text'][:60]} → {lnk['href']}" for i, lnk in enumerate(links_raw)]
return render_template("vision/perceptions.prompt.j2", type="links", items=lines[:100])

# mobile_controller.py:522
return render_template("vision/perceptions.prompt.j2", type="android_devices", items=[f"{d['serial']} ({d['status']}) {d['info']}" for d in devices])
```

**优化建议**：
创建 `PerceptionsFormatter` 工具类：

```python
class PerceptionsFormatter:
    @staticmethod
    def wiki_pages(pages: list) -> str:
        items = [f"{p.title} (slug: {p.slug})" for p in pages]
        return render_template("vision/perceptions.prompt.j2", type="wiki_pages", items=items)
    
    @staticmethod
    def links(links: list) -> str:
        items = [f"[{i}] {lnk['text'][:60]} → {lnk['href']}" for i, lnk in enumerate(links)]
        return render_template("vision/perceptions.prompt.j2", type="links", items=items[:100])
    
    @staticmethod
    def android_devices(devices: list) -> str:
        items = [f"{d['serial']} ({d['status']}) {d['info']}" for d in devices]
        return render_template("vision/perceptions.prompt.j2", type="android_devices", items=items)
```

**影响文件**：
- `wiki_tools.py` (2处)
- `browser_controller.py` (3处)
- `mobile_controller.py` (1处)
- `finish.py` (2处)
- `desktop_controller.py` (1处)

**减少代码量**：约 **40 行**

---

### 2. System Tools 模板数据准备重复

**问题描述**：
`events/system_tools.prompt.j2` 被多处使用，但数据准备模式重复：

```python
# checkpoint_tools.py:74-79, 126-136, 188-190
# scheduler.py:80-85, 120-130
# ranking.py:65
# agent.py:391, 574

cp_data.append({
    "id": t.id,
    "status": status,
    "name": t.intent_description[:50],
    "time": f"Next: {t.next_run_at}"
})
return render_template("events/system_tools.prompt.j2", checkpoints=cp_data)
```

**优化建议**：
创建 `SystemToolsFormatter`：

```python
class SystemToolsFormatter:
    @staticmethod
    def checkpoints(checkpoints: list) -> str:
        """Format checkpoint/autonomous task data."""
        cp_data = []
        for cp in checkpoints:
            status = getattr(cp, 'status', 'Unknown')
            cp_data.append({
                "id": getattr(cp, 'id', 0),
                "status": status,
                "name": getattr(cp, 'name', 'Unknown')[:50],
                "time": getattr(cp, 'time', '')
            })
        return render_template("events/system_tools.prompt.j2", checkpoints=cp_data)
    
    @staticmethod
    def signals(messages: list[str]) -> str:
        """Format signal messages."""
        signal_data = [{"message": m} for m in messages]
        return render_template("events/system_tools.prompt.j2", signals=signal_data)
```

**影响文件**：
- `checkpoint_tools.py` (4处)
- `scheduler.py` (2处)
- `ranking.py` (1处)
- `agent.py` (2处)

**减少代码量**：约 **50 行**

---

### 3. Project Management 模板重复格式化

**问题描述**：
`project/project_management.prompt.j2` 被多处使用，手动构建 `checklist`：

```python
# memory.py:80-87
# facades.py:242-248, 287-294
checklist = []
for ep in episodes:
    status = "FAILED" if ep.get("error") else "SUCCESS"
    checklist.append(f"[{status}] {ep.get('goal', 'Unknown')}")
return render_template("project/project_management.prompt.j2", checklist=checklist)
```

**优化建议**：
创建 `ProjectManagementFormatter`：

```python
class ProjectManagementFormatter:
    @staticmethod
    def checklist(items: list, status_key: str = None, name_key: str = "name") -> str:
        """Format items as a checklist."""
        checklist = []
        for item in items:
            if status_key:
                status = "FAILED" if item.get(status_key) else "SUCCESS"
                checklist.append(f"[{status}] {item.get(name_key, 'Unknown')}")
            else:
                checklist.append(str(item))
        return render_template("project/project_management.prompt.j2", checklist=checklist)
    
    @staticmethod
    def architecture_summary(info: dict) -> str:
        """Format architecture info."""
        checklist = [f"Summary: {info['summary']}"]
        for sub in info.get("sub_modules", []):
            checklist.append(f"Module {sub['name']}: {sub['summary'][:100]}...")
        for dep in info.get("dependencies", []):
            checklist.append(f"Depends on {dep['target']}")
        return render_template("project/project_management.prompt.j2", checklist=checklist)
```

**影响文件**：
- `memory.py` (1处)
- `facades.py` (2处)

**减少代码量**：约 **25 行**

---

### 4. LearningPromptBuilder 重复错误处理模式

**问题描述**：
`LearningPromptBuilder` 中每个方法都有相同的错误处理模式：

```python
def build_synthesis_prompt(self, vars: Dict[str, Any]) -> str:
    try:
        return render_template("learning/skill_synthesis.prompt.j2", **vars)
    except Exception as e:
        logger.error(f"Error rendering Synthesis template: {e}")
        return f"Error loading skill synthesis template: {e}"

# 重复 8 次...
```

**优化建议**：
提取通用渲染方法：

```python
class LearningPromptBuilder:
    def _render_with_fallback(self, template_name: str, vars: dict, fallback_msg: str) -> str:
        """Generic template rendering with error handling."""
        try:
            return render_template(template_name, **vars)
        except Exception as e:
            logger.error(f"Error rendering {template_name}: {e}")
            return f"{fallback_msg}: {e}"
    
    def build_synthesis_prompt(self, vars: Dict[str, Any]) -> str:
        return self._render_with_fallback(
            "learning/skill_synthesis.prompt.j2",
            vars,
            "Error loading skill synthesis template"
        )
    # ... 其他方法简化
```

**影响文件**：
- `learning/prompts/builder.py`

**减少代码量**：约 **35 行**

---

## 🟡 中优先级优化

### 5. Error Response 模板降级不一致

**问题描述**：
多处 try/except 块在模板渲染失败时使用字符串拼接降级：

```python
# document_reader.py:335-349
try:
    return render_template("project/document_content.prompt.j2", ...)
except Exception as e:
    logger.error(f"Failed to render Document template for PDF: {e}")
    # Fallback to string concatenation
    text = []
    text.append(f"# Document: {os.path.basename(path)}")
    ...
    return "\n\n".join(text)
```

**优化建议**：
1. 创建标准降级模板或工具函数
2. 或者将 fallback 逻辑移到模板层

```python
def render_with_fallback(template_name: str, fallback_template: str, **kwargs) -> str:
    try:
        return render_template(template_name, **kwargs)
    except Exception as e:
        logger.error(f"Primary template failed: {e}")
        try:
            return render_template(fallback_template, error=str(e), **kwargs)
        except:
            return str(kwargs)  # Ultimate fallback
```

**影响文件**：
- `document_reader.py` (2处)
- `multimodal_synthesizer.py` (1处)
- `desktop_controller.py` (1处)

---

### 6. FinishPromptBuilder 错误处理

**问题描述**：
`FinishPromptBuilder.build()` 在模板失败时返回字符串而非使用模板：

```python
try:
    return render_template("agents/finish.prompt.j2", **template_vars)
except Exception as e:
    logger.error(f"Error rendering Reviewer template: {e}")
    return f"Session Reviewer template error: {e}"  # 非模板化响应
```

**优化建议**：
使用统一的错误响应模板：

```python
except Exception as e:
    logger.error(f"Error rendering Reviewer template: {e}")
    return ControllerResponse.error(
        "Session Reviewer template error",
        details=str(e)
    )
```

---

### 7. SupervisorBuilder 错误处理重复

**问题描述**：
`supervisor_builder.py:129` 的错误处理可以改用 `ControllerResponse`：

```python
except Exception as e:
    logger.error(f"Failed to render Supervisor template: {e}")
    return render_template("report/response.prompt.j2", success=False, message="Supervisor Template Error", details=str(e), note=f"PID: {self.project_id}")
```

**优化建议**：
```python
except Exception as e:
    logger.error(f"Failed to render Supervisor template: {e}")
    return ControllerResponse.error(
        "Supervisor Template Error",
        details=str(e),
        note=f"PID: {self.project_id}"
    )
```

---

## 🟢 低优先级优化（代码整洁）

### 8. Inline Import 清理

**多处代码使用 inline import**：

```python
# wiki_tools.py:52, 56, 82, 85, 164
from app.utils import render_template

# facades.py:242, 286
from app.utils import render_template

# checkpoint_tools.py: 多处
```

**优化**：统一移到文件顶部导入

**影响文件**：约 **8 个文件**

---

### 9. Vision Pipeline Manager 内联数据处理

**文件**：`vision/pipeline/manager.py:157-165`

```python
element_data = [{"line": el.to_prompt_line()} for el in display_elements]
return render_template("vision/elements_list.prompt.j2", elements=element_data, ...)
```

**优化建议**：
传递原始元素，让模板调用 `to_prompt_line()`：

```python
# Python 端
return render_template("vision/elements_list.prompt.j2", elements=display_elements, ...)

# 模板端
{% for el in elements %}
{{ el.to_prompt_line() }}
{% endfor %}
```

---

## 📊 优化收益汇总

| 优化项 | 代码减少量 | 维护性提升 | 优先级 |
|--------|-----------|-----------|--------|
| PerceptionsFormatter | ~40行 | ⭐⭐⭐⭐ | 🔴 高 |
| SystemToolsFormatter | ~50行 | ⭐⭐⭐⭐ | 🔴 高 |
| ProjectManagementFormatter | ~25行 | ⭐⭐⭐ | 🔴 高 |
| LearningPromptBuilder 重构 | ~35行 | ⭐⭐⭐⭐ | 🔴 高 |
| Error Response 降级统一 | ~20行 | ⭐⭐⭐ | 🟡 中 |
| FinishPromptBuilder 错误处理 | ~5行 | ⭐⭐⭐ | 🟡 中 |
| SupervisorBuilder 错误处理 | ~3行 | ⭐⭐ | 🟡 中 |
| Inline Import 清理 | N/A | ⭐⭐ | 🟢 低 |
| Vision Pipeline 优化 | ~5行 | ⭐⭐ | 🟢 低 |

**总计可减少约 183 行代码**

---

## 🎯 实施建议

### 阶段一：高优先级（立即实施）
1. 创建 `PerceptionsFormatter` 工具类
2. 创建 `SystemToolsFormatter` 工具类
3. 创建 `ProjectManagementFormatter` 工具类
4. 重构 `LearningPromptBuilder`

### 阶段二：中优先级（后续迭代）
1. 统一 Error Response 降级处理
2. 更新 `FinishPromptBuilder` 和 `SupervisorBuilder`

### 阶段三：低优先级（代码清理）
1. 清理 inline imports
2. 优化 Vision Pipeline

---

## 💡 最佳实践建议

1. **Formatter 类模式**：对于同一模板的多次使用，创建专门的 Formatter 类
2. **数据准备 vs 表现逻辑**：保持 Python 端数据准备，模板端负责格式化
3. **错误处理一致性**：所有模板渲染错误应使用统一的降级策略
4. **Import 规范**：避免 inline import，统一在文件顶部导入
