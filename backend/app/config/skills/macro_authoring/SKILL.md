---
name: Macro Authoring Guide
description: |
  Evoloop 平台"宏机制"的自我知识库。宏是确定性的 UI 步骤回放脚本，覆盖浏览器(web)、桌面端、
  移动端三端。需要"把可重复操作封装成宏""手写宏脚本""在三端里做页面/端内采集、翻页、数据落盘"、
  或宏脚本被 macro create/update 拒绝要排查格式时，加载本技能。本技能提供一套对任意新界面通用的
  写宏方法论（探索→数据打样→编排→提交→实跑自检，详见 §8），并补全了工具说明缺失的端内细节：
  桌面 AX/OCR 动作、移动端 tap 坐标与 content-desc、collect_loop 双阶段采集、bash 收尾、run_js 的
  require_success/expect 断言等，附三端各一个范例（含真机验证与 DSL 模板两种可信度标注）。
namespace: system
trigger_patterns:
  - "怎么写宏"
  - "帮我写个宏"
  - "创建宏脚本"
  - "手写宏"
  - "宏怎么用"
  - "宏机制"
  - "宏格式"
  - "网页宏"
  - "桌面自动化宏"
  - "移动端采集宏"
  - "collect_loop"
  - "宏里跑 bash"
parameters: []
---

# 🎯 宏机制自我知识（Macro Authoring Guide，三端全覆盖）

你是 Evoloop 平台的助手。这份技能告诉你**平台自身的宏是怎么写的**，覆盖浏览器(DOM)、桌面(DESKTOP)、
移动端(MOBILE)三个动作源，让你在不读平台源码的前提下写出能通过 `macro create` 风险门与真实执行验证的宏。

## 1. 什么是宏 & 什么时候用

宏 = 一段确定性的 UI 步骤脚本（YAML / step dict 列表），由 `MacroEngine` 逐步骤回放：
- 适合：可重复的固定操作（打开 App→进页面→点按钮→等待→收集→落盘）。
- 不适合：需要即兴推理/随机应变的活——那种直接用你的交互工具现做，不要硬塞进宏。

创建：用统一入口 `macro create`（React 主 Agent 的工具面只有 `macro` 这一把，
`create_macro`/`run_macro` 独立工具已删除并入了它）。两种模式：
- **Script 模式**（传 `script_steps` + 必带 `rationale`）：你手写步骤 dict 列表。管线 =
  解析 → 规范化(cleanup_macro_steps) → 风险门(scan_step_families) → **真实执行验证**
  (MacroService.run：会真的打开页面/点击/采集，仅限滚动深度 max_scrolls=2) → 计算 risk_tier。
  验证通过后会自动 `confirm_macro` 提升为 verified+active——**succeed 即 active，`macro list` 立即可见**。
  ⚠️ 验证是**真执行**：`macro create` 提交含 navigate/click/tap 的脚本时，环境会被真实操作（不是模拟）。
- **Trace 模式**（不传 `script_steps`，只给 name/description/trigger_patterns）：把本会话刚完成的
  真实 UI 操作编译成宏。⛔ 前置条件苛刻，不满足直接返回"no macro was created"：
  1. `AUTO_MACRO_CREATION_ENABLED` 配置开启；
  2. 会话对应 `AgentActivity.final_outcome=="COMPLETED"` **且** `macro_creation_eligible=True`；
  3. 线程里有 ≥1 个可回放事件（compiler 能产出步骤）。
  所以**只有当会话是真做完了一串 UI 操作、且被标记 eligible 时**，Trace 模式才可用；
  没把握时用 Script 模式更可控。

 修复：`macro update macro_id=..`。改 `macro_script` 必须给 `rationale`；管线与 create
 相同（风险门 + **真实执行验证**），但会先 `downgrade_macro` 退回 pending_review、验证通过后
 再 `confirm_macro` 重新激活——**失败时宏停留在未激活状态，不会残留活动中**。
 模板：`macro read name/macro_id`（返回完整元数据 + 完整 YAML 脚本）——**写相似宏前先 read 一个
 同域已 verified 宏做模板**（工具 description 只给 MacroStep 核心格式摘要，本技能第二节的完整枚举以引擎为准）。

