---
name: Mobile Device SOP
description: |
  Android 设备自动化（mobile 工具，ADB + Reactor）的完整操作规程：为什么必须走本工具而非 bash
  裸 adb（uiautomator2 绕过 dump 屏蔽）、18 个动作逐个语义、intent_flow 高频批量格式、
  坐标绝对/相对 0.0-1.0 约定、scroll_amount 幅度档位、read_sms 智能轮询与 after_timestamp、
  push/pull 路径要求、dump_ui(UIAutomator XML) 与 gui_extract 定位取数。操作已连接安卓手机前
  加载本技能。
namespace: system
trigger_patterns:
  - "操作手机"
  - "安卓设备"
  - "mobile 怎么用"
  - "手机截图"
  - "手机上点击"
  - "读短信验证码"
parameters: []
---

# 📱 Android 设备操作规程（mobile 工具）

`mobile` 通过 ADB + 本地响应式循环（Reactor）控制已连接安卓设备。

## 1. 铁律：不要用 bash 跑裸 adb

- `dump_ui` 走 **uiautomator2**，能绕过很多 App 对 native `adb shell uiautomator dump` 的
  屏蔽（native 可能失败或抓到错误的 App）。
- 截图/tap/滚动都经过设备抽象，正确处理多设备 `device_id`。
- 一切设备交互都调本工具。

## 2. 动作全目录

- `screenshot`: 截屏，返回图片文件路径；`ocr=True` 提取文本；`region="x,y,w,h"`（逻辑点）
  裁剪用于定向 OCR 或验证。
- `tap`: 坐标 (x, y) 点按；`x, y, x2, y2` 可为绝对像素或相对 0.0-1.0。
- `click`: 语义点击。给 `element_name`/`target` 时走 **Reactor 本地轮询**（高频、带等待）。
- `long_press`: (x, y) 或 element_name 长按。
- `swipe`: (x, y) → (x2, y2)；`duration_ms` 默认 300。
- `scroll`: `direction` + `scroll_amount`：small(~30%) / medium(~50%) / large(~70%) /
  full(~90%)。
- `input_text`: 输入 `text`；给 `element_name` 时先点它聚焦。
- `press_key`: `keycode`=home/back/enter 等键名或键码。
- `dump_ui`: UI 层级 XML（定位元素坐标/文本的第一优先信息源）。
- `list_devices` / `get_info` / `list_apps`: 设备、信息、第三方包列表。
- `open_app`: 按包名打开 App（`text` 传包名）。
- `push` / `pull`: `local_path`（Mac 完整路径）↔ `remote_path`（设备完整路径）。
- `intent_flow`: 本地高频执行一系列 intent（见 §3）。
- `read_sms`: 智能延迟轮询短信。`text`=正则过滤，`timeout`=最大等待秒（默认 30），
  `after_timestamp`=Unix 毫秒时间戳只取更新的消息（过滤旧验证码、只监听新消息）。
  节奏：首次查询前等 3s，之后每 2-5s 轮询。
- `gui_extract`: OCR 从区域或 (x, y) 附近智能提取文本。

## 3. intent_flow（快路径）

对**已知稳定**的连续操作合入一次 intent_flow，减少回合数：
```json
[
  {"action": "click", "target": "Search"},
  {"action": "input", "target": "SearchBox", "text": "iPhone"}
]
```
`input` 动作给了 `target`/`element_name` 会先点该元素聚焦。界面状态未知（新页面/加载/弹窗）
时**不要**批量，逐步 click/dump_ui 验证后再走。

## 4. 典型探索循环

1. `screenshot` + `dump_ui` 确定当前界面；
2. 从 UI 树/OCR 拿元素 bounds → `tap`/`click`；
3. 翻页采集用 `scroll`（medium/large）+ 重复 dump；
4. `wait_after_ms` 可给单个动作加后置等待。

## 5. 参数速查

`element_name`/`target`=语义名（target 为跨工具别名）；`element_role`=角色/类过滤；
`text`=输入文本或包名；`device_id`=设备序列号；`ocr`=截图即 OCR；`timeout`=动作/轮询超时秒；
`intents`=intent_flow 列表；`region`=截图裁剪 "x,y,w,h"；`after_timestamp`=短信过滤起点。
