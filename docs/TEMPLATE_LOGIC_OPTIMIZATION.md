# 模板引用逻辑优化评估报告

## 概述

通过对所有 `render_template` 调用点的分析，发现了几类可以优化的模式。这些优化将提升代码的可维护性、一致性和复用性。

---

## 🔴 高优先级优化

### 1. Controller 响应格式化重复代码

**问题描述**:
`mobile_controller.py`、`browser_controller.py`、`desktop_controller.py` 中大量重复代码：

```python
return render_template("report/response.prompt.j2", success=True/False, message=..., details=...)
```

**统计**:
- mobile_controller.py: ~40次
- browser_controller.py: ~50次
- desktop_controller.py: ~40次

**优化建议**:
创建一个 ControllerResponse 类或工具函数来统一处理：

```python
# 新建: app/utils/controller_response.py
class ControllerResponse:
    @staticmethod
    def success(message: str, details: str = None, note: str = None) -> str:
        return render_template("report/response.prompt.j2", 
                              success=True, message=message, details=details, note=note)
    
    @staticmethod
    def error(message: str, details: str = None, note: str = None) -> str:
        return render_template("report/response.prompt.j2", 
                              success=False, message=message, details=details, note=note)
    
    @staticmethod
    def not_found(item_name: str) -> str:
        return render_template("report/response.prompt.j2", 
                              success=False, message=f"{item_name} not found")
    
    @staticmethod
    def missing_param(param_name: str) -> str:
        return render_template("report/response.prompt.j2", 
                              success=False, message=f"'{param_name}' is required")
```

**收益**:
- 减少 ~130 行重复代码
- 统一错误消息格式
- 便于全局修改响应风格

---

### 2. WorkerBuilder._prepare_knowledge_blocks 列表渲染

**当前代码** (`worker_builder.py:68-90`):
```python
def _prepare_knowledge_blocks(self) -> list[str]:
    if not self.skills:
        return []
    blocks = []
    for i, skill in enumerate(self.skills):
        is_primary = (i == 0)
        block = render_template("fragments/knowledge_block.j2", ...)
        blocks.append(block)
    return blocks
```

**优化建议**:
创建一个通用的列表渲染模板片段：

```python
# 在 fragments/common/ 添加 list_renderer_wrapper.j2
{% macro render_list_with_index(items, template_name, index_key='index') %}
{% for item in items %}
{% set is_first = (loop.index0 == 0) %}
{% include template_name %}
{% endfor %}
{% endmacro %}
```

或者改为模板驱动：
```python
def _prepare_knowledge_blocks(self) -> str:
    return render_template(
        "fragments/knowledge_blocks_wrapper.j2",
        skills=self.skills,
        is_subtask=self.agent_config.get("is_subtask", False)
    )
```

---

### 3. ProjectSummarizer 数据格式化逻辑泄露

**当前代码** (`project/summarizer.py:111`):
```python
project_info = f"Name: {name}\nFiles: {', '.join(files[:20])}\nREADME: {readme_content[:1000]}\nArchitecture: {arch_summary[:2000]}"
prompt_text = render_template("project/project_summary.prompt.j2", project_info=project_info)
```

**问题**:
- 字符串拼接逻辑在 Python 中
- 截断逻辑硬编码 ([:20], [:1000], [:2000])

**优化建议**:
```python
# 改为传递结构化数据
prompt_text = render_template(
    "project/project_summary.prompt.j2",
    project_name=name,
    files=files,  # 模板中处理截断
    readme_content=readme_content,
    arch_summary=arch_summary
)
```

模板中使用：
```jinja2
Name: {{ project_name }}
Files: {{ files | truncate_list(20) | join(', ') }}
README: {{ readme_content | truncate(1000) }}
Architecture: {{ arch_summary | truncate(2000) }}
```

---

## 🟡 中优先级优化

### 4. MultimodalSynthesizer 条件渲染复杂

**当前代码** (`multimodal_synthesizer.py:555-568`):
```python
try:
    frames_narrative = render_template("vision/multimodal_frames.prompt.j2", frames=frame_vars)
    content.append({"type": "text", "text": frames_narrative})
except Exception as e:
    logger.error(f"Failed to render...")
    content.append({"type": "text", "text": "## Keyframes Analysis\n(Error...)"})
    # 插入 Base64 图片
```

**问题**:
- 异常处理和 fallback 逻辑在 Python 中
- 多模态内容构建逻辑分散

**优化建议**:
创建一个多模态内容构建器模板：
```jinja2
{# vision/multimodal_content.j2 #}
{% macro build_multimodal_content(frames, images) %}
{% for frame in frames %}
{{ frame.narrative }}
{% endfor %}
{% for img in images %}
[IMAGE: {{ img.description }}]
{% endfor %}
{% endmacro %}
```

