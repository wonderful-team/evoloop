# Evoloop 宏（Macro）业务最终全面评估报告

## 执行摘要

本次评估对 Evoloop 项目的宏业务进行了从录制/创建技能 → 存储 → 编辑 → 执行的完整链路检查。发现了 **1个P0级问题**、**5个P1级问题** 和 **4个P2级问题**，以及 **2个未闭环功能**。

---

## 一、完整业务链路检查

### 1.1 录制事件 → 宏步骤转换

**流程：**
```
录制事件 (Frontend)
    ↓ POST /global/events, /dom/events, /mirror/events
TraceEvent 表 (Database)
    ↓ WorkflowSynthesizer._compile_macro_script()
宏步骤列表 (List[dict])
    ↓ yaml.dump()
YAML 字符串
```

**状态：** ✅ 正常
- 录制事件通过实时 API 持久化到 TraceEvent 表
- `WorkflowSynthesizer._compile_macro_script()` 正确转换事件为宏步骤
- 支持多种事件源：DOM、Mobile、Desktop、Global

### 1.2 合成器生成宏格式

**流程：**
```
TraceSequence
    ↓ _compile_macro_script()
List[dict] steps
    ↓ yaml.dump()
YAML 字符串 → LearnedSkill.macro_script
```

**状态：** ⚠️ 有缺陷（见P0问题#1）

### 1.3 数据库存储格式

**表结构：**
```python
# LearnedSkill 模型 (backend/app/models/learning.py:148)
macro_script: Mapped[str | None] = mapped_column(Text, nullable=True)  # YAML format
execution_mode: Mapped[str] = mapped_column(String(20), default="agentic")  # "agentic" or "deterministic"
allow_self_healing: Mapped[bool] = mapped_column(default=True)
```

**状态：** ✅ 正常
- 使用 Text 类型存储 YAML 字符串
- 支持 null/空值
- 有执行模式和自愈开关字段

### 1.4 API 返回格式

| 端点 | 输入 | 输出 | 状态 |
|------|------|------|------|
| GET /skills/{id} | - | macro_script: string (YAML) | ✅ |
| PUT /skills/{id} | macro_script: string (YAML) | 更新后的技能 | ⚠️ 验证严格 |
| POST /skills/{id}/execute | params: object | 执行结果 | ✅ |
| GET /skills/{id}/yaml | - | text/yaml | ✅ |
| PUT /skills/{id}/yaml | text/yaml (raw body) | 更新结果 | ✅ |
| POST /skills/synthesize | thread_id, session_id | skill + YAML | ⚠️ 有P0问题 |
| POST /skills/validate-yaml | yaml_content | valid, errors, step_count | ✅ |
| POST /skills/create-from-yaml | yaml_content | skill_id | ✅ |

### 1.5 前端显示和编辑

**流程：**
```
API Response (YAML string)
    ↓ SkillEditorPage
yamlLoad() → steps[]
    ↓ MacroEditor (可视化) 或 MacroYamlEditor (YAML)
编辑 steps
    ↓ yamlDump()
API Request (YAML string)
```

**状态：** ⚠️ 有缺陷（见P1问题#4）

### 1.6 执行时解析

**流程：**
```
skill.macro_script (YAML string)
    ↓ macro_from_yaml()
List[dict] steps
    ↓ MacroScript(steps=steps)
MacroScript 对象
    ↓ MacroEngine.execute_steps()
执行结果
```

**状态：** ✅ 正常

---

## 二、发现问题清单

### 🔴 P0 级别（严重 - 立即修复）

#### 问题 #1: skill_synthesizer.py 中重复调用 `_generate_skill_yaml`

**位置：** `backend/app/core/learning/skill_synthesizer.py:131 和 161`

**代码：**
```python
# 第131行
yaml_output = await self._generate_skill_yaml(narrative, summary, first_user_msg)

# ... 中间代码 ...

# 第161行 - 重复调用！
yaml_output = await self._generate_skill_yaml(narrative, summary, first_user_msg)
```

**影响：**
- 每次技能合成都进行两次 LLM 调用
- 浪费 API 资源，增加合成时间（2x）
- 第二次调用可能生成不同的 YAML，导致验证结果不一致

**修复方案：**
```python
# 删除第161行的重复调用
# 只保留第131行的调用
```

---

### 🟠 P1 级别（重要 - 优先修复）

#### 问题 #2: 前端 `safeParseMacro` 对嵌套格式支持不完善

**位置：** `frontend/packages/desktop/src/components/Learning/SkillEditorPage.tsx:132-163`

**问题：**
当后端返回的 YAML 格式为嵌套格式时，解析可能失败：
```yaml
# 这种格式解析可能有问题
macro_script:
  steps:
    - type: action
      ...
```

