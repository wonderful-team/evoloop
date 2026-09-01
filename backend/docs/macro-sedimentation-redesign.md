# 飞轮 Macro 沉淀机制重设计

## 1. 背景与问题

当前系统中的 `SkillSedimentationSubscriber` 监听 `SystemEventType.SESSION_COMPLETED`，并在每个 session 结束时做“是否沉淀”的判断。存在以下问题：

- **盲目性**：该 subscriber 只判断 source（voice/agent），不判断 session 是否真的成功、是否有可重放的执行路径，导致大量无效沉淀意图。
- **耦合 skill 与 macro**：旧的 `learn_from_trace` 工具会同时生成 `LearnedSkill` 与 `Macro`，而按照新的架构方向，`LearnedSkill` 与 `Macro` 已经解耦，`Macro` 应该是沉淀的主要产物。
- **快照过期问题**：如果用户回撤/重试消息，任何存在 `AgentActivity` 中的 trace 快照都会失效。
- **职责放错位置**：沉淀逻辑放在 `app/core/routing` 中，但这是语音路由层，不属于 macro 生命周期管理域。

## 2. 设计目标

- 沉淀由 `FinishNode` 审计成功后的**显式资格标记**触发，而不是 session 完成即触发。
- 沉淀产物仅为 `Macro`（`pending_review` / `is_active=False`），不再生成 `LearnedSkill`。
- trace 以 `trace_events` 表为唯一事实来源，通过 `message_id` 绑定与 rewind 清理，避免快照过期。
- 沉淀订阅器与 trace 清理订阅器分别放在各自正确的领域模块中。
- 复用现有的 `WorkflowSynthesizer` 生成 macro 元数据（name / description / namespace / trigger_patterns / parameters），但 macro script 改由 `MacroScriptCompiler` 确定性编译产出。`WorkflowSynthesizer` 不再持有宏编译逻辑。

## 3. 实施阶段

整个重构分为两个阶段：

- **Phase 1：宏编译与 Skill 合成逻辑解耦**
  - 将 `WorkflowSynthesizer` 中编译 macro script 的逻辑迁移到 `app/core/execution/macro/compiler.py`。
  - 将 `cleanup_macro_steps`、`verify_macro_script`、`MacroVerificationResult` 迁移到 `app/core/execution/macro/`。
  - `WorkflowSynthesizer` 只负责生成 skill 元数据（`SynthesizedSkill`）。
  - 所有调用方（REST API、engine tasks、multimodal synthesizer、`learn_from_trace`）改为显式调用 `MacroScriptCompiler` 编译 macro。
  - 运行测试验证解耦后功能无损。

- **Phase 2：沉淀订阅机制**
  - 删除 `learn_from_trace` 工具。
  - 新增 `TraceEvent.message_id` 绑定与 `TraceRewindSubscriber`。
  - 新增 `MacroSedimentationSubscriber` 与 `MacroCreatorService`。
  - 完成 `FinishNode` 沉淀资格判定与 `AgentActivity` 字段扩展。
  - 运行测试验证沉淀流程。

## 4. 非目标

- 本设计不解决 macro 的人工 review UI 流程，`pending_review` 仍需要后续确认才能激活。
- 不引入新的 LLM 来生成 macro script，macro script 仍由 `MacroScriptCompiler` 确定性地从 trace 编译。
- 不处理跨 thread 的 macro 去重高级语义（如“语义相似但参数不同”）。

## 4. 总体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Agent 执行流程                               │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
                    ┌──────────────────────┐
                    │     FinishNode         │
                    │  AuditService.execute  │
                    │  final_outcome 判断   │
                    └──────────────────────┘
                                 │
              COMPLETED          │  其他
                 │               │
                 ▼               ▼
    ┌──────────────────────┐   不沉淀
    │ TraceSedimentation   │
    │ Service.is_eligible  │
    │ (存在可重放步骤)      │
    └──────────────────────┘
                 │
       eligible = True
                 ▼
    ┌──────────────────────┐
    │ AgentActivity 写入     │
    │ final_outcome          │
    │ macro_creation_eligible │
    │ summary                │
    └──────────────────────┘
                 │
                 ▼
    ┌──────────────────────┐
    │ publish_session_completed │
    │ SystemEventType.SESSION_COMPLETED │
    └──────────────────────┘
                 │
                 ▼
    ┌──────────────────────┐
    │ MacroSedimentation   │
    │ Subscriber           │
    │ (execution/macro)    │
    └──────────────────────┘
                 │
                 ▼
    ┌──────────────────────┐
     │ MacroCreator          │
     │ Service.create_macro_from_trace() │
    │ 1. 读取 AgentActivity  │
    │ 2. 校验 final_outcome  │
    │ 3. 读取当前有效 trace  │
    │ 4. WorkflowSynthesizer │
    │    生成 metadata       │
   │ 5. MacroScriptCompiler │
   │    .compile(sequence)   │
   │ 6. create_macro_from_  │
    │    synthesis           │
    │ 7. publish_macro_      │
    │    mutated             │
    └──────────────────────┘