调试：`macro debug(script_steps=...)` 或 `macro debug(macro_script=<YAML 字符串>)`——**不落库**，
走风险门后完整执行一遍，返回逐步成败 + 提取数据。适合：
- 写宏前验证 DSL 写法对不对（如某 event_type 的 payload 字段名）；
- 定位脚本哪一步失败（未生效步骤明细）；
- 反复调参快速迭代，不必每次 create→run→delete 折腾。
**推荐流程：debug 跑通 → 再 create 落库**。

## 2. DSL 公共契约（照此写必过校验）

`MacroStep` 字段（`app/core/learning/macro/schemas.py`）：
- `step_number`: **必须是整数**（`5.1` 会校验失败），重复会报错；可不写，引擎会自动归一化。
- `type`: `action | extract | control | dump | if | loop | native | bash`
- `source`: `DOM`(web) | `DESKTOP` | `MOBILE` | `GLOBAL`（不写默认 DOM）——**三端都靠它分派执行器**。
- `event_type`: 见 §3-6 各端动作清单。
- `payload`: dict，保留你写的所有键；引擎用自己的默认值兜底。
- `target_selector`: 元素定位（各端语义不同，见下）。
- `extract` 必须带 `extract_type` + `key`。
- `if`/`loop`: `condition` + `then_steps`/`else_steps`/`steps` + `max_iterations`；loop 还有 `collect_mode`。

条件类型（loop/if 共用）：`element_exists | element_visible | text_contains`，配 `target_selector`；
另有 `has_more_items | pagination_exists`（恒真，配翻页检测用）。

**变量**：
- `{{param}}` / `{{parameters.param}}`：字面注入，支持 `{{a.b}}` 嵌套取值；**不支持 Jinja 过滤器**（会原样残留）。
- `{{base_url}}`：项目部署基地址，`MacroEngine.run` 自动注入（仅当项目配了部署 URL）。
- 循环注入：`{{item}}`、`{{batch_index}}`、`{{loop_index}}`、`{{collected_signature}}`。
- `{{device_id}}`：真机设备 ID（移动端宏必备）。
- **extract/bash 步骤的输出会并入参数**（显式 caller 参数优先），下游步骤可用 `{{key}}` 引用。

**重试**：action 步骤的 `payload.retry`（次数）+ `payload.retry_interval_ms`（毫秒），失败自动重试。

## 3. 浏览器（source: DOM）

选择器：`payload.selector`（dict：`{"type": "css"|"xpath"|"text", "value": "..."}`）或顶层 `target_selector`。

```yaml
- type: action
  source: dom
  event_type: navigate
  payload:
    url: '{{base_url}}/shop.html#url=shop/goods/lists'   # 必须绝对地址或用 {{base_url}}
- type: action
  source: dom
  event_type: click
  payload:
    selector: {type: css, value: '.layui-laypage-next:not(.layui-disabled)'}
- type: action
  source: dom
  event_type: click
  payload: {selector: {type: text, value: '提交'}}
- type: action
  source: dom
  event_type: input
  payload: {selector: {type: css, value: '#search-input'}, value: '{{keyword}}', clear_first: true}
- type: action
  source: dom
  event_type: wait
  payload: {seconds: 2}
- type: action
  source: dom
  event_type: wait_for
  payload: {selector: {type: css, value: '.row'}, state: visible, timeout_ms: 8000}
```

浏览器动作全集（均支持 `timeout_ms`/`continue_on_error`）：
`navigate`(绝对url/`{{base_url}}`)、`back`/`forward`/`reload`、`click`/`tap`/`double_click`/`hover`、
`input`/`type_text`(text+clear_first)、`select_option`(value)、`key_press`(key)、`scroll`(direction,amount)、
`drag_drop`(source_selector,target_selector)、`upload`(file_path)、`new_tab`(url)、`switch_tab`(tab_index)、
`dialog_handle`(dialog_action)、`screenshot`(full_page)、`detect_pagination`、`scroll_to_bottom`。

**三次保障（web 独有）**：
- `payload.pre_wait`：`{selector, state: visible, timeout_ms}` —— 操作前等元素就绪。
- `payload.post_verify`：`{url_pattern, selector}` —— 动作后校验跳转/元素出现，不满足即失败。
- `payload.retry: N` + `payload.retry_interval: 毫秒`：步骤失败自动重试。

