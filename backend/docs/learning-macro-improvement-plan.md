# Learning 模块宏录制与合成系统改进计划

## 背景

基于"预定会议"宏（383）调试和真实录制数据分析，发现当前 learning 模块的录制-编译-合成 pipeline 在桌面宏自动化场景下存在系统性缺口。本文档逐一分析，并给出分阶段可实施的改进方案。

---

## 1. 当前架构与发现的问题

### 1.1 录制层：Rust recorder 二进制

**文件**: `frontend/src-tauri/src/bin/recorder.rs`

```
rdev::listen (CGEventTap)
  → mouse_click: {position, window_title, app_name, timestamp}
  → key_press:   {key, position, window_title, app_name, timestamp}
  → (key_release: 空分支，不输出)
  → println! JSON → stdout
```

**问题 #1：key_press 未写入 key_name 列**

`mirror.py:_build_trace_event` 没有 `key_name` 参数，`payload.key` 存了数据但 `key_name` 列永远为 NULL。下游 `trace_parser.py:152` 和 `multimodal_synthesizer.py:559` 读的都是 `event.key_name`（死列）。

**问题 #2：key_press 不触发时，全程无声**

macOS CGEventTap 键盘捕获需要辅助功能权限。如果没授权，`rdev::listen` 不会报错，只是静默不产出 key_press 事件。我们在 session `c8a2f6cd` 中看到的就是这种情况——大量 mouse_click，零 key_press。

**问题 #3：录坐标不录元素名**

录的 `position=(635.45, 641.34)` 是屏幕绝对坐标，不是 `element_name`。回放时如果窗口移动/缩放，坐标全废。

### 1.2 编译层：MacroScriptCompiler

**文件**: `app/core/execution/macro/compiler.py`

**问题 #4：`ALLOWED_UI_ACTIONS` 缺少桌面宏事件类型**

当前包含： `click`, `key_press`, `scroll`, `open_app`, `applescript` 等
缺少： `ax_press`, `cgclick`, `wait`

**问题 #5：编译产物使用死坐标**

```python
# 当前产出
MacroStep(event_type="click", payload={"x": 635.45, "y": 641.34})

# 需要的产出
MacroStep(event_type="click", payload={"element_name": "预定会议"})
```

**问题 #6：不生成 wait 时序**

`TraceEvent.timestamp` 存在但 compiler 不计算相邻事件的时间间隔，不插入 `wait` 步骤。

### 1.3 合成层：MultimodalSkillSynthesizer

**文件**: `app/core/learning/multimodal_synthesizer.py`

**问题 #7：LLM Prompt 未教桌面宏格式**

`multimodal_synthesis.prompt.j2` 的 Desktop source 只列出：
```
"click", "double_click", "type_text", "key_press", "scroll", "drag_drop",
"screenshot", "dump_ui", "open_app", "applescript"
```
缺少 `ax_press`, `cgclick`, `wait`。也没有 `optional: true` 或 `element_name` 概念。

**问题 #8：LLM 从未见过我们的宏 schema 示例**

LLM 看到的示例是 DOM source 为主的（navigate/click/extract），不知道桌面宏的 `element_name` + `ax_press` + `applescript` 组合应该怎么写。

### 1.4 数据层：TraceEvent 模型

**文件**: `app/models/learning.py`

**问题 #9：key_name 列是死列**

写入端（`_build_trace_event`）没有 `key_name` 参数，读端（`trace_parser`, `multimodal_synthesizer`）却从列读取。实际数据在 `payload["key"]` 里。

**问题 #10：没有 `element_name` / `element_role` 列**

这些值只在 `_interaction_mixin._record()` 中写入 `payload.element_name`，无法被 recorder 使用。

---

## 2. 改进方案

### Phase 1：录制层 — 录元素名 + 补键盘捕获

**目标**: 录制时实时将鼠标坐标反向解析为 `element_name`，同时确保 key_press 可靠捕获。

#### 1.1 在 `persist_global_events` 中注入 OCR 反向解析

文件：`app/api/routes/learning/mirror.py`

```python
async def persist_global_events(body: GlobalEventsRequest, ...):
    for event in body.events:
        # 新增：OCR 反向解析坐标 → element_name
        element_name = None
        element_role = None
        if event.event_type == "mouse_click" and event.position:
            # 调 tri-engine 解析
            from app.core.environment.controllers.desktop._element_mixin import DesktopElementMixin
            resolved = await DesktopElementMixin._resolve_element_at_point(
                event.position[0], event.position[1]
            )
            if resolved:
                element_name = resolved.get("text")
                element_role = resolved.get("role")

        # 存储到 payload
        payload = {
            "mouse_button": event.mouse_button,
            "position": event.position,
            "key": event.key,
            "element_name": element_name,   # ← 新增
            "element_role": element_role,   # ← 新增
            ...
        }
```

新增 `_resolve_element_at_point` 方法到 `_element_mixin.py`：