Rewind 流程：

    RewindRequestedEvent
                 │
                 ▼
    ┌──────────────────────┐
    │ TraceRewindSubscriber │
    │ (learning/event)      │
    │ 清理被删除 message 的  │
    │ trace_events 记录     │
    └──────────────────────┘
```

## 5. 关键变更

### 5.1 移除 `SkillSedimentationSubscriber`

- 删除 `app/core/routing/subscribers.py` 中的 `SkillSedimentationSubscriber` 及相关辅助函数。
- 删除 `app/core/config.py` 中的 `SKILL_SEDIMENTATION_ENABLED` 配置。
- 删除 `tests/routing/test_skill_sedimentation_m0.py`。

### 5.2 宏编译与 Skill 合成解耦（Phase 1）

当前 `WorkflowSynthesizer` 同时承担两件事：生成 skill 元数据、编译 macro script。Phase 1 要把后者拆到 `app/core/execution/macro/`。

#### 5.2.1 新增 `app/core/execution/macro/compiler.py`

迁移以下内容：

- `ALLOWED_UI_ACTIONS` 白名单
- `_EVENT_TYPE_REMAP` 映射表
- `_compile_macro_script(sequence)` 方法，封装为 `MacroScriptCompiler.compile(sequence)`
- 移动端事件归一化 `_normalize_mobile_event()`，从 `TraceParser` 移入

`MacroScriptCompiler` 只依赖 `TraceSequence` / `TraceStep`，输出 `MacroScript`。

#### 5.2.2 新增 `app/core/execution/macro/utils.py`

迁移：

- `cleanup_macro_steps()`
- `verify_macro_script()`

#### 5.2.3 迁移 `MacroVerificationResult`

从 `app/core/learning/schemas/migrated.py` 移到 `app/core/execution/macro/schemas.py`。

#### 5.2.4 精简 `WorkflowSynthesizer`

- 删除 `_compile_macro_script`、`verify_macro`。
- 删除 `ALLOWED_UI_ACTIONS`、`_EVENT_TYPE_REMAP`。
- `SynthesisResult` 不再包含 `macro_script` 字段。
- `synthesize()` 只返回 `SynthesizedSkill` 元数据（或 `SynthesisResult(skill=...)`）。

#### 5.2.5 更新 `TraceParser`

- 移除 `_normalize_mobile_event()` 调用。
- 移动端事件保持原始 event_type，由 `MacroScriptCompiler` 在编译阶段归一化。

#### 5.2.6 更新调用方

所有需要同时生成 skill 和 macro 的地方改为两段式调用：

```python
from app.core.learning.workflow_synthesizer import WorkflowSynthesizer
from app.core.learning.macro.compiler import MacroScriptCompiler
from app.core.learning.trace_parser import TraceParser

sequence = await TraceParser(thread_id).parse()
skill = await WorkflowSynthesizer(...).synthesize_skill(sequence)
macro_script = MacroScriptCompiler().compile(sequence)
```

受影响调用方：

- `app/api/routes/learning/skills.py` 的 `synthesize_skill`
- `app/core/engine/tasks.py` 中的 synthesis 任务
- `app/core/learning/multimodal_synthesizer.py` 的 `_compile_macro_from_events`
- `app/domain/tools/learning/learn_from_trace.py`（Phase 2 删除，但 Phase 1 需先改为使用 `MacroScriptCompiler`）

### 5.3 `TraceEvent` 绑定 `message_id`

在 `app/models/learning.py` 的 `TraceEvent` 中增加字段：

```python
message_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
```

所有写入 `TraceEvent` 的位置应尽可能带上 `message_id`：

- `TraceCallbackHandler`：从 callback 上下文或当前消息中获取 `message_id`。
- `app/api/routes/learning/mirror.py` 与 `app/core/environment/controllers/mirror_session.py`：在构建 trace event 时写入对应 message_id。
- 全局 observation 事件（桌面点击、手机镜像）没有对应 message 时允许为 `None`。

### 5.4 `TraceRewindSubscriber`

新增 `app/core/learning/event/subscribers.py`：

```python
@event_register()
class TraceRewindSubscriber:
    @event_subscribe(RewindEventType.REWIND_REQUESTED)
    async def on_rewind_requested(self, event: RewindRequestedEvent) -> None:
        affected_message_ids = event.affected_message_ids or []
        target_sequence = event.target_sequence

        # 1. 删除 message_id 在被删除消息列表中的 trace_events
        # 2. 删除 message_id 为空但 step_number >= target_sequence 的 trace_events