**修复方案：**
增强 safeParseMacro 函数以处理更多嵌套情况。

#### 问题 #3: `macro_from_yaml` 对纯数组格式的处理不一致

**位置：** `backend/app/utils/yaml.py:79-111`

**问题：**
当 YAML 是直接的步骤数组（非包裹格式）时：
```yaml
# 直接数组格式
- type: action
  event_type: click
- type: action
  event_type: input
```

当前代码处理：
```python
# 第106行
steps = data.get("steps", data.get("macro_script", data))
# 如果 data 是列表，data.get() 会抛出 AttributeError
```

**修复方案：**
```python
def macro_from_yaml(yaml_content: str) -> list[dict]:
    # ... 现有代码 ...
    
    # Handle None (empty YAML)
    if data is None:
        return []
    
    # Handle direct array format
    if isinstance(data, list):
        return data
    
    if not isinstance(data, dict):
        raise YAMLError("YAML root must be a mapping or list")
    
    # Support both wrapped and unwrapped formats
    steps = data.get("steps", data.get("macro_script", []))
    # ...
```

#### 问题 #4: API 错误处理不够具体

**位置：** 多处使用 `except Exception`

**问题：**
在 `learning.py` 中有超过20处使用裸的 `except Exception`，这会：
- 捕获不应该捕获的错误（如 KeyboardInterrupt）
- 隐藏真正的错误原因
- 给调试带来困难

**建议改进：**
```python
# 替换
except Exception as e:
    logger.exception(f"...")
    
# 为
except (ValidationError, YAMLError) as e:
    logger.error(f"Validation error: {e}")
except SQLAlchemyError as e:
    logger.error(f"Database error: {e}")
except Exception as e:
    logger.exception(f"Unexpected error: {e}")
```

#### 问题 #5: 空宏脚本执行边界情况处理不完善

**位置：** `backend/app/core/execution/macro/service.py:47-49`

**当前代码：**
```python
if not script.steps:
    logger.warning(f"[{thread_id}] Macro execution skipped: script is empty.")
    return {"success": False, "message": "Macro script is empty"}
```

**问题：**
- 当 execution_mode 为 "deterministic" 但 macro_script 为空时，应自动回退到 agentic 模式
- 当前返回错误，用户体验不佳

**修复方案：**
在 `learning.py` 的 `execute_skill` 函数中改进回退逻辑：
```python
if execution_mode == "deterministic" and skill.macro_script:
    try:
        macro_steps = macro_from_yaml(skill.macro_script)
        if not macro_steps:  # 空宏脚本
            logger.warning(f"Empty macro script, falling back to agentic mode")
            execution_mode = "agentic"
    except YAMLError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse macro YAML: {e}")
```

#### 问题 #6: 前端 MacroEditor 和 MacroYamlEditor 同步状态不一致

**位置：** `SkillEditorPage.tsx:455-471`

**问题：**
当用户在 Visual 和 YAML 编辑器之间切换时，状态同步可能存在延迟或竞争条件。

---

### 🟡 P2 级别（次要 - 建议修复）

#### 问题 #7: 类型定义不一致

**位置：** 前后端 MacroStep 类型定义

**前端 (`MacroEditor.tsx:57-82`)：**
```typescript
interface MacroStep {
    step_number: number
    type: "action" | "extract" | "dump" | "wait" | "if" | "loop" | "control"
    source: "dom" | "mobile" | "desktop" | "hybrid" | "global"
    // ...
}
```

**后端 (`schema.py:111-189`)：**
```python
class MacroStep(BaseModel):
    step_number: Optional[int] = None
    type: MacroStepType  # 枚举值不同
    source: MacroSource = MacroSource.DOM
    # ...
```

**差异：**
- 前端 `source` 包含 "hybrid"，后端没有
- 前端 `type` 包含 "wait"，后端没有（作为 event_type）

#### 问题 #8: 参数注入正则表达式不够健壮

**位置：** `backend/app/core/execution/macro/engine.py:1324-1347`

**当前正则：**
```python
pattern = r"\{\{\s*(?:parameters\.)?([a-zA-Z0-9_\-\.]+)\s*\}\}"
```

**问题：**
不支持数组索引，如 `{{items[0].name}}`

#### 问题 #9: MultimodalSynthesizer 中重复导入 yaml

**位置：** `backend/app/core/learning/multimodal_synthesizer.py:28 和 266`

```python
# 第28行
import yaml

# ... 在第266行又导入一次 ...
import yaml
```

#### 问题 #10: 缺少批量操作 API

**问题：**
- 没有批量导入/导出技能的 API
- 没有批量验证宏脚本的 API

---

## 三、未闭环功能

### 1. Smart Replay 合成功能依赖检查 ⚠️

