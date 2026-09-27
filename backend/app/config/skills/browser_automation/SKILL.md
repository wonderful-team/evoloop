---
name: Browser Automation SOP
description: |
  Playwright 持久化浏览器（browser 工具）的完整动作目录与操作规程：导航/交互/读取/感知/批量/
  高级/生命周期七组动作的逐个语义、selector-text-坐标三级定位优先级、wait_for/network_wait
  等待模式、cookies/localStorage 预登录会话、run_js 返回值约束、batch 动作列表写法、
  upload/dialog 处理。需要在网页内做 DOM 交互、内容提取或状态管理前加载本技能。
namespace: system
trigger_patterns:
  - "浏览器自动化"
  - "网页操作"
  - "browser 怎么用"
  - "在网页上点击"
  - "爬取页面"
  - "网页登录"
parameters: []
---

# 🌐 浏览器自动化操作规程（browser 工具）

`browser` 通过 Playwright 控制一个**持久化** Chromium（跨调用保留登录态/标签页）。与
`desktop`（OS 级）互补：网页内的精确 DOM 交互、内容提取、浏览器状态管理用 browser。

## 1. 动作全目录（按组）

**导航**
- `navigate`: 跳转 `url`，等待 networkidle。
- `back` / `forward`: 浏览器历史。`reload`: 刷新当前页。
- `get_url`: 返回当前 URL + 页面标题。
- `new_tab`: 打开新标签页（可选 `url`）并切换到它。
- `switch_tab`: 按 `tab_index`（从 0 开始）切换活动标签页。

**交互**
- `click`: 点击 `selector` 或 `text`；都无定位时可回退 (x, y)。
- `double_click`: 双击 `selector`/`text`。
- `hover`: 悬停（显示 tooltip/下拉）。
- `type_text`: 向 `selector`/`text` 输入 `value`；`clear_first=False` 可追加。
- `select_option`: 按 `value` 或可见 `text` 选 `<select>` 项。
- `key_press`: 键盘快捷键，如 `Enter`、`Control+a`、`Tab`。
- `scroll`: 沿 `direction` 滚 `amount` 像素（页面或 `selector` 元素内）。
- `drag_drop`: `source_selector` → `target_selector`。

**读取**
- `get_text`: 页面或 `selector` 的可见文本。
- `get_html`: 页面或 `selector` 的 outerHTML。
- `get_attribute`: `selector` 的 `attribute` 属性值。
- `get_links`: 所有 href 链接（可限定在 `selector` 内）。

**感知**
- `screenshot`: 截图（`full_page=True` 整页滚动）；`ocr=True` 立即跑 OCR 返回
  图片路径 + 文本/坐标（与 desktop 同格式，坐标可直接回填 click）。
- `wait_for`: 等 `selector`/`text`/`url_pattern` 满足 `state`
  （visible/hidden/attached/detached，默认 visible），`timeout_ms` 默认 15000。
- `check_element`: `selector` 的可见/勾选/启用状态。

**批量与文件**
- `batch`: 顺序执行 `actions` 列表（每项为 browser 动作 dict）；`continue_on_error`
  （默认 True）、`delay_ms`（默认 100）。适用于**已知的稳定序列**；页面状态未知时逐步调用。
- `upload`: 上传本地文件 `file_path` 到文件输入元素。

**高级**
- `run_js`: 页面上下文执行 `script`，返回 JSON 可序列化结果（不可序列化时失败）。
- `get_cookies` / `set_cookies`: 列 cookie / 注入 `cookies` 列表（预登录会话）。
- `local_storage`: `storage_action`=get/set/clear，配 `storage_key`/`value`。
- `network_wait`: 等待匹配 `url_pattern` 的网络请求完成（异步数据加载场景）。
- `dialog_handle`: `dialog_action`=accept/dismiss 处理下一个 alert/confirm/prompt，
  prompt 可带 `dialog_text`。

**生命周期**
- `close`: 优雅关闭浏览器（会丢运行时状态；持久化 profile 保留）。

## 2. 定位优先级

`selector`（CSS / XPath `//` 前缀 / Playwright locator 字符串）> `text`（可见文本）> 坐标
(x, y)。动态页面先 `wait_for` 再交互；点击后内容变化用 `get_text`/`screenshot` 验证。

## 3. 典型流程

1. `navigate` → `wait_for`(关键元素) → 交互 → 读取验证。
2. 登录复用：`set_cookies` 预注入 或 一次人工登录后持久 profile 自动带走。
3. 列表采集：`get_links`/`get_text` 批量取；需要执行 JS 聚合时用 `run_js`。
4. 已知稳定序列合入一个 `batch`（如 填表：点输入→输入→Tab→输入→提交）。