```

这样回撤后 trace 与 conversation 始终一致。

### 5.5 `FinishNode` 沉淀资格判定

在 `app/core/engine/nodes/finish.py` 中：

1. 获取 `AuditResult`，提取 `final_outcome`。
2. 仅当 `final_outcome.upper() == "COMPLETED"` 时，调用 `TraceSedimentationService.is_eligible(thread_id)`。
3. `is_eligible` 从 `trace_events` 读取当前有效事件，过滤探索性/失败事件，若存在至少一个可重放动作则返回 `True`。
4. 若 eligible，写入 `AgentActivity.macro_creation_eligible = True`。

### 5.6 `AgentActivity` 字段变更

不增加 `verified_trace_json` 字段。只增加/保留：

```python
final_outcome: Mapped[str] = mapped_column(Text, default="")
summary: Mapped[str] = mapped_column(Text, default="")
macro_creation_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
```

`main_goal` 已存在，继续使用。

### 5.7 `MacroSedimentationSubscriber`

新增到 `app/core/execution/macro/event/subscribers.py`：

```python
@event_register()
class MacroSedimentationSubscriber:
    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: SessionCompletedEvent) -> None:
        if not getattr(event.data, "macro_creation_eligible", False):
            return

        thread_id = event.data.thread_id
        await MacroCreatorService.create_macro_from_trace(thread_id)
```

### 5.8 `MacroCreatorService`

新增 `app/core/execution/macro/macro_creator_service.py`，核心方法：

```python
class MacroCreatorService:
    @staticmethod
    async def is_eligible(thread_id: str) -> bool:
        """判断是否存在可沉淀的确定性步骤。"""

    @staticmethod
    async def create_macro_from_trace(thread_id: str) -> Macro | None:
        """从 trace 创建 pending_review macro。"""
```

`create_macro_from_trace()` 内部流程：

1. 读取 `AgentActivity`，校验 `final_outcome == "COMPLETED"` 且 `macro_creation_eligible` 为 `True`。
2. 读取当前 thread 的有效 trace（过滤已删除消息、探索性/失败事件）。
3. 使用 `WorkflowSynthesizer` 生成 `SynthesizedSkill` 元数据（name / description / namespace / trigger_patterns / parameters）。
4. 使用 `MacroScriptCompiler().compile(sequence)` 编译 `macro_script`。
5. 处理命名冲突：若同名 macro 已存在，追加 hash 或计数后缀。
6. 调用 `create_macro_from_synthesis(...)` 创建 `Macro`：
   - `status="pending_review"`
   - `is_active=False`
   - `project_id=None`（全局沉淀）
   - `fallback_skill_id=None`（不绑定 skill）
   - `allow_self_healing=True`
7. 发布 `macro_mutated`。

### 5.9 Macro 元数据生成

复用 `WorkflowSynthesizer`：

```python
synthesizer = WorkflowSynthesizer(...)
skill_data = await synthesizer.synthesize_skill(sequence)
```

取：

- `name` → `Macro.name`
- `description` → `Macro.description`
- `namespace` → `Macro.namespace`
- `trigger_patterns` → `Macro.trigger_patterns`
- `parameters`（经 `normalize_parameters` 处理） → `Macro.parameters`

`macro_script` 不使用 `result` 中 LLM 生成的版本，而是使用 `MacroScriptCompiler().compile(sequence)` 的确定性版本。

### 5.10 删除 `learn_from_trace` 工具

- 删除 `app/domain/tools/learning/learn_from_trace.py`。
- 从 `app/domain/tools/learning/__init__.py` 移除导出。
- 从 `app/core/engine/config/agent_main.yaml` 工具列表中移除 `learn_from_trace`。
- 从 `app/config/templates/core/engine/finish.prompt.j2` 中移除“调用 `learn_from_trace`”的指令。
- 删除相关 i18n 文案。
- 重写/删除 `tests/unit/core/learning/test_skill_lifecycle_db.py` 中依赖 `learn_from_trace` 的测试。

## 6. 数据模型变更

### `TraceEvent`

新增字段：

```python
message_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
```

### `AgentActivity`

新增字段：

```python
summary: Mapped[str] = mapped_column(Text, default="")
macro_creation_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
```

不新增 `verified_trace_json`。

## 7. 事件流

```
FinishNode 完成审计
  ├── AuditResult.final_outcome = "COMPLETED"
  ├── TraceSedimentationService.is_eligible(thread_id) -> True
  ├── AgentActivity 写入 final_outcome / summary / macro_creation_eligible
  └── publish_session_completed
         └── MacroSedimentationSubscriber.on_session_completed
              └── MacroCreatorService.create_macro_from_trace(thread_id)
                     └── publish_macro_mutated

Rewind 操作
  └── publish_rewind_requested
         └── TraceRewindSubscriber.on_rewind_requested
              └── 删除 trace_events 中被回撤消息对应的记录