**run_js**（多数页面状态靠它拿）：
- 写法必须 `() => {...}` 返回 JSON 可序列化值。
- 支持 `require_success: true`（返回 false/null/undefined → 步骤判失败）。
- 支持 **VERIFY 断言**：脚本返回 `VERIFY:<实际状态>` 且步骤声明 `expect: "状态A|状态B"` 时，不匹配即失败——解决"提交了但没生效"。
- **run_js 当 ACTION 属于 escape 风险族**；放进 EXTRACT 步骤读页面状态则是 observe。

**web 分页/列表采集**（没有桌面端那样的 collect_loop，用普通 loop 自己做）：
```yaml
- type: loop
  source: dom
  condition:
    type: element_exists
    target_selector: '.layui-laypage-next:not(.layui-disabled)'
  steps:
    - type: extract
      source: dom
      extract_type: run_js
      key: page_count
      payload:
        script: '() => JSON.stringify({ n: document.querySelectorAll(".row").length })'
    - type: action
      source: dom
      event_type: click
      payload: {selector: {type: css, value: '.layui-laypage-next'}}
  max_iterations: 5
```

## 4. 桌面端（source: DESKTOP）

桌面通过 AX（辅助功能树）/ OCR / AppleScript 驱动，元素定位用 **AX name 包含匹配**的字符串。

```yaml
- type: action
  source: desktop
  event_type: open_app
  payload: {app_name: 'WeChat'}                # 或 bundle_id + focus: false 走无焦点启动
- type: action
  source: desktop
  event_type: click
  payload: {element_name: '发送'}               # AX name 包含匹配；或给 x/y 坐标
- type: action
  source: desktop
  event_type: click
  payload: {element_name: '弹窗关闭', optional: true}   # optional: 找不到就跳过，不中断宏
- type: action
  source: desktop
  event_type: type_text
  payload: {text: '{{keyword}}', force_keystroke: true}
- type: action
  source: desktop
  event_type: scroll
  payload: {direction: down, amount: 300}
- type: action
  source: desktop
  event_type: key_press
  payload: {key: 'enter'}
```

桌面动作全集：`open_app`(app_name / bundle_id+focus:false)、`click`/`tap`(element_name 或 x,y，`optional: true` 可跳过)、
`type_text`(text/force_keystroke)、`key_press`(key)、`scroll`(direction,amount)、`drag_drop`(source_element,target_element,x/y…)、
`applescript`/`native`（System Events 脚本，escape 风险族）、`ax_press`/`ax_menu_press`/`ax_set_value`（AX 原生原语）、`get_active_app`。

**桌面条件判定**：`element_exists/visible/text_contains` 会执行
`tell application "System Events" to exists (first UI element whose name contains "<target_selector>")`
——所以 **target_selector 是 AX name 子串**。

**桌面 OCR 取文本**（读不出 AX 名时）：extract `gui_extract`，用相对坐标点取字。

```yaml
- type: extract
  source: desktop
  extract_type: gui_extract
  key: point_text
  payload: {relative_position: {x: 0.5, y: 0.3}}
```

## 5. 移动端（source: MOBILE）

真机经 adb 驱动。关键认知：**Android 列表的信息大多在节点 `content-desc` 而非 `text`**；
很多元素没有稳定 name，`tap` 用**屏幕坐标**最可靠（坐标取 node bounds 中心）。

**⚠️ 探索必须用 `mobile(action=dump_ui)` 工具，不要用裸 adb `uiautomator dump`。**
引擎的 `mobile` 工具走 `adb_driver.dump_ui`：**优先 uiautomator2 机制**（AccessibilityService），
只有它失败才回退 native `uiautomator dump`。部分 App（尤其防自动化/Flutter 混合的）会
**屏蔽 native `uiautomator dump`**（命令静默失败、无产物），但 uiautomator2 仍可读——所以：
- 探索时**一律调 `mobile(action=dump_ui)`** 拿 XML，裸 adb dump 失败不代表读不到 UI；
- 若 `mobile` 的 dump_ui 也不通，才考虑截图 + `media(action="analyze")` / OCR 兜底（但那是最后手段，
  能 dump 就 dump，视觉方案慢且结构信息少）；
- collect_loop 内部逐屏 dump 也是同一 uiautomator2 路径，只要 `mobile` 能 dump，采集就能跑。

**锚点选择（列表采集通用原则）**：锚点要选**单个节点就能完整命中正则的稳定文本**——
比如"发布时间/编号/状态"这类带明确模式的字段。避免选会被拆成多个节点、或跨卡重复的字段
（如价格可能拆成 `¥` 和数字两个节点、或与相邻卡片文本混在一起）——那样的锚点/特征会漏采
或带噪音。优先"每卡唯一、单节点完整"的字段做锚点，价格等拆分字段放解析阶段合并。

