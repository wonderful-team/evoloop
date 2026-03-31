# 宏脚本 YAML 迁移改进计划

## 1. 项目概述

### 1.1 目标
将宏脚本在人机交互和 LLM 交互层面从 JSON 迁移到 YAML，提升可读性和 LLM 生成准确率，同时保持后端执行引擎继续高效处理 JSON。

### 1.2 核心原则
- **边界转换**：仅在系统边界（API 层）进行 YAML ↔ JSON 转换
- **向后兼容**：保持 JSON 支持，逐步迁移
- **存储不变**：数据库继续存储 JSONB 格式
- **引擎透明**：执行引擎内部保持 Python dict，与格式无关

---

## 2. 实施阶段

### 阶段 1：基础设施准备（Day 1-2）

#### 2.1.1 添加依赖

**Backend (`pyproject.toml`)**
```toml
dependencies = [
    # ... existing deps ...
    "PyYAML>=6.0.1",           # YAML 解析/生成
    "yamllint>=1.35.1",        # YAML 语法校验（可选）
]
```

**Frontend (`package.json`)**
```json
{
  "dependencies": {
    "js-yaml": "^4.1.0",
    "@types/js-yaml": "^4.0.9"
  }
}
```

#### 2.1.2 创建 YAML 工具模块

**新增文件：`backend/app/utils/yaml.py`**
```python
"""
YAML Utilities for Macro Script Processing

Provides safe YAML parsing and conversion to/from JSON.
"""

import yaml
from typing import Any
from yaml.scanner import ScannerError
from yaml.parser import ParserError


class YAMLError(Exception):
    """Custom YAML error with context."""
    pass


def safe_yaml_loads(content: str) -> Any:
    """
    Safely parse YAML content.
    
    Args:
        content: YAML string
        
    Returns:
        Parsed Python object
        
    Raises:
        YAMLError: If parsing fails
    """
    try:
        return yaml.safe_load(content)
    except (ScannerError, ParserError) as e:
        raise YAMLError(f"YAML parse error at line {e.problem_mark.line}: {e.problem}")


def safe_yaml_dumps(obj: Any, indent: int = 2) -> str:
    """
    Safely serialize object to YAML.
    
    Args:
        obj: Object to serialize
        indent: Indentation level
        
    Returns:
        YAML string
    """
    return yaml.safe_dump(
        obj,
        indent=indent,
        allow_unicode=True,
        sort_keys=False,  # Preserve key order for readability
        default_flow_style=False
    )


def macro_to_yaml(macro_steps: list[dict]) -> str:
    """
    Convert macro steps to human-friendly YAML format.
    
    Args:
        macro_steps: List of macro step dicts
        
    Returns:
        Formatted YAML string
    """
    # Add metadata header
    data = {
        "version": "1.0",
        "metadata": {
            "format": "evoloop-macro",
            "step_count": len(macro_steps)
        },
        "steps": macro_steps
    }
    return safe_yaml_dumps(data)


def macro_from_yaml(yaml_content: str) -> list[dict]:
    """
    Parse YAML macro and extract steps.
    
    Args:
        yaml_content: YAML string
        
    Returns:
        List of macro step dicts
        
    Raises:
        YAMLError: If format is invalid
    """
    data = safe_yaml_loads(yaml_content)
    
    if not isinstance(data, dict):
        raise YAMLError("YAML root must be a mapping")
    
    # Support both wrapped and unwrapped formats
    steps = data.get("steps", data.get("macro_script", data))
    
    if not isinstance(steps, list):
        raise YAMLError("Macro steps must be a list")
    
    return steps


def validate_macro_yaml(yaml_content: str) -> tuple[bool, list[str]]:
    """
    Validate YAML macro format without full parsing.
    
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    try:
        data = safe_yaml_loads(yaml_content)
    except YAMLError as e:
        return False, [str(e)]
    
    if not isinstance(data, (dict, list)):
        return False, ["YAML root must be a mapping or list"]
    
    steps = data.get("steps", data) if isinstance(data, dict) else data
    
    if not isinstance(steps, list):
        return False, ["'steps' must be a list"]
    
    # Validate each step has required fields
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"Step {i+1}: must be a mapping")
            continue
            
        if "type" not in step:
            errors.append(f"Step {i+1}: missing required field 'type'")
    
    return len(errors) == 0, errors
```