```

## 8. Trace 过滤规则

### 8.1 消息存在性过滤

只保留满足以下条件之一的 `TraceEvent`：

- `message_id` 在 `messages` 表中仍然存在。
- `message_id IS NULL` 且 `step_number` 小于当前 thread 最新 sequence（或不被本次 rewind 影响）。

### 8.2 事件类型过滤（排除探索性/噪声）

排除：

- `llm_output`
- `tool_result`
- `node_start`
- `macro_thought`
- `list_macros`, `list_skills`, `search_history`, `recall`
- `read_file`, `list_dir`, `grep_search`, `find_files`
- `ask_human`, `ask_confirm`, `forget_tool_outputs`
- `think`

### 8.3 失败信号过滤

排除：

- `reward is not None and reward < 0`
- `payload.get("success") is False`
- `user_feedback` 明确为负向（可选）

### 8.4 可重放动作白名单

保留以下动作类型（`action_type` 或 `event_type`）：

- `desktop_control`, `mobile_control`, `browser_control`
- `run_macro`
- `write_file`, `edit_file`, `move_file`, `delete_file`
- `tap`, `swipe`, `key_press`, `click`, `input`, `navigate`, `open_app`, `close_app`
- `scroll`, `wait`, `wait_for`
- `get_text`, `get_attribute`, `get_html`, `dump_ui`
- `applescript`, `run_js`

注意：`execute_command` 是否允许进入 macro 由运行时风险策略决定，建议初始版本默认排除或标记为 `requires_confirmation=True`。

## 9. Macro 命名与描述规范

沿用 `app/config/templates/core/learning/skill_synthesis.prompt.j2` 的规范：

- **name**：短、描述性，建议使用英文 snake_case 或中文自然名称。例如 `open_wechat_send_message` / `打开微信发送消息`。
- **description**：简明说明 macro 做什么，包含具体应用名称。例如："Open WeChat and send a text message to the specified contact."
- **namespace**：逻辑分类，如 `web/example`、`os/macos/wechat`、`cross_app/mobile`。
- **trigger_patterns**：从用户初始意图（`main_goal` / 首条人类消息）提取，用于后续意图匹配。可包含多个同义表达。
- **parameters**：从 trace 中识别出的变量（如 `contact_name`、`message_text`）。

命名冲突处理：若同名 macro 已存在，追加 `_{short_hash(main_goal)[:6]}` 或递增后缀。

## 10. 配置项

新增或复用配置：

```python
AUTO_MACRO_CREATION_ENABLED: bool = True  # 总开关
```

`MacroSedimentationSubscriber` 或 `MacroCreatorService` 首先检查此开关，为 `False` 时直接跳过。

## 11. 测试策略

### 11.1 单元测试

- `tests/unit/core/learning/test_trace_rewind_subscriber.py`：验证 rewind 时正确清理 trace_events。
- `tests/unit/core/execution/macro/test_macro_creator_service.py`：
  - 仅 `COMPLETED` + eligible 才创建 macro。
  - `INCOMPLETE` / `FAILED` 不创建。
  - 无有效步骤时不创建。
  - 复用 `WorkflowSynthesizer` 生成元数据。
  - 确定性编译 macro script。
  - 创建出的 macro 状态为 `pending_review` / `is_active=False` / `project_id=None`。
- `tests/unit/core/execution/macro/test_macro_sedimentation_subscriber.py`：验证事件订阅与过滤逻辑。

### 11.2 集成测试

- 跑完整 agent 流程，触发 `FinishNode`，验证 `AgentActivity` 写入正确。
- 执行 rewind，验证 trace_events 被正确清理，且 `MacroCreatorService` 不会从已清理 trace 中沉淀。

### 11.3 旧测试更新

- 更新/删除 `tests/unit/core/learning/test_skill_lifecycle_db.py` 中所有依赖 `learn_from_trace` 的 case。

## 12. 数据库迁移

生成 Alembic migration：

1. `trace_events` 表增加 `message_id VARCHAR(36) NULL` 及索引。
2. `agent_activities` 表增加：
   - `summary TEXT DEFAULT ''`
    - `macro_creation_eligible BOOLEAN DEFAULT FALSE`

## 13. 待确认问题

1. `execute_command` 是否允许进入 macro？若允许，是否默认 `requires_confirmation=True`？
2. 是否允许沉淀 project 级别的 macro？当前设计默认 `project_id=None`（全局），是否需要按 project 隔离？
3. 同名 macro 冲突时采用 hash 后缀还是计数后缀？
4. 是否保留 `learn_from_trace` 作为“手动触发沉淀”的入口？本设计建议完全删除，但可作为可选项讨论。
5. `message_id` 在 `TraceCallbackHandler` 中如何可靠获取？是否需要扩展 callback 上下文以传递当前消息 ID？