```yaml
- type: action
  source: mobile
  event_type: open_app
  payload: {package_name: com.netease.cbg}      # 也认 package/app_name/text；默认 force_stop
- type: action
  source: mobile
  event_type: tap
  payload: {x: 335, y: 748}                      # 坐标优先；也支持 element_name
- type: action
  source: mobile
  event_type: wait
  payload: {seconds: 4}
- type: action
  source: mobile
  event_type: scroll
  payload: {direction: down, scroll_amount: medium}
- type: action
  source: mobile
  event_type: back_key
  payload: {keycode: back}
- type: extract
  source: mobile
  extract_type: dump_ui
  key: ui_xml                                 # 导出当前 UI XML（调试/找锚点用）
```

**移动端条件判定**：`element_exists/visible/text_contains` 都是先 `dump_ui` 再把 `target_selector` 当**子串**匹配——
所以直接写能看到的关键字（如 `总修:`），不是 CSS。

**`tap` 无稳定元素时的兜底范式**：底部 Tab 之类没有 name 的，先 `dump_ui` 拿到 bounds，
`tap {x: bounds中心}`，再 `wait` 2~4s。

## 6. 采集核心：collect_loop（LIST → DETAIL 双阶段）⚠ mobile 专属

**scan-and-collect 不要自己写 scroll→dump→匹配**，用引擎内置 `collect_loop`：每屏自动 `dump_ui` →
按正则锚点提取 → signature 去重 → 自动下滑 → 换屏，并支持断点续抓（`state_file`）。

```yaml
- type: loop
  source: mobile
  collect_mode: list                 # list | detail | auto（mobile 专属）
  max_iterations: 12
  payload:
    state_file: /tmp/cbg_collect.json
    list_config:
      max_screens: 12
      swipe_distance: 1200
      wait_after_swipe_ms: 1500
      anchor_element: {type: price, pattern: '￥[0-9,.]+'}   # 锚点正则：匹配 node text 或 content-desc
      feature_region: {offset_y: -200, height: 200, max_features: 4}
```

- 候选结构：`{text, bounds, anchor_y, tap_x, tap_y, signature, features, content_desc, status, collected_at, screen_num}`。
- `signature` = 去空白 text 前 100 字符，用于**去重**；列表卡片文本一变即算新条目。
- **LIST 模式**：结果写 `extracted_data["collected_items"]` + `collect_state_file`，loop 结束（不执行 `steps`）。
- **DETAIL 模式**：自动按 `tap_x/tap_y` 点进每条 → 执行 `steps`（注入 `{{item}}`）→ `press_key back` 返回 →
  `detail_config.data_capture`（`目标字段: extract_key`）把详情页值写回条目；结果在 `extracted_data["collect_results"]`。
- **`auto` = 先 LIST 再 DETAIL。增量天然支持**：`state_file` 已有 signature 不会再入库——适合"每天只收新上架"。

**移动列表解析陷阱**（真机验证）：
- 价格 `￥1,272` 有千分位逗号：对原始 `text` 做 `￥([0-9,]+(?:\.\d+)?)`，**别先按逗号 split**。
- 卡片判定：锚点只给价格会误收装备/物品卡，要再加业务特征（如都含 `级` 才当角色）。
- 服务器/地区可能被截断（如只剩 `长安城`），解析留 fallback。
- **价格可能被拆成两个节点**（`¥` 和数字分开）：锚点别用价格，用"每卡唯一、单节点完整"的字段
  （发布时间/编号等）；价格在解析阶段做 `¥` + 相邻数字节点合并。
- **双列/多列瀑布流 + `feature_region` 过大**会把相邻卡片的文本也带进 features：`max_features`
  设小一点，或解析时按锚点坐标过滤（同列、锚点上下限内）。features 有噪音不代表采集失败，
  是解析要按坐标/模式过滤。
- **防自动化 / Flutter 混合 App**：native `uiautomator dump` 可能被屏蔽，但 `mobile(action=dump_ui)`
  的 uiautomator2 路径通常仍可读（见 §5）。滚动/跳页可能把界面切到 Flutter 层，`dumpsys window`
  的 focus 会变，但 dump_ui 仍能采——不要因一次 dump 失败就放弃，重试或稍等再 dump。