#### 2.1.3 更新 Schema 模块

**修改：`backend/app/core/execution/macro/schema.py`**

添加类方法：
```python
from app.utils.yaml import macro_from_yaml, macro_to_yaml, YAMLError

class MacroScript(BaseModel):
    # ... existing fields ...
    
    @classmethod
    def from_yaml(cls, yaml_content: str) -> "MacroScript":
        """Parse macro from YAML string."""
        steps = macro_from_yaml(yaml_content)
        return cls(steps=steps)
    
    def to_yaml(self) -> str:
        """Export macro to YAML string."""
        return macro_to_yaml([step.model_dump() for step in self.steps])
    
    @classmethod
    def parse(cls, content: str, format: str = "auto") -> "MacroScript":
        """
        Parse macro from string (auto-detect or specified format).
        
        Args:
            content: String content (JSON or YAML)
            format: "auto", "json", or "yaml"
        """
        if format == "auto":
            # Auto-detect based on first non-whitespace char
            stripped = content.strip()
            if stripped.startswith(("{", "[")):
                format = "json"
            else:
                format = "yaml"
        
        if format == "yaml":
            return cls.from_yaml(content)
        else:
            # Existing JSON parsing
            return cls.parse_raw(content) if stripped.startswith("{") else cls(steps=json.loads(content))
```

---

### 阶段 2：API 层增强（Day 2-3）

#### 2.2.1 创建 YAML 依赖注入

**新增：`backend/app/api/dependencies/yaml.py`**
```python
"""
YAML Content-Type support for FastAPI
"""

from fastapi import Request, HTTPException
from typing import Any
from app.utils.yaml import macro_from_yaml, YAMLError


async def parse_macro_body(request: Request) -> list[dict]:
    """
    Parse request body as macro steps, supporting both JSON and YAML.
    
    Content-Type headers:
    - application/json -> JSON parsing
    - application/yaml or text/yaml -> YAML parsing
    - application/x-yaml -> YAML parsing
    """
    content_type = request.headers.get("content-type", "application/json").lower()
    body = await request.body()
    content = body.decode("utf-8")
    
    try:
        if "yaml" in content_type or content_type == "text/yaml":
            return macro_from_yaml(content)
        else:
            import json
            data = json.loads(content)
            # Handle both {steps: [...]} and [...] formats
            return data.get("steps", data) if isinstance(data, dict) else data
    except (YAMLError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid format: {str(e)}")
```

#### 2.2.2 更新 Learning API

**修改：`backend/app/api/routes/learning.py`**

添加新的端点：
```python
from fastapi import Depends
from app.api.dependencies.yaml import parse_macro_body


class CreateSkillFromYamlRequest(BaseModel):
    name: str
    description: str | None = None
    namespace: str | None = None
    yaml_content: str


@router.post("/skills/from-yaml")
async def create_skill_from_yaml(
    body: CreateSkillFromYamlRequest,
    bg_tasks: BackgroundTasks
):
    """Create skill from YAML macro definition."""
    try:
        macro_script = macro_from_yaml(body.yaml_content)
        
        async with session_scope() as db:
            skill = LearnedSkill(
                name=body.name,
                description=body.description or "",
                namespace=body.namespace,
                macro_script=macro_script,
                execution_mode="deterministic",
                is_active=False,
                status="pending_review"
            )
            db.add(skill)
            await db.flush()
            return {"success": True, "skill_id": skill.id}
            
    except YAMLError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/skills/{skill_id}/yaml")
async def update_skill_yaml(
    skill_id: int,
    yaml_content: str = Body(..., media_type="text/yaml"),
):
    """Update skill macro from YAML."""
    try:
        macro_script = macro_from_yaml(yaml_content)
        
        async with session_scope() as db:
            skill = await db.get(LearnedSkill, skill_id)
            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")
            
            skill.macro_script = macro_script
            await db.flush()
            
        return {"success": True, "message": "Skill updated from YAML"}
        
    except YAMLError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/skills/{skill_id}/yaml")
async def get_skill_yaml(skill_id: int):
    """Get skill macro as YAML."""
    async with session_scope() as db:
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        
        if not skill.macro_script:
            return "# No macro script defined\n"
        
        yaml_content = macro_to_yaml(skill.macro_script)
        return Response(
            content=yaml_content,
            media_type="text/yaml"
        )
```

