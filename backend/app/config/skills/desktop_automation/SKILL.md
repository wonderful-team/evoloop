---
name: Desktop Automation SOP
description: |
  macOS 桌面自动化（desktop 工具）的完整操作规程：速度三纪律（键盘优先/批量/少截图）、批量
  actions 的正确与错误用法、微信/Chrome/系统常用快捷键、截图 OCR 坐标回点工作流、region 局部
  截图语义、AppleScript 陷阱、AX 树（dump_ui/verify）过滤参数。操作桌面 App（微信、Chrome、
  访达、原生 App）或需要在桌面输入/点击/批量执行前加载本技能。
namespace: system
trigger_patterns:
  - "操作桌面"
  - "打开应用点击"
  - "微信发消息"
  - "桌面自动化"
  - "desktop 怎么用"
  - "批量动作"
parameters: []
---

# 🖥️ macOS 桌面自动化操作规程（desktop 工具）

`desktop` 工具经 Accessibility/剪贴板/合成事件控制 macOS。动作枚举与参数以工具 schema 为准；
本技能提供**怎么用好**的完整细节。

## 1. 速度三纪律（遵守这些能快 3 倍）

**规则 1：键盘优先**——始终优先键盘而非鼠标。
- 好：`key_press("cmd+w")` 关窗口；`key_press("return")` 发消息；`key_press("cmd+v")` 粘贴。
- 坏：点坐标，除非键盘做不到。

**规则 2：用批量模式**——多个动作合进一个 `batch`。
- 好：所有步骤都在**同一个输入框**；步骤间跳过验证，最后再验证。
- 坏：不要跨不同屏幕或加载状态批量。

**规则 3：跳过不必要的截图**——批量中只在开始和结束时截图；**不要**每个动作后都截图。

## 2. 常用快捷键（记牢）

- 微信：`return`（发送）、`cmd+f`（搜索）、`cmd+n`（新会话）
- Chrome：`cmd+l`（地址栏）、`cmd+t`（新标签）、`cmd+w`（关标签）
- 系统：`cmd+tab`（切换 App）、`cmd+space`（Spotlight）

## 3. batch 的 actions 写法

正确用例（适合批量）：
- 所有动作都针对**同一个输入框**
- 纯键盘序列：`[cmd+f -> 输入 -> 回车]`
- 已知工作流：`[点输入框 -> 输入 -> 回车发送]`

不要用批量（用单独调用 + 验证）：
- 会改变屏幕/状态的动作
- 需要等待加载的动作
- 跨不同窗口的动作

**示例 1 —— 微信发消息（好）**：
```json
[
  {"action": "click", "element_name": "输入框"},
  {"action": "type_text", "text": "Hello"},
  {"action": "key_press", "key": "return"}
]
```
结果：开始 1 张截图、结束 1 张。快！

**示例 2 —— Chrome 搜索（好）**：
```json
[
  {"action": "key_press", "key": "cmd+l"},
  {"action": "key_press", "key": "cmd+a"},
  {"action": "type_text", "text": "google.com"},
  {"action": "key_press", "key": "return"}
]
```
全是键盘，非常快，无需坐标！

**示例 3 —— 填表单（好）**：
```json
[
  {"action": "click", "element_name": "用户名"},
  {"action": "type_text", "text": "user@example.com"},
  {"action": "key_press", "key": "tab"},
  {"action": "type_text", "text": "password"},
  {"action": "key_press", "key": "return"}
]
```
5 个动作，1 个 batch，共 2 张截图。

**反例（坏）**——三次单独调用各配截图：
`desktop(click) -> screenshot -> verify -> desktop(type_text) -> screenshot -> ...`

batch 附加参数：`continue_on_error`（默认 True）、`delay_ms`（动作间毫秒，默认 300）。

## 4. 截图与定位工作流

- `screenshot(ocr=True)` 立即跑 OCR，返回**文本元素 + 屏幕坐标**，可直接回填 `click(x, y)`；
  局部截图的坐标也会自动换算为屏幕坐标。
- `region="x,y,w,h"` 局部截图（逻辑点）。不提供 region 时取决于 `ENABLE_PARTIAL_SCREENSHOT`
  配置：True（默认）自动截当前活动窗口；False 截全屏；无法确定窗口 bounds 时回退全屏。
  - 截指定窗口：先 `get_active_app` 拿 bounds 再传入。
- 优先 `element_name`/`target`（AX 语义名）定位，坐标是最后手段。
- `dump_ui` 读 AX 树（JSON 数组），支持 `role_filter`（如 `AXButton`）、`name_filter`（部分
  匹配）、`max_depth`（默认 10）；比截图快且确定。
- `gui_extract` 用 OCR 从区域或坐标 (x, y) 附近智能提取文本。
- 配套快速验证工具（如在你的工具面上）：`verify_ui_state`（AX 查元素/文本）、
  `quick_check_screen`（~500ms，无 LLM，代替 image analyze 的 ~12s）。

## 5. 输入与 App 控制

- `type_text`：默认走剪贴板粘贴（快）；`force_keystroke=True` 用慢速 AppleScript keystroke
  （个别拒绝粘贴的输入框才用）。
- `open_app`：按名称打开或聚焦应用；`list_apps` 列 /Applications；`get_info` 读系统硬件/OS；
  `get_active_app` 取当前聚焦 App 名/标题/窗口 bounds。
- `key_press`：`enter`、`tab`、`escape`、组合键 `command+a`、`shift+tab` 等。
- `click`/`double_click`：`element_name` 或 (x, y)；`element_role` 可加角色过滤。
- `drag_drop`：源/目标用元素名（`source_element`/`target_element`）或坐标 (x,y)→(x2,y2)，
  `duration_ms` 默认 500。
- `scroll`：`direction`（up/down/left/right）+ `amount` 像素（默认 300）。

## 6. AppleScript 边界（重要）

`applescript` 动作**不要**对动态 App（微信、Chrome、Electron 应用）使用——它们缺少健壮的
AppleScript 支持，会失败或误操作。对这类 App 一律用原生 `type_text`/`click`/`key_press`。
原始 `applescript` 仅用于确有字典支持的原生 App（如 Finder、System Events 查询）。

## 7. 参数速查

`x, y`=click 坐标；`element_name`/`target`=语义名；`element_role`=角色过滤；`text`=type_text
内容；`key`=按键/组合；`app_name`=open_app 目标；`script`=applescript 代码；`region`=截图裁剪；
`ocr`=截图即 OCR；`actions`/`continue_on_error`/`delay_ms`=batch；`direction`/`amount`=scroll；
`x2, y2, source_element, target_element, duration_ms`=drag_drop；
`role_filter, name_filter, max_depth`=dump_ui。