## 7. bash 步骤：数据加工收尾（三端通用）

`payload`：`{command, key(默认 bash_output), timeout(默认30s), continue_on_error(默认false)}`。
stdout 捕获进 `extracted_data[key]`，并并入参数，后续 `{{key}}` 可引用；`macro run` 返回里可见。

⚠️ **风险边界**：`DEFAULT_ALLOWED_FAMILIES` 当前临时放行了 escape 族（含 bash），所以 bash 能过风险门；
但**整体 risk 升为 escape → 该宏被标记 `requires_confirmation=true`，每次执行要人工确认**。因此：
- bash 只用来做**只读的本地 JSON 数据加工**（解析候选、去重、按日期分区写 JSONL），不要做危险副作用。
- 不想每次被确认，就把加工逻辑放 DETAIL/loop 的 extract（run_js/get_text），bash 只做最终落盘。
- `macro create/macro update` 的工具 DESCRIPTION 里"禁止 bash/native/run_js ACTION"是收紧前的旧措辞，风险门现在放行 escape 族，以本技能为准。

## 8. 写宏的标准工作流（对任意新界面通用）

**铁律：宏 = 把"真机/真页面验证过的确定性操作"固化下来，不是凭空编步骤。顺序永远是
探索 → 打样 → 编排 → 提交 → 实跑自检。** 这套流程对 web / 桌面 / 移动任意一端、任意目标
界面都适用——不管目标是电商列表、后台表格、聊天窗口还是 App 采集页。探索与打样用你的交互
工具（`mobile`/`desktop`/`browser`/`media`）直接在目标上做，不靠猜。
**闭环终点 = 宏创建并激活 + 实跑验证通过。** 中途写 YAML 文件、给用户"你自己提交"的指引，
都只是半成品——**"完成"的定义是：`macro create` 成功落库激活，且 `macro run` 验证数据真实采到。**