```python
@classmethod
async def _resolve_element_at_point(cls, x: float, y: float):
    """OCR 反向解析：给定屏幕坐标，返回该位置的 UI 元素信息"""
    app_info = await asyncio.to_thread(macos_driver.get_current_app)
    bounds = app_info.get("bounds", {})
    temp_img = await asyncio.to_thread(macos_driver.screenshot, region=bounds)
    result = await vision_engine.process(VisionTask.OCR, temp_img)
    if result.success:
        for el in result.elements:
            if el.x <= x <= el.x + el.width and el.y <= y <= el.y + el.height:
                return {"text": el.text.strip(), "role": "AXButton"}
    return None
```

#### 1.2 补 key_press 捕获

**方案 A（轻量）**: 在 `recorder.rs` 中，为 key_press 也尝试从 `rdev::grab` 而非 `listen` 捕获（grab 不需要辅助功能权限，但会阻止事件传递，不适合生产）。

**方案 B（推荐）**: 用 `ax_press` 替代——在 AppleScript 轮询循环中，检测当前窗口的 AXFocusedUIElement 是否变化，推断键盘输入。

**方案 C（最快落地）**: 在前端 `GlobalRecorderManager.tsx` 中，录制期间同时监听 Tauri 的全局快捷键事件（F12 等），补充捕获 Cmd+A/Cmd+V/Cmd+W 等组合键。

**推荐方案 C**，改动最小。在 `useGlobalRecorder.ts` 的 `flushEvents` 中增加键盘事件类型。

#### 1.3 修复 key_name 死列

方案：在 `mirror.py:_build_trace_event` 中增加 `key_name` 参数并写入列。

```python
def _build_trace_event(
    ...,
    key_name: str | None = None,   # 新增
):
    ...
    return TraceEvent(
        ...,
        key_name=key_name,
    )
```

同时在 `persist_global_events` 中传入：

```python
event_row = _build_trace_event(
    ...,
    key_name=event.key,  # ← 新增
)
```

### Phase 2：编译层 — 桌面宏编译路径

#### 2.1 扩展 `ALLOWED_UI_ACTIONS`

文件：`app/core/execution/macro/compiler.py`

```python
ALLOWED_UI_ACTIONS = {
    # ... 现有 ...
    # Desktop 宏新增
    "ax_press",
    "cgclick",
    "wait",          # 已有
    "applescript",   # 已有
}
```

#### 2.2 增加桌面专用编译路径

在 `compile()` 中，当 `source_type == MacroSource.DESKTOP` 且 `action_type == "mouse_click"` 时：

```python
def _compile_desktop_click(self, step: TraceStep) -> MacroStep:
    """桌面鼠标点击 → element_name 优先，坐标兜底"""
    element_name = step.action_args.get("element_name")
    x = step.action_args.get("position", [0, 0])[0]
    y = step.action_args.get("position", [0, 0])[1]

    if element_name:
        return MacroStep(
            event_type=MacroActionType.CLICK,
            source=MacroSource.DESKTOP,
            payload={"element_name": element_name},
        )
    else:
        return MacroStep(
            event_type=MacroActionType.CLICK,
            source=MacroSource.DESKTOP,
            payload={"x": x, "y": y},
        )
```

#### 2.3 插入 wait 时序

在 `compile()` 主循环中：

```python
prev_timestamp = None
for step in sequence.steps:
    if prev_timestamp and step.timestamp:
        delta_ms = (step.timestamp - prev_timestamp) * 1000
        if delta_ms > 1500:  # 间隔超过 1.5s
            steps.append(MacroStep(
                type=MacroStepType.ACTION,
                event_type=MacroActionType.WAIT,
                source=source_type,
                payload={"duration_ms": int(delta_ms)},
            ))
    prev_timestamp = step.timestamp
```

#### 2.4 key_press → appleScript 合并

连续的 key_press 事件合并为一条 appleScript：

```python
# 检测连续 key_press 序列
key_buffer = []
for step in sequence.steps:
    if step.action_type == "key_press":
        key_buffer.append(step.action_args.get("key"))
    else:
        if key_buffer:
            script = self._keys_to_applescript(key_buffer)
            steps.append(MacroStep(event_type="applescript",
                                   payload={"script": script}))
            key_buffer = []
```

### Phase 3：合成层 — LLM Prompt 改进

#### 3.1 更新 `multimodal_synthesis.prompt.j2` Desktop 事件类型

```
### 3. Allowed Event Types by Source:
- **DOM**: "navigate", "click", "input", ...
- **Desktop**: "click", "double_click", "type_text", "key_press",
    "scroll", "drag_drop", "screenshot", "dump_ui",
    "open_app", "applescript",
    "ax_press", "cgclick", "wait".          # ← 新增
- **Mobile**: ...
```

#### 3.2 增加 `element_name` 和 `optional` 概念

```
### Desktop Element Reference (STRICT):
- For desktop "click", use "element_name" (NOT x/y coordinates) in payload.
  The element_name is resolved at runtime via OCR + Accessibility API.
  Example: payload: {"element_name": "预定会议"}
- Use "optional: true" for conditional elements that may not always appear
  (e.g., conflict popups, error dialogs).
  Example: payload: {"element_name": "仍然预定", "optional": true}
```