**位置：** `learning.py:1834` 和 `learning.py:1857`

```python
from app.core.learning.smart_synthesizer import SmartSynthesizer

synthesizer = SmartSynthesizer(
    job_id=job_id,
    session_id=session_id,
    ...
)
skill = await synthesizer.synthesize()
```

**检查项：**
- [ ] `SmartSynthesizer` 类是否完全实现？
- [ ] 相关模板文件是否都存在？
- [ ] 后台任务执行是否可靠？

**建议：** 验证 `backend/app/core/learning/smart_synthesizer.py` 是否存在且功能完整。

### 2. 视频文件处理错误恢复机制 ⚠️

**位置：** `multimodal_synthesizer.py:164-175`

```python
try:
    llm_response = await self._call_vision_llm(...)
except Exception as e:
    logger.error(f"Vision LLM call failed: {e}")
    raise RuntimeError(f"LLM analysis failed: {e}")
```

**问题：**
- 如果视频文件处理失败（如损坏的帧），没有重试或降级机制
- 用户可能失去整个录制会话的数据

**建议：** 添加降级策略，如跳过损坏帧继续处理。

---

## 四、自愈功能评估

### 4.1 自愈策略实现状态

**位置：** `backend/app/core/execution/macro/healing_policy.py`

| 层级 | 配置项 | 状态 |
|------|--------|------|
| 全局 | `settings.ENABLE_MACRO_SELF_HEALING` | ✅ 实现 |
| 技能级 | `skill.allow_self_healing` | ✅ 实现 |
| 执行级 | `execution_params._allow_self_healing` | ✅ 实现 |

### 4.2 自愈触发流程

```
MacroEngine 执行失败
    ↓
MacroService.run() 捕获失败
    ↓
SelfHealingPolicy.check(skill, params)
    ↓
如果允许自愈：发布 MacroExecutionFailedEvent
    ↓
system_bus 分发事件给 Advisor
    ↓
Advisor 生成修复建议
```

**状态：** ✅ 完整实现

---

## 五、数据类型一致性矩阵

| 阶段 | 格式 | 验证 | 备注 |
|------|------|------|------|
| 数据库 | YAML String | 存储时不验证 | Text 类型 |
| API 传输 | YAML String | 接收时验证 | validate_macro_yaml() |
| 前端编辑 | YAML String | 实时验证 | js-yaml |
| 执行时 | List[dict] | Pydantic Model | MacroScript |
| 合成器输出 | YAML String | 无 | yaml.dump() |

**一致性评级：** 良好（⚠️  minor issues）

---

## 六、建议修复优先级

### 立即修复（本周）
1. **P0-1:** 删除 `skill_synthesizer.py` 第161行的重复调用

### 高优先级（下周）
2. **P1-3:** 修复 `macro_from_yaml` 纯数组格式处理
3. **P1-2:** 增强前端 `safeParseMacro` 函数
4. **P1-5:** 改进空宏脚本回退逻辑

### 中优先级（下个月）
5. **P1-4:** 改进错误处理，使用更具体的异常类型
6. **P2-7:** 统一前后端类型定义
7. **P2-9:** 清理重复导入

### 低优先级（ backlog ）
8. **P2-8:** 增强参数注入正则
9. **P2-10:** 添加批量操作 API

---

## 七、测试建议

### 必须测试的边界情况

1. **空宏脚本：**
   - `macro_script: null`
   - `macro_script: ""`
   - `macro_script: "[]"`
   - `macro_script: "steps: []"`

2. **格式变体：**
   - 直接数组格式：`[{"type": "action"}]`
   - 包裹格式：`{"steps": [{"type": "action"}]}`
   - 完整格式：`{"version": "1.0", "steps": [...]}`

3. **执行模式切换：**
   - Agentic → Deterministic
   - Deterministic → Agentic（macro_script 为空）

4. **自愈场景：**
   - 全局禁用自愈
   - 技能级禁用自愈
   - 执行级禁用自愈

---

## 八、总结

Evoloop 的宏业务整体架构设计良好，数据流清晰，自愈功能完整。主要问题是 **P0-1 的重复 LLM 调用** 需要立即修复，这直接影响成本和性能。其他问题主要是边界情况处理和代码健壮性方面的改进。

**整体评级：** B+ （良好，有小问题需修复）

| 维度 | 评级 | 说明 |
|------|------|------|
| 架构设计 | A | 清晰的分层，合理的职责划分 |
| 代码质量 | B | 有重复代码和裸 except 问题 |
| 边界处理 | B- | 空值和格式兼容性需改进 |
| 自愈功能 | A | 完整的三层策略实现 |
| 文档注释 | B+ | 关键函数有 docstring |
| 测试覆盖 | ? | 需要验证测试覆盖情况 |