**文件与工作目录**：所有打样脚本、解析器、state_file、产物一律放在**当前项目工作目录**下
（建议 `./.tmp/`、`./scripts/`、`./data/` 子目录），**禁止写 /tmp/**——沙箱只允许工作目录，
写 /tmp 会被拒绝或违反安全边界。宏 bash 步骤的 command 也引用工作目录内的脚本（写绝对路径
时用工作目录，不要写 `/tmp/xxx.py`）。

### 阶段 0 · 先读模板
`macro list` → `macro read <名字/id>` 找一个同域（web/桌面/移动）已 verified 宏，记下骨架与参数；
examples/ 里的完整范例可 `read` 直接照抄。**注意范例可信度标注**（见 §9）：只有真机验证过的才能
直接照抄参数；标注"模板"的要看懂结构后按你的目标重新打样。

### 阶段 A · 探索目标（产出一张"界面蓝图"）
用交互工具摸清目标，必须产出 4 样，写宏时直接引用：
1. **进入路径**：怎么到达目标页/界面——web 的 URL（`navigate`/`{{base_url}}`）、桌面/移动的
   `open_app` 冷启动方式、初始 `wait` 几秒、有没有首启弹窗/登录页要先处理。
2. **元素定位**：
   - web：`payload.selector`（css/text/xpath）、可点击按钮、`run_js` 取数脚本。
   - 桌面：AX `element_name` 子串、OCR 光标点（`gui_extract` relative_position）。
   - 移动：先 `mobile(action=dump_ui)` 拿 XML——看节点是 `text` 还是 `content-desc` 有内容、
     `bounds` 多少；**无稳定 name 的元素记下 `bounds` 中心坐标给 `tap` 用**。
     ⚠️ **必须用 `mobile` 工具，禁止用 bash 跑 `adb shell uiautomator dump`**（那是被屏蔽的
     native 路径，会失败/抓错 App）；mobile 工具的 dump_ui 走 uiautomator2，能绕过屏蔽。
   - 通用兜底：任何一端都准备 OCR/截图做二次确认，不猜（但先试 dump_ui，视觉是最后手段）。
3. **特征关键字**：能判定"已进入目标页 / 已见目标卡"的可见子串——用于 if 兜底和业务过滤。
4. **锚点正则**：列表/卡片上可正则命中的文本特征（如价格、编号、名称模式）。

探索工具速查：
- `mobile`：`dump_ui`（UI XML）、`screenshot`、`gui_extract`（OCR 取字）、`tap/swipe/scroll/input_text`、
  `open_app`、`pull`（把设备数据拉到本地打样）。
- `desktop`：`dump_ui`（AX 树）、`open_app`、`click/type_text`、`gui_extract`。
- `browser`：`navigate/click/run_js`。
- `media(action="analyze", kind="image", source=<截图路径>, question=...)`：看截图布局、识别按钮/弹窗/坐标区。

### 阶段 B · 数据打样（写宏前先证明"数据可解析"）⚠️ 最容易跳过、也最容易翻车的一步
目标：在写宏脚本**之前**，用一小份**真实样本**证明采集逻辑成立，避免宏写完才发现锚点/解析不对。
这一阶段与具体业务无关，对任何"列表采集 + 结构化落盘"类宏都是必须的：
1. 抓真实样本：移动端 `mobile(action=dump_ui)` 或 `mobile(action=pull)` 拉 XML/截图；web `run_js`
   取一屏 DOM；桌面 `dump_ui`。
2. 本地写个临时解析脚本（如 `/tmp/xxx_process.py`）把样本跑通：锚点正则命中、卡片过滤正确
   （用目标自己的特征字段判定，如 `级`+`￥` 或订单号+金额）、字段拆对、去重键稳定。
3. **打样通过 → 才把这段逻辑搬进宏**（collect_loop 的 `anchor_element` / bash 步骤的 `command`）。
   打样用的临时脚本就是宏里 bash 步骤的 command 本体（或已验证的版本）。
4. 打样不过就改思路，**不要带着未验证的解析去写宏**。

### 阶段 C · 编排（通用骨架，套用即可）
冷启动/开页 → 进目标 → 兜底 IF（用阶段 A 的特征关键字）→ 采集（web 用 loop+条件，
移动用 collect_loop，桌面无内置列表采集则 loop+extract）→ bash 只读数据加工落盘。
骨架是固定的，变的是阶段 A/B 摸出来的具体 selector / 坐标 / 正则。
**编排产物直接组织成 `script_steps`（dict 列表）**，不要为了"写文件"先转 YAML 再转回来——create
要的是 dict 列表，直接按这个形态构造步骤即可（想留档可 create 成功后把同样内容落 YAML 备份）。

### 阶段 D · 提交（⚠️ 必须由你执行，不要停在"写好文件"）
**宏创建是闭环的终点：必须亲自调用 `macro create` 让宏落库并激活。** 把脚本写成本地 YAML
文件只是中间产物/备份，**不是交付**——交付出的是"已创建并激活的宏"。流程：
0. **先 debug 再 create（强烈推荐）**：正式 create 前先用 `macro debug(script_steps=...)`
   跑通脚本——它能不落库执行并返回逐步成败，DSL 写法、失败步骤当场暴露，避免 create 反复失败。
1. 把你要的脚本转成 `script_steps`（dict 列表，每个元素一个步骤，字段同 §2 DSL：`type/source/
   event_type/payload/condition/...`；不要传 YAML 字符串，要传结构化 dict 列表）。
2. 调用 `macro create(name=..., description=..., trigger_patterns=..., script_steps=..., rationale=...)`。
   ⚠️ **`trigger_patterns` 必填**（不能留空）：这是"以后一句话触发宏"的入口。按用户原话 + 你的
   自然概括写 2~3 个触发词，如 ["抓藏宝阁新角色", "抓取藏宝阁新上架角色", "藏宝阁新上架"]。
   触发词空 = 宏无法被一句话复用，等于废宏。若确实不清楚触发词，先 `question` 问用户，不要空着。
3. 看返回：`创建成功` + `risk_tier` + `requires_confirmation`。**创建即已通过真实执行验证并激活**，
   `macro list` 立即可见——如果宏还没出现在列表里，说明没创建成功，继续处理错误而不是就此收尾。
4. 想写文件留档可以，但顺序是**先 create 成功，再落盘备份**，不是反过来。

管线会**真实执行**验证（真的开页/点击/采集，仅限滚动深度）。通过即 activated。
⛔ 想走 Trace 模式（设备真操作完再 create）时，确认会话满足：COMPLETED + macro_creation_eligible +
可回放事件；否则会返回 "no macro was created"。**没把握就用 Script 模式更可控。**

### 阶段 E · 实跑自检（⚠️ 也是必须步骤）
宏创建并激活后，**必须亲自 `macro run(name=...)` 跑一次验证闭环**，不要停在"已创建"。
返回有**逐步骤成败**（step_log）+ `提取数据`——**别只看"执行完成"**，要验证数据真采到了
（如 bash 步骤的 `cbg_report` 里 batch=N 是新增条数）。⚠️ 宏带 `requires_confirmation`
（risk 含 money/escape）时会挂起等运营确认：发起后不要重复发起，等确认完成后 resume 继续。
docker 模式自动放行。

### 阶段 F · 修复
失败步骤 → 改脚本 → `macro update(macro_id=.., macro_script=.., rationale='修复...')`
→ 先退回 pending_review，验证（真实执行）通过后重新激活；失败则保持未激活，如实告诉用户。

### 真实示范（CBG 藏宝阁角色采集，方法论的一次落地）
这套流程在 `examples/mobile_cbg_roles_collect.yaml` 完整落地过，真机验证 175 条入库、二次运行
0 新增。它示范的是**怎么把通用流程套到具体目标**：`dump_ui` 拿首页 XML 发现底部 Tab 无 name →
tap 用坐标 `(335,748)`；OCR 详情页确认字段结构；写解析脚本把 collect 样本跑通（锚点正则、
卡片过滤、增量去重）→ 才写宏。读这份范例时看的是"流程怎么走"，不是抄它的业务参数。

## 9. 三端完整范例（examples/ 可独立 read 照抄）

完整脚本抽在 `examples/` 目录，经 `skill` 加载后会出现在 `<skill_files>` 里，用 `read` 工具直接打开。
**可信度标注（务必先看）**：
- ✅ **真机验证**：脚本在真实设备/页面完整执行过、数据真实采到，参数可直接复用。
- 📄 **DSL 模板**：按 DSL 规格编写、结构正确，但**未在真实环境执行过**——selector/坐标/字段
  需按 §8 阶段 A/B 在你的目标上重新打样后使用，**不要直接照抄参数**。

| 范例 | 端 | 形态 | 可信度 |
|---|---|---|---|
| `examples/web_orders_collect.yaml` | web(DOM) | 后台订单翻页采集：`{{base_url}}` 导航 + `wait_for` + loop(`element_exists` 下一页) + EXTRACT-run_js 取数 + bash 落盘 | 📄 DSL 模板 |
| `examples/desktop_chat_submit.yaml` | 桌面 | 打开 App→搜索→提交：open_app / AX name 定位 / `type_text`+`key_press` / IF 判定 + `gui_extract` OCR 兜底 | 📄 DSL 模板 |
| `examples/mobile_cbg_roles_collect.yaml` | 移动 | 每日新上架采集：open_app → tap 坐标 → IF 兜底 → collect_loop(list) → bash 解析落盘 | ✅ 真机验证（175 条入库、二次运行 0 新增） |

移动端解析器要点（已真机验证）：`is_role` 判定含 `级` 且 `￥` 且（`成就:`/`总修:`/`总宠修:`）排除装备卡；
价格对原始 text 正则 `￥([0-9,]+(?:\.\d+)?)`；稳定键 `server|level|sect|achievement|total_cultivation|pet_cultivation|price_yuan`
写 `_keys.txt` 做增量去重；按 `_YYYYMMDD.jsonl` 日期分区追加；输出统计到 stdout 供 `macro run` 当报告。
读范例时重点是**结构与方法**（怎么编排、怎么兜底、怎么打样），参数要按你的目标重新探索。

## 10. 提交前自查清单

- [ ] `step_number` 全是整数（或无）。
- [ ] `extract` 有 `extract_type` + `key`。
- [ ] `navigate` 用了绝对 URL 或 `{{base_url}}`。
- [ ] web 用 `payload.selector` dict 或顶层 `target_selector`；桌面/移动的 `target_selector` 是 name/文本子串。
- [ ] 移动 `tap` 给了 `x/y`（不稳定元素别指望 name）；采集用 `collect_mode: list` 而非手写滚动。
- [ ] web 翻页用 loop + `element_exists` 条件；run_js 用它该用的 `require_success`/`expect`。
- [ ] bash 只做只读数据加工；明确接受"会被 requires_confirmation"的代价。
- [ ] 提交时给了 `rationale`。
- [ ] 跑完用返回的 step_log + extracted_data 验证数据真采到了，而不是只看"成功"。