#### 3.3 增加桌面宏 YAML 示例

在 prompt 中增加一个完整的桌面宏示例（以"预定会议"为模板），包含：
- `applescript` 激活应用
- `click` + `element_name`
- `applescript` 粘贴日期时间
- `ax_press` 点击按钮
- `optional: true` 冲突处理
- `wait` 时序
- `applescript` Cmd+W 关闭

#### 3.4 增加 ax_press 选择指南

```
### AXPress vs Click Selection:
- Use "ax_press" for Electron dialogs, buttons that don't respond to mouse events
- Use "click" + "element_name" for OCR-visible elements
- Use "cgclick" for native macOS controls with known coordinates
```

### Phase 4：验证层 — Dry-run 结构验证

#### 4.1 在 synthesis API 中增加 dry-run

当前只验证 YAML 结构：

```python
# synthesis.py 当前
steps = macro_from_yaml(macro_script)
MacroScript(steps=steps)  # 只验证结构
```

增加 dry-run 执行（非真执行，只检查资源可用性）：

```python
# 新增 dry-run 验证
from app.core.learning.macro.utils import verify_macro_script
result = await verify_macro_script(
    macro_script=macro_script,
    thread_id=f"dryrun_{session_id}",
    params={"is_dry_run": True},
)
```

#### 4.2 增加 element_name 可用性检查

在 dry-run 阶段，尝试解析宏中所有 `element_name` 是否能在当前桌面上找到：

```python
for step in steps:
    if step.payload.get("element_name"):
        resolved = await DesktopElementMixin._resolve_element(
            step.payload["element_name"]
        )
        if isinstance(resolved, str):  # error
            verification["warnings"].append(
                f"Element '{step.payload['element_name']}' not resolvable"
            )
```

---

## 3. 实施优先级与工作量估算

| Phase | 任务 | 工作量 | 影响 | 优先级 |
|-------|------|--------|------|--------|
| 1.1 | OCR 反向解析注入 | 2h | 🔴 核心 | P0 |
| 1.2 | key_press 捕获补全 | 4h | 🔴 核心 | P0 |
| 1.3 | key_name 死列修复 | 30min | 🟡 数据一致性 | P1 |
| 2.1 | ALLOWED_UI_ACTIONS 扩展 | 15min | 🔴 编译正确性 | P0 |
| 2.2 | 桌面宏编译路径 | 3h | 🔴 核心 | P0 |
| 2.3 | wait 时序插入 | 1h | 🟡 稳定性 | P1 |
| 2.4 | key_press → appleScript 合并 | 2h | 🟡 简化 | P2 |
| 3.1-3.4 | Prompt 模板更新 | 2h | 🔴 LLM 产出质量 | P0 |
| 4.1-4.2 | Dry-run 验证 | 2h | 🟢 防御性 | P2 |

**P0 合计约 11.5h**（1.5 天），即可让"录制 → 编译 → 合成"链路产出可执行的桌面宏。

---

## 4. 测试策略

### 4.1 单元测试

- `_resolve_element_at_point`: 给定已知坐标，断言返回正确元素名
- `_compile_desktop_click`: element_name 优先 vs 坐标兜底
- `wait` 插入：构造带时间戳的 event 序列，断言 wait 步骤生成

### 4.2 集成测试

1. **录制 → 编译 → 回放**: 录制"预定会议"操作 → 编译出宏 → 执行回放 → 断言剪贴板非空
2. **key_press 捕获**: 录制期间按 Cmd+V → 断言 TraceEvent 有 key_press 记录
3. **optional 处理**: 编译带 `optional: true` 的宏 → 元素不存在时跳过不报错

### 4.3 端到端验证

使用宏 383 的完整流程（"预定会议 → 复制全部信息 → 关闭"）作为基准：
- 录制用户手动完成此流程的操作
- 编译出的宏直接执行
- 断言：剪贴板包含会议邀请信息

---

## 5. 风险与注意事项

1. **OCR 反向解析延迟**：`_resolve_element_at_point` 每次调用需截屏 + OCR（~500ms）。录制期间高频调用可能影响体验。建议：只在 `mouse_click` 事件时解析（非 mouse_move），或加缓存（同一位置 500ms 内不重复解析）。

2. **rdev 键盘权限**：macOS 辅助功能权限需用户手动授权。前端应在首次录制时检查权限状态并提示。

3. **多窗口场景**：当前 `get_current_app()` 只返回 frontmost 窗口，但录制可能跨窗口（如从主窗口切到对话框）。`_resolve_element_at_point` 需要遍历当前应用的所有窗口。

4. **key_press → appleScript 合并的边界**：不是所有 key_press 都应该合并。独立的 Tab 键和粘贴操作（Cmd+A + Cmd+V）应该保留为独立的 `key_press` 步骤，只在连续的文本输入时才合并。