---

### 5. Skill 执行结果格式化重复

**当前代码** (`tools/execution.py:175-201`):
```python
if result.get("success"):
    extracted = result.get("extracted_data", {})
    details = render_template("vision/perceptions.prompt.j2", ...) if extracted else None
    return render_template("report/response.prompt.j2", success=True, ...)
else:
    msg = result.get("message", "Unknown error")
    fallback = result.get("fallback_context")
    suggestions = result.get("suggestions", [])
    # 错误处理逻辑...
```

**优化建议**:
创建一个 SkillResultFormatter 类：
```python
class SkillResultFormatter:
    def format_success(self, skill_name: str, extracted_data: dict) -> str:
        details = render_template("vision/perceptions.prompt.j2", ...) if extracted_data else None
        return ControllerResponse.success(f"Skill '{skill_name}' completed", details=details)
    
    def format_error(self, skill_name: str, result: dict) -> str:
        # 统一错误格式化逻辑
```

---

### 6. Trace Parser 条件数据准备

**当前代码** (`trace_parser.py:354`):
```python
return render_template(
    "events/trace_narrative.prompt.j2",
    thread_id=sequence.thread_id,
    steps_count=len(sequence.steps),
    human_steps=...,  # 复杂条件计算
    agent_steps=...,
)
```

**优化建议**:
传递原始数据，让模板处理统计：
```python
return render_template(
    "events/trace_narrative.prompt.j2",
    sequence=sequence,  # 原始对象
    steps=sequence.steps  # 列表
)
```

模板中使用 Jinja2 过滤器：
```jinja2
Total steps: {{ steps | length }}
Human steps: {{ steps | selectattr("source", "equalto", "human") | list | length }}
Agent steps: {{ steps | selectattr("source", "equalto", "agent") | list | length }}
```

---

## 🟢 低优先级优化（代码整洁）

### 7. 重复导入清理

多处代码中 `from app.utils import render_template` 被重复导入：
- `tools/execution.py` 第 54、130、135、180、200 行附近

建议移到文件顶部统一导入。

### 8. 内联字符串拼接简化

```python
# 优化前
message=f"Tapped at ({tx}, {ty})" + (f" (resolved from '{element_name}')" if element_name else ".")

# 优化后 - 移到模板
render_template("events/tap_result.j2", x=tx, y=ty, element_name=element_name)
```

---

## 📊 优化收益汇总

| 优化项 | 代码减少量 | 维护性提升 | 优先级 |
|--------|-----------|-----------|--------|
| Controller 响应统一 | ~130行 | ⭐⭐⭐⭐⭐ | 🔴 高 |
| 列表渲染模板化 | ~20行 | ⭐⭐⭐⭐ | 🔴 高 |
| 数据格式化迁移 | ~30行 | ⭐⭐⭐⭐ | 🔴 高 |
| Skill 结果格式化 | ~40行 | ⭐⭐⭐ | 🟡 中 |
| 多模态内容构建 | ~25行 | ⭐⭐⭐ | 🟡 中 |
| Trace 统计模板化 | ~15行 | ⭐⭐⭐ | 🟡 中 |
| 导入清理 | N/A | ⭐⭐ | 🟢 低 |
| 字符串拼接简化 | ~20行 | ⭐⭐ | 🟢 低 |

**总计可减少约 280 行代码，显著提升可维护性**

---

## 🎯 实施建议

### 阶段一：高优先级（立即实施）
1. 创建 `ControllerResponse` 工具类
2. 重构三个 controller 文件
3. 更新 `_prepare_knowledge_blocks` 方法
4. 重构 `ProjectSummarizer`

### 阶段二：中优先级（后续迭代）
1. 创建 `SkillResultFormatter`
2. 优化多模态内容构建
3. 重构 Trace Parser 统计逻辑

### 阶段三：低优先级（代码清理）
1. 清理重复导入
2. 简化内联字符串拼接

---

## 💡 最佳实践建议

1. **数据准备 vs 表现逻辑**
   - Python: 负责数据获取、验证、转换
   - Jinja2: 负责格式化、过滤、条件显示

2. **模板粒度**
   - 简单响应：使用通用模板 (report/response)
   - 复杂结构：使用专用模板
   - 可复用片段：使用 fragments

3. **错误处理**
   - 模板渲染错误应统一捕获
   - 提供 fallback 内容
   - 记录日志但不中断流程

4. **命名规范**
   - 模板路径应反映功能：`{模块}/{功能}.prompt.j2`
   - 变量名应清晰描述内容