---

### 阶段 3：Prompt 更新（Day 3-5）

#### 2.3.1 更新智能回放宏 Prompt

**修改：`backend/app/config/templates/learning/smart_replay_macro.prompt.j2`**

```jinja2
{# 第 80-92 行替换为 YAML 格式 #}

Respond with ONLY a YAML array:

```yaml
steps:
  - type: action
    event_type: navigate
    source: dom
    payload:
      url: "https://example.com"
    description: Navigate to target
  
  - type: action
    event_type: click
    source: dom
    target_selector: ".submit-btn"
    payload:
      x: 0.5
      y: 0.3
    description: Click submit button
```

IMPORTANT YAML RULES:
1. Use 2-space indentation
2. Do NOT use tabs
3. Strings with special chars must be quoted
4. Multi-line strings use | or >
```

#### 2.3.2 更新验证 Prompt

**修改：`backend/app/config/templates/macro/decide_next_step.prompt.j2`**

```jinja2
## Current Macro Step
```yaml
{{ step_yaml }}  {# 改为 YAML 格式 #}
```
```

#### 2.3.3 创建 Prompt 响应解析器

**新增：`backend/app/core/execution/macro/parsers.py`**
```python
"""
LLM Response Parsers for different formats
"""

import re
import json
from typing import Any
from app.utils.yaml import safe_yaml_loads, YAMLError


def extract_yaml_from_response(response: str) -> str | None:
    """Extract YAML content from LLM response."""
    # Try fenced code block
    patterns = [
        r'```yaml\n(.*?)\n```',
        r'```yml\n(.*?)\n```',
        r'```\n(.*?)\n```',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
    
    # Try to find YAML-like structure (starts with "steps:" or "- ")
    lines = response.split('\n')
    yaml_lines = []
    in_yaml = False
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(('steps:', '- ', 'type:')):
            in_yaml = True
        if in_yaml:
            yaml_lines.append(line)
    
    return '\n'.join(yaml_lines) if yaml_lines else None


def parse_macro_response(response: str) -> list[dict]:
    """
    Parse LLM response containing macro steps.
    
    Supports:
    - YAML format (preferred)
    - JSON format (legacy)
    """
    # Try YAML first
    yaml_content = extract_yaml_from_response(response)
    if yaml_content:
        try:
            data = safe_yaml_loads(yaml_content)
            steps = data.get("steps", data) if isinstance(data, dict) else data
            if isinstance(steps, list):
                return steps
        except YAMLError:
            pass
    
    # Fallback to JSON
    try:
        # Try to extract JSON
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    
    raise ValueError("Could not parse response as YAML or JSON macro")
```

---

### 阶段 4：前端更新（Day 5-8）

#### 2.4.1 创建 YAML 编辑器组件

**新增：`frontend/packages/desktop/src/components/Learning/SmartReplay/MacroYamlEditor.tsx`**
```typescript
/**
 * MacroYamlEditor - YAML editor for macro scripts
 * 
 * Features:
 * - YAML syntax highlighting
 * - Real-time validation
 * - Auto-formatting
 * - Error annotations
 */

import { useState, useCallback, useEffect } from "react"
import { load, dump } from "js-yaml"
import { AlertCircle, Check, FileJson, FileCode } from "lucide-react"
import { Button } from "@evoloop/shared/components/ui/button"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { Alert, AlertDescription } from "@evoloop/shared/components/ui/alert"
import { useTranslation } from "react-i18next"

interface MacroYamlEditorProps {
    steps: MacroStep[]
    onChange: (steps: MacroStep[]) => void
    children?: React.ReactNode
}

const DEFAULT_YAML_TEMPLATE = `version: "1.0"
metadata:
  format: evoloop-macro
  step_count: 0

steps:
  # Add your steps here
  - type: action
    event_type: navigate
    source: dom
    description: Navigate to target page
    payload:
      url: "https://example.com"
`

export function MacroYamlEditor({ steps, onChange, children }: MacroYamlEditorProps) {
    const { t } = useTranslation()
    const [yamlValue, setYamlValue] = useState("")
    const [error, setError] = useState<string | null>(null)
    const [isValid, setIsValid] = useState(true)

    // Convert steps to YAML on mount
    useEffect(() => {
        try {
            const yaml = dump({
                version: "1.0",
                metadata: {
                    format: "evoloop-macro",
                    step_count: steps.length
                },
                steps
            }, {
                indent: 2,
                lineWidth: -1,
                noRefs: true,
                sortKeys: false
            })
            setYamlValue(yaml)
            setError(null)
            setIsValid(true)
        } catch (e) {
            setError(t("macroEditor.yamlConvertError"))
            setIsValid(false)
        }
    }, [steps])

    const validateYaml = useCallback((content: string): { valid: boolean; error?: string } => {
        try {
            const parsed = load(content)
            
            if (!parsed || typeof parsed !== "object") {
                return { valid: false, error: t("macroEditor.yamlRootObject") }
            }
            
            const data = parsed as any
            const steps = data.steps || data
            
            if (!Array.isArray(steps)) {
                return { valid: false, error: t("macroEditor.yamlStepsArray") }
            }
            
            // Validate each step
            for (let i = 0; i < steps.length; i++) {
                const step = steps[i]
                if (!step.type) {
                    return { valid: false, error: t("macroEditor.yamlStepTypeMissing", { index: i + 1 }) }
                }
            }
            
            return { valid: true }
        } catch (e: any) {
            return { valid: false, error: e.message }
        }
    }, [t])

    const handleChange = useCallback((value: string) => {
        setYamlValue(value)
        const result = validateYaml(value)
        setIsValid(result.valid)
        setError(result.error || null)
    }, [validateYaml])

    const handleApply = useCallback(() => {
        const result = validateYaml(yamlValue)
        if (!result.valid) {
            setError(result.error || null)
            return
        }

        try {
            const parsed = load(yamlValue) as any
            const steps = parsed.steps || parsed
            onChange(steps as MacroStep[])
        } catch (e: any) {
            setError(e.message)
        }
    }, [yamlValue, onChange, validateYaml])

    const handleFormat = useCallback(() => {
        try {
            const parsed = load(yamlValue)
            const formatted = dump(parsed, {
                indent: 2,
                lineWidth: -1,
                noRefs: true,
                sortKeys: false
            })
            setYamlValue(formatted)
            setError(null)
            setIsValid(true)
        } catch (e: any) {
            setError(e.message)
        }
    }, [yamlValue])

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <FileCode className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">{t("macroEditor.yamlMode")}</span>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleFormat}
                        disabled={!isValid}
                    >
                        {t("macroEditor.format")}
                    </Button>
                    <Button
                        size="sm"
                        onClick={handleApply}
                        disabled={!isValid}
                        className="gap-2"
                    >
                        <Check className="h-4 w-4" />
                        {t("common.apply")}
                    </Button>
                </div>
            </div>

            {error && (
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            )}

            <Textarea
                value={yamlValue}
                onChange={(e) => handleChange(e.target.value)}
                className="font-mono text-xs min-h-[500px] leading-relaxed"
                spellCheck={false}
                placeholder={DEFAULT_YAML_TEMPLATE}
            />

            {children}
        </div>
    )
}
```

#### 2.4.2 更新 SkillEditorPage

**修改：`frontend/packages/desktop/src/components/Learning/SkillEditorPage.tsx`**

```typescript
// 添加导入
import { MacroYamlEditor } from "./SmartReplay/MacroYamlEditor"

// 添加状态
const [editorMode, setEditorMode] = useState<"visual" | "yaml" | "json">("visual")

// 在 deterministic 模式下添加编辑器切换
{executionMode === "deterministic" && (
    <div className="flex-1 min-h-0 border rounded-xl bg-background shadow-sm overflow-hidden">
        <div className="flex items-center justify-between p-2 border-b bg-muted/50">
            <div className="flex items-center gap-2">
                <Button
                    variant={editorMode === "visual" ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setEditorMode("visual")}
                >
                    {t("macroEditor.visual")}
                </Button>
                <Button
                    variant={editorMode === "yaml" ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setEditorMode("yaml")}
                >
                    YAML
                </Button>
                <Button
                    variant={editorMode === "json" ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setEditorMode("json")}
                >
                    JSON
                </Button>
            </div>
        </div>
        
        <div className="h-[calc(100%-44px)] overflow-auto">
            {editorMode === "visual" && (
                <MacroEditor
                    steps={safeParseMacro(macroScript)}
                    onChange={(steps) => setMacroScript(JSON.stringify(steps, null, 2))}
                />
            )}
            {editorMode === "yaml" && (
                <MacroYamlEditor
                    steps={safeParseMacro(macroScript)}
                    onChange={(steps) => setMacroScript(JSON.stringify(steps, null, 2))}
                />
            )}
            {editorMode === "json" && (
                <MacroJsonEditor
                    steps={safeParseMacro(macroScript)}
                    onChange={(steps) => setMacroScript(JSON.stringify(steps, null, 2))}
                >
                    <Button variant="outline" size="sm">{t("learning.editJson")}</Button>
                </MacroJsonEditor>
            )}
        </div>
    </div>
)}
```

---

### 阶段 5：测试与验证（Day 8-10）

#### 2.5.1 单元测试

**新增：`backend/tests/test_yaml_utils.py`**
```python
"""Tests for YAML utilities."""

import pytest
from app.utils.yaml import (
    safe_yaml_loads,
    safe_yaml_dumps,
    macro_from_yaml,
    macro_to_yaml,
    validate_macro_yaml,
    YAMLError
)


class TestYAMLParsing:
    """Test YAML parsing functions."""
    
    def test_parse_simple_macro(self):
        yaml_content = """
steps:
  - type: action
    event_type: click
    source: dom
    target_selector: ".btn"
"""
        result = macro_from_yaml(yaml_content)
        assert len(result) == 1
        assert result[0]["type"] == "action"
        assert result[0]["event_type"] == "click"
    
    def test_parse_nested_structure(self):
        yaml_content = """
steps:
  - type: if
    condition:
      type: element_exists
      target_selector: ".modal"
    then_steps:
      - type: action
        event_type: click
        target_selector: ".close"
"""
        result = macro_from_yaml(yaml_content)
        assert result[0]["type"] == "if"
        assert len(result[0]["then_steps"]) == 1
    
    def test_invalid_yaml_raises_error(self):
        with pytest.raises(YAMLError):
            safe_yaml_loads("invalid: yaml: [")
    
    def test_missing_steps_field(self):
        with pytest.raises(YAMLError):
            macro_from_yaml("name: test")  # No steps field


class TestYAMLValidation:
    """Test YAML validation."""
    
    def test_valid_macro(self):
        yaml_content = """
steps:
  - type: action
    event_type: navigate
"""
        valid, errors = validate_macro_yaml(yaml_content)
        assert valid is True
        assert len(errors) == 0
    
    def test_missing_type_field(self):
        yaml_content = """
steps:
  - event_type: navigate
"""
        valid, errors = validate_macro_yaml(yaml_content)
        assert valid is False
        assert any("type" in e for e in errors)


class TestYAMLGeneration:
    """Test YAML generation from macro."""
    
    def test_generate_yaml(self):
        steps = [
            {"type": "action", "event_type": "navigate", "source": "dom"},
            {"type": "click", "target_selector": ".btn"}
        ]
        yaml_str = macro_to_yaml(steps)
        assert "version: '1.0'" in yaml_str
        assert "steps:" in yaml_str
        # Verify round-trip
        parsed = macro_from_yaml(yaml_str)
        assert len(parsed) == 2
```

#### 2.5.2 集成测试

**新增：`backend/tests/api/test_learning_yaml.py`**
```python
"""Integration tests for YAML endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestYamlEndpoints:
    """Test YAML API endpoints."""
    
    def test_create_skill_from_yaml(self, client: TestClient):
        yaml_content = """
steps:
  - type: action
    event_type: navigate
    source: dom
    payload:
      url: "https://example.com"
"""
        response = client.post("/api/v1/learning/skills/from-yaml", json={
            "name": "Test YAML Skill",
            "yaml_content": yaml_content
        })
        assert response.status_code == 200
        assert response.json()["success"] is True
    
    def test_invalid_yaml_returns_400(self, client: TestClient):
        response = client.post("/api/v1/learning/skills/from-yaml", json={
            "name": "Test",
            "yaml_content": "invalid: yaml: ["
        })
        assert response.status_code == 400
    
    def test_get_skill_as_yaml(self, client: TestClient, sample_skill):
        response = client.get(f"/api/v1/learning/skills/{sample_skill.id}/yaml")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/yaml"
        assert "steps:" in response.text
```

#### 2.5.3 E2E 测试清单

1. **LLM 合成流程**
   - [ ] 智能回放合成输出 YAML 格式
   - [ ] YAML 被正确解析并存储
   - [ ] 存储后 YAML 能正确渲染到前端

2. **前端编辑流程**
   - [ ] 可视化编辑器修改同步到 YAML
   - [ ] YAML 编辑器实时验证语法
   - [ ] 格式错误有清晰的错误提示
   - [ ] 三种编辑器模式切换不丢失数据

3. **后端执行流程**
   - [ ] YAML 宏能正确执行
   - [ ] JSON 宏保持兼容
   - [ ] 混合使用无问题

---

### 阶段 6：部署与文档（Day 10-12）

#### 2.6.1 部署检查清单

- [ ] 安装 PyYAML 依赖
- [ ] 安装 js-yaml 依赖
- [ ] 运行数据库迁移（如有 schema 变更）
- [ ] 部署后端服务
- [ ] 部署前端应用
- [ ] 验证所有新端点

#### 2.6.2 用户文档

**新增：`docs/guides/macro-yaml-format.md`**

```markdown
# Macro YAML Format Guide

## Overview
EvoLoop now supports YAML format for macro scripts, making them more human-readable and easier to edit.

## Basic Structure

```yaml
version: "1.0"
metadata:
  format: evoloop-macro
  step_count: 3

steps:
  - type: action
    event_type: navigate
    source: dom
    description: Navigate to example.com
    payload:
      url: "https://example.com"

  - type: action
    event_type: click
    source: dom
    target_selector: ".login-button"
    description: Click login button

  - type: extract
    extract_type: get_text
    source: dom
    target_selector: ".welcome-message"
    key: welcome_text
    description: Extract welcome message
```

## Step Types

### Action Step
```yaml
- type: action
  event_type: click|navigate|input|scroll|...
  source: dom|mobile|desktop
  target_selector: "optional css selector"
  payload:
    # action-specific parameters
```

### Conditional Step (if)
```yaml
- type: if
  description: Handle cookie banner
  condition:
    type: element_exists
    target_selector: ".cookie-banner"
  then_steps:
    - type: action
      event_type: click
      target_selector: ".accept-cookies"
  else_steps: []  # optional
```

### Loop Step
```yaml
- type: loop
  description: Process all items
  max_iterations: 10
  condition:
    type: element_exists
    target_selector: ".next-button"
  steps:
    - type: action
      event_type: click
      target_selector: ".item"
```

## YAML Syntax Rules

1. **Indentation**: Use 2 spaces, never tabs
2. **Quotes**: Quote strings containing special characters
3. **Multi-line**: Use `|` for literal blocks, `>` for folded
4. **Comments**: Use `#` for comments

## Migration from JSON

Use the conversion utility:
```bash
# API endpoint
POST /api/v1/learning/skills/{id}/convert-to-yaml
```

Or manually convert using online tools.
```

---

## 3. 风险管理

### 3.1 风险识别

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| LLM YAML 生成错误 | 中 | 高 | 提供 strict schema + 验证 |
| 前端包体积增加 | 低 | 低 | js-yaml 仅 ~10KB gzipped |
| 向后兼容破坏 | 低 | 高 | 保持 JSON 支持，渐进迁移 |
| 性能下降 | 低 | 中 | YAML 只在边界解析，引擎保持 JSON |

### 3.2 回滚方案

```python
# 如果 YAML 出现问题，快速回滚到 JSON 的开关
FEATURE_FLAGS = {
    "macro_yaml_input": True,   # 可快速关闭
    "macro_yaml_output": True,  # 可快速关闭
}

# 在 API 层检查
if not FEATURE_FLAGS["macro_yaml_input"]:
    # 强制使用 JSON
    raise HTTPException(status_code=415, detail="YAML temporarily disabled")
```

---

## 4. 成功指标

### 4.1 技术指标
- [ ] YAML 解析错误率 < 1%
- [ ] 端到端延迟增加 < 50ms
- [ ] 单元测试覆盖率 > 80%
- [ ] 零向后兼容性破坏

### 4.2 用户体验指标
- [ ] LLM 宏生成准确率提升（对比 JSON）
- [ ] 用户主动选择 YAML 编辑器的比例
- [ ] 格式错误导致的用户投诉减少

---

## 5. 附录

### 5.1 文件变更清单

#### 新增文件
```
backend/
├── app/
│   ├── utils/
│   │   └── yaml.py                    # YAML 工具函数
│   ├── api/
│   │   └── dependencies/
│   │       └── yaml.py                # FastAPI YAML 依赖
│   └── core/execution/macro/
│       └── parsers.py                 # LLM 响应解析器
└── tests/
    ├── test_yaml_utils.py
    └── api/test_learning_yaml.py

frontend/
└── packages/desktop/src/components/Learning/
    └── SmartReplay/
        └── MacroYamlEditor.tsx        # YAML 编辑器组件
```

#### 修改文件
```
backend/
├── pyproject.toml                     # 添加 PyYAML 依赖
├── app/
│   ├── core/execution/macro/
│   │   └── schema.py                  # 添加 from_yaml/to_yaml
│   ├── api/routes/
│   │   └── learning.py                # 添加 YAML 端点
│   └── config/templates/learning/
│       ├── smart_replay_macro.prompt.j2
│       ├── skill_synthesis.prompt.j2
│       └── multimodal_synthesis.prompt.j2
└── app/config/templates/macro/
    └── decide_next_step.prompt.j2

frontend/
├── package.json                       # 添加 js-yaml 依赖
└── packages/desktop/src/components/Learning/
    └── SkillEditorPage.tsx            # 添加 YAML 编辑器切换
```

### 5.2 时间估算

| 阶段 | 天数 | 负责人 |
|------|------|--------|
| 基础设施 | 2 | 后端开发 |
| API 层 | 1-2 | 后端开发 |
| Prompt 更新 | 2-3 | AI/后端开发 |
| 前端更新 | 3-4 | 前端开发 |
| 测试验证 | 2-3 | QA/测试 |
| 文档部署 | 2 | 技术写作 |
| **总计** | **12-16** | - |

---

**计划制定完成，等待评审通过后实施。**
