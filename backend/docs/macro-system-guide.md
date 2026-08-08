# 宏系统完整指南

> 宏（Macro）是 evoloop 中的确定性自动化脚本系统，覆盖生成→存储→校验→执行→验证→进化→优化的全生命周期。

---

## 一、工作原理

### 1.1 什么是宏

宏是一段 **YAML 格式的确定性步骤脚本**，由 `MacroEngine` 逐步骤执行。与 LLM Agent 的"思考→行动"模式不同，宏按预设剧本精确执行，延迟低、可靠性高。

```
LLM Agent 路径:  感知 → 推理 → 决策 → 执行 → 验证  (灵活但慢)
宏路径 (L0):     命中 → 执行 → 返回              (快、稳)
```

### 1.2 执行流程

```
用户触发 (语音/文本)
    │
    ▼
L0 匹配器 (trigger_patterns 命中 或 embedding 匹配)
    │
    ▼
preflight() 门控检查
  ├── is_routable()         → 状态为 verified + is_active
  ├── 必需参数完整性检查     → parameters_schema 校验
  └── YAML 解析并缓存       → MacroScript.from_yaml()
    │
    ▼
run_deterministic() 执行
  ├── 策略门控: source / family / risk 三层过滤
  │
  ├── [快速路径] Engine.execute_steps()
  │     ├── 参数注入 {{param}}
  │     ├── 按 type 分发至:
  │     │   ├── ACTION   → _execute_browser / mobile / desktop_step()
  │     │   ├── EXTRACT  → handle_extraction()
  │     │   ├── IF       → evaluate_condition → 分支执行
  │     │   ├── LOOP     → _handle_collect_loop() / _handle_loop()
  │     │   ├── DUMP     → file / MCP / webhook
  │     │   ├── NATIVE   → subprocess (G5 门控)
  │     │   └── CONTROL  → 控制流分发
  │     └── 失败 → _debug_screenshot()
  │
  └── [自愈路径] 如失败且允许自愈:
        ├── MacroService.run() 重试
        └── 仍失败 → 发布事件 → Agentic 回退
```

### 1.3 三种来源

| 来源 | 生成方式 | project_id | app_map_id | 特点 |
|---|---|---|---|---|
| **全局预设** | `seed_preset_macros.py` 脚本写入 | NULL | NULL | system级操，永不淘汰 |
| **飞轮创建** | `MacroCreatorService` 从完成会话自动生成 | NULL | NULL | 经验证后激活，永不淘汰 |
| **AppMap 模板** | `macro_factory.synthesize()` 从应用地图批量产出 | 具体项目ID | 有值 | 需人工审核，地图重生成时废弃旧宏 |

### 1.4 生命周期状态机

```
pending_review ──→ verified ──→ obsolete
     │                 │
     │           (is_active=true)
     │                 │
     ▼                 ▼
  退回编辑        路由索引可见
```

---

## 二、YAML 格式规范

### 2.1 顶层结构

宏脚本是一个 YAML 字符串，内容为步骤列表（List of steps），每个步骤是一个字典。

```yaml
# 序列化存储在 macros.macro_script 字段
# MacroScript.from_yaml() 解析为 MacroStep 列表
# MacroScript.to_yaml() 序列化回字符串

- step_number: 1          # 可选，引擎自动编号
  type: action             # 必填: action | extract | if | loop | control | dump | native
  source: desktop          # 必填: dom | mobile | desktop
  event_type: click        # 动作类型（type=action 时必填）
  target_selector: "#btn"  # 元素选择器（推荐优先使用）
  description: "点击提交"  # 可选，人类可读描述
  payload:                 # 可选，动作参数
    delay_after_ms: 200
```

### 2.2 步骤类型全集

| type | 用途 | 关键字段 | 示例 |
|---|---|---|---|
| `action` | 执行交互动作 | `event_type`, `target_selector`, `payload` | click, navigate, input |
| `extract` | 从页面提取数据 | `extract_type`, `target_selector`, `key` | get_text, screenshot |
| `if` | 条件分支 | `condition`, `then_steps`, `else_steps` | element_exists 判断 |
| `loop` | 循环执行子步骤 | `steps`, `max_iterations`, `collect_mode` | 列表遍历、批量收集 |
| `control` | 通用控制流 | 同 if，按 `payload.condition.type` 分发 | 高级条件 |
| `dump` | 导出数据 | `payload.sink` (file/mcp/webhook) | 结果写入文件 |
| `native` | 执行外部脚本 | `payload.script` | G5 门控，白名单 |

### 2.3 执行源（source）与动作类型

#### dom（浏览器 Web）

| event_type | payload 关键字段 | 说明 |
|---|---|---|
| `navigate` | `url`, `wait_until`, `timeout_ms` | 导航（相同 URL 自动跳过） |
| `click` | `button`, `clicks`, `modifiers`, `delay_after_ms` | 点击元素 |
| `input` / `type_text` | `text`, `append`, `enter` | 输入文本 |
| `select_option` | `text` / `value` | 下拉选择 |
| `wait` | `duration_ms` / `seconds` | 等待 |
| `wait_for` | `target_selector`, `timeout_ms` | 等待元素出现 |
| `scroll` | `direction`, `amount` | 滚动 |
| `hover` | — | 悬停 |
| `key_press` | `key`, `modifiers` | 按键 |
| `new_tab` / `switch_tab` | `url` / `index` | 标签页操作 |
| `upload` | `file_path` | 上传文件 |
| `run_js` | `script` / `expression` | 执行 JS（G5 门控） |
| `screenshot` | `region` | 截图 |
| `get_text` | `attribute` | 提取文本 |
| `get_attribute` | `attribute` | 提取属性 |
| `dialog_handle` | `action` (accept/dismiss) | 弹窗处理 |
| `reload` | — | 刷新 |

#### mobile（Android 移动端）

| event_type | payload 关键字段 | 说明 |
|---|---|---|
| `tap` | `x`, `y` (归一化坐标 0~1) | 点击 |
| `long_press` | `x`, `y`, `duration_ms` | 长按 |
| `input` | `text` | 输入 |
| `key_press` | `key` | 按键 |
| `swipe` | `direction`, `amount` | 滑动 |
| `scroll` | `direction`, `amount` | 滚动 |
| `back_key` | — | 返回键 |
| `home` | — | Home 键 |
| `open_app` | `package` | 打开应用 |
| `close_app` | — | 关闭应用 |
| `wait` | `duration_ms` | 等待 |
| `screenshot` | — | 截图 |
| `dump_ui` | — | 导出 UI 树 |
| `gui_extract` | `region` | OCR 区域提取 |

#### desktop（macOS 桌面）

| event_type | payload 关键字段 | 说明 |
|---|---|---|
| `open_app` | `app_name` / `bundle_id` | 打开应用（免焦点启动） |
| `close_app` | `app_name` | 关闭应用 |
| `click` | `x`, `y` | 鼠标点击 |
| `type_text` | `text` | 键盘输入 |
| `key_press` | `key` | 按键 |
| `scroll` | `direction`, `amount` | 滚动 |
| `screenshot` | — | 截图 |
| `applescript` | `script` | AppleScript 执行（G5 门控） |
| `ax_press` | — | AX 无障碍按下（免焦点） |
| `ax_menu_press` | `menu_path` | AX 菜单按下（免焦点） |
| `ax_set_value` | `value` | AX 设置值（免焦点） |
| `get_active_app` | — | 获取前台应用 |
| `mouse_click` | `button`, `x`, `y` | 鼠标原生点击 |

### 2.4 控制流

#### IF 条件分支

```yaml
- type: if
  condition:
    type: element_exists       # 条件类型
    target_selector: ".modal"  # 条件参数
  then_steps:
    - type: action
      event_type: click
      source: dom
      target_selector: ".close-btn"
  else_steps:
    - type: action
      event_type: wait
      source: dom
      payload:
        duration_ms: 300
```

支持的条件类型：
- `element_exists` — 元素是否存在（跨 dom/mobile/desktop）
- `element_visible` — 元素是否可见
- `text_contains` — 页面文本是否包含
- `has_more_items` — 是否还有更多项（分页检测）
- `url_is` / `url_contains` — URL 匹配

#### LOOP 数据循环

```yaml
- type: loop
  source: dom
  payload:
    items_key: items           # 从 extracted_data 读取的 key
    max_iterations: 10         # 最大循环次数
    max_retries: 3             # 失败重试次数
    backoff_base: 2.0          # 指数退避基数
  steps:
    - type: action
      event_type: click
      source: dom
      target_selector: "{{item.link}}"
```

#### LOOP 两阶段批量收集（collect_mode）

```yaml
- type: loop
  collect_mode: auto            # normal | list | detail | auto
  source: mobile
  payload:
    list_config:
      anchor_rule: "//android.widget.TextView[@text='商品']"
      feature_config:
        max_items: 20
        scroll_direction: down
    detail_config:
      data_capture:
        title: "//android.widget.TextView[@id='title']"
        price: "//android.widget.TextView[@id='price']"
  steps:
    - type: extract
      extract_type: get_text
      target_selector: ".detail-title"
      key: detail
```

- `normal` — 标准循环
- `list` — 仅 LIST 阶段：滚动收集列表项
- `detail` — 仅 DETAIL 阶段：逐项处理
- `auto` — 自动先 LIST 再 DETAIL（状态持久化到文件，支持断点续传）

### 2.5 变量注入

```yaml
# 参数注入（执行时传入）
- type: action
  event_type: input
  source: dom
  target_selector: "#search"
  payload:
    text: "{{ keyword }}"       # 来自 params.keyword

# 提取结果引用
- type: action
  event_type: click
  source: dom
  target_selector: ".result-{{ extracted.index }}"

# 循环项字段
- type: action
  event_type: click
  source: dom
  target_selector: "{{ item.link }}"

# 基础 URL（项目配置）
- type: action
  event_type: navigate
  source: dom
  payload:
    url: "{{ base_url }}/list"
```

### 2.6 数据提取与导出

```yaml
# 单步提取
- type: extract
  source: dom
  extract_type: get_text
  target_selector: ".price"
  key: item_price                # 存入 extracted_data["item_price"]

# 批量提取捕获（detail_config 内）
- type: loop
  collect_mode: detail
  payload:
    detail_config:
      data_capture:
        title: "//h1"
        price: "//.price"

# 导出到文件/MCP/Webhook
- type: dump
  payload:
    sink: file                   # file | mcp | webhook
    file_path: "/tmp/results.json"
```

---

## 三、设计约束

### 3.1 安全约束

| 约束 | 说明 | 违反后果 |
|---|---|---|
| **G5 原生脚本门控** | `applescript` / `run_js` / `native` 类型步骤受白名单控制，默认拒绝 | 执行被阻止 |
| **风险层级** | observe < act < data < money < escape，执行策略可设 `max_risk_tier` | 高风险被策略拒绝 |
| **动作族** | `action_family()` 派生: escape / observe / control / act，escape 族需显式授权 | 策略门控拒绝 |
| **requires_confirmation** | money/data-write 操作需用户确认 | 执行前弹出确认 |

### 3.2 格式约束

| 约束 | 说明 |
|---|---|
| `step_number` 全局唯一 | 嵌套步骤也不能重复编号（`MacroScript.check_step_numbers` 严格校验） |
| `extract` 类型必须有 `extract_type` | `MacroStep.validate_extract_type` 强校验 |
| 禁止字面量目标 | `target_selector` 必须指向 AppMap 条目或实际选择器，禁止硬编码假名 |
| `target_selector` 优先于坐标 | 坐标仅作 fallback，需标记 `original_x/y` 和 `vision_corrected` |
| 步骤类型兼容 | `model_validator` 自动迁移 `while`→`loop`，`then/else/do`→`then_steps/else_steps/steps` |

### 3.3 执行约束

| 约束 | 说明 |
|---|---|
| **仅 verified + is_active 可路由** | `is_routable()` 检查两个条件 |
| **必需参数完整性** | `preflight()` 检查 `parameters_schema` 定义的必填参数 |
| **source 匹配** | 仅当宏的 source 在执行策略 `allowed_sources` 内才执行 |
| **family 匹配** | 仅当 `action_family()` 结果在 `allowed_families` 内才执行 |
| **navigate 去重** | 已在目标 URL 时自动跳过（`_execute_browser_step`） |

### 3.4 最佳实践

| 实践 | 说明 |
|---|---|
| **包含 observe 步** | 每个 action 后应有 extract/screenshot/dump_ui 验证结果 |
| **合理等待** | 用 `wait` 步骤或 `delay_after_ms`，引擎优化器会自动合并 |
| **循环设上限** | `max_iterations` 始终设置，防止死循环 |
| **避免冗余** | 不写 `mouse_move` / `hover` 等低价值动作（优化器会自动过滤） |
| **坐标归一化** | mobile 坐标范围 0~1（相对屏幕宽高比） |
| **参数化** | 可变值用 `{{ param }}` 而非硬编码 |
| **赋描述** | 每个步骤加 `description` 便于调试和验证报告 |

---

## 四、完整示例脚本

### 4.1 桌面 AppleScript（预设宏风格）

```yaml
- type: action
  event_type: applescript
  source: desktop
  payload:
    script: set volume output volume ((output volume of (get volume settings)) + 10)
```

```yaml
- type: action
  event_type: open_app
  source: desktop
  payload:
    app_name: WeChat
```

### 4.2 浏览器搜索

```yaml
- type: action
  event_type: navigate
  source: dom
  payload:
    url: "https://www.baidu.com"
    wait_until: load
- type: action
  event_type: input
  source: dom
  target_selector: "#kw"
  payload:
    text: "{{ keyword }}"
    enter: true
- type: action
  event_type: wait
  source: dom
  payload:
    duration_ms: 2000
- type: extract
  source: dom
  extract_type: get_text
  target_selector: ".result-title"
  key: search_results
```

### 4.3 移动端列表收集

```yaml
- type: action
  event_type: open_app
  source: mobile
  payload:
    package: com.example.app
- type: action
  event_type: wait
  source: mobile
  payload:
    duration_ms: 3000
- type: loop
  collect_mode: auto
  source: mobile
  payload:
    list_config:
      anchor_rule: "//android.widget.TextView[@text='商品列表']"
      max_items: 20
    detail_config:
      data_capture:
        title: "//android.widget.TextView[@id='title']"
        price: "//android.widget.TextView[@id='price']"
  steps:
    - type: extract
      source: mobile
      extract_type: get_text
      target_selector: "//android.widget.TextView[@id='title']"
      key: item_title
    - type: action
      event_type: back_key
      source: mobile
```

### 4.4 带条件的桌面 AX 操作

```yaml
- type: action
  event_type: open_app
  source: desktop
  payload:
    app_name: Safari
- type: action
  event_type: wait
  source: desktop
  payload:
    duration_ms: 2000
- type: if
  condition:
    type: element_exists
    target_selector: "ax://AXButton[标识='关闭']"
  then_steps:
    - type: action
      event_type: ax_press
      source: desktop
      target_selector: "ax://AXButton[标识='关闭']"
  else_steps:
    - type: action
      event_type: wait
      source: desktop
      payload:
        duration_ms: 1000
```

---

## 五、内置预设宏清单

以下为系统级全局宏（`project_id=NULL`, `namespace="preset"`, `risk_tier="ui"`, `requires_confirmation=False`），随系统部署自带，所有项目可见。

> **设计原则**：仅含纯动作类宏——执行完即可，无需 TTS 回读结果。查询类（IP/电量/时间/系统版本等）走 Agent 路径。应用打开/退出通过 `{app}` slot 参数化。

### 5.1 🔊 音量控制 (7)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 静音 | 静音、别出声、不要声音、安静 | `set volume with output muted` |
| `unmute` | 取消静音、恢复声音、打开声音、不静音了 | 取消静音 |
| `volume_up` | 音量大一点、调高音量、大声一点、声音大一点、调大音量 | 音量 +10 |
| `volume_down` | 音量小一点、调低音量、小声一点、声音小一点、调小音量 | 音量 -10 |
| `volume_max` | 音量最大、最大声、声音调到最大、最大音量 | 音量 100 |
| `volume_mid` | 音量一半、音量中等、声音一半 | 音量 50 |
| `volume_min` | 音量最小、最小声 | 音量 0 |

### 5.2 ▶️ 播放控制 (7)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 播放暂停 | 暂停、继续播放、开始播放、停一下、别放了 | 键盘播放/暂停 |
| 下一曲 | 下一首、下一曲、切歌、换一首、下首歌 | 键盘下一曲 |
| 上一曲 | 上一首、上一曲、回上一首、上一首歌 | 键盘上一曲 |
| 快进 | 快进、往前跳、跳过这段、快进一下 | 右方向键 |
| 快退 | 快退、往后退、倒回去、退回几秒 | 左方向键 |
| 加速播放 | 加速、倍速、加快速度、放快一点 | `>` 键 |
| 减速播放 | 减速、减慢速度、放慢一点、慢放 | `<` 键 |

### 5.3 🖥️ 系统操作 (5)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 锁屏 | 锁屏、锁定屏幕、锁一下 | ⌘⌃Q |
| 息屏 | 息屏、关屏幕、关闭显示器 | `pmset displaysleepnow` |
| 深色模式 | 切换深色模式、暗色模式、夜间模式 | 切换 appearance |
| 清空废纸篓 | 清空废纸篓、清倒废纸篓、清空垃圾桶 | Finder empty trash |
| 弹出磁盘 | 弹出磁盘、弹出U盘、推出外置盘、弹出所有 | Finder eject |

### 5.4 📸 截图 (4)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 截屏 | 截图、截屏、截个图、截一下屏 | 全屏截图到桌面 |
| 区域截屏 | 区域截图、截取选定区域、选区截图 | 交互选区截图 |
| 截屏到剪贴板 | 截图复制、截图到剪贴板、截图不保存 | 截图到剪贴板 |
| 定时截屏 | 定时截图、延时截图、倒计时截图、稍后截图 | 5 秒后截图 |

### 5.5 🗔 窗口管理 (6)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 隐藏窗口 | 隐藏、隐藏窗口、隐藏当前、先藏起来 | ⌘H |
| 隐藏其他 | 隐藏其他、只保留当前、别的都隐藏、只看当前 | ⌥⌘H |
| 最小化 | 最小化、最小化窗口、收起窗口 | ⌘M |
| 全屏 | 全屏、最大化、全屏窗口、全屏显示 | ⌃⌘F |
| 关闭窗口 | 关闭窗口、关掉当前、把窗口关掉 | ⌘W |
| 强制退出 | 强制退出、强退、程序卡死、结束任务 | ⌥⌘⎋ |

### 5.6 📋 通用编辑 (7)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 撤销 | 撤销、撤回、回退、取消上一步 | ⌘Z |
| 重做 | 重做、恢复撤销 | ⇧⌘Z |
| 剪切 | 剪切、剪下、剪掉 | ⌘X |
| 复制 | 复制、拷贝、复制选中 | ⌘C |
| 粘贴 | 粘贴、粘贴出来、贴出来 | ⌘V |
| 全选 | 全选、选中全部、全部选中 | ⌘A |
| 保存 | 保存、存档、存盘、保存文件 | ⌘S |

### 5.7 🌐 浏览器 (6)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 新建标签页 | 新建标签页、新建标签、打开新标签、新开一页、新标签 | ⌘T |
| 关闭标签页 | 关闭标签页、关闭标签、关掉标签、关掉这一页 | ⌘W |
| 恢复标签页 | 恢复标签、打开刚关的、不小心关了 | ⇧⌘T |
| 刷新 | 刷新、重新加载、刷新一下 | ⌘R |
| 后退 | 后退、返回、上一页、后退一页 | ⌘[ |
| 前进 | 前进、向前、往前、前进一页 | ⌘] |

### 5.8 ⏱️ QuickTime Player 跳转 (1 个参数化宏)

通过 `{time}` slot 参数化，解析自然语言时间并跳转。

| 宏名 | 触发语 | 参数 | 动作 |
|---|---|---|---|
| **跳转到时间** | 跳到{time}、调到{time}处、跳到{time}位置 | `time` (type=str) | QuickTime Player 跳转 |

支持的时间格式：`30分钟`、`1小时20分`、`45秒`、`1小时`、`5分30秒`、纯数字（≤99 视为分钟）。

### 5.9 🤖 应用操作 (2 个参数化宏)

两个宏通过 `{app}` slot 参数化，覆盖所有已安装应用的打开和退出。

| 宏名 | 触发语 | 参数 |
|---|---|---|
| **打开应用** | 打开{app}、启动{app}、开一下{app} | `app` (type=app) |
| **退出应用** | 退出{app}、关闭{app}、关掉{app} | `app` (type=app) |

应用名称消歧：别名 → 拼音相等 → 编辑距离 1 → 使用排名 tiebreak。

### 5.10 🌐 网站直达 (1 个参数化宏)

| 宏名 | 触发语 | 参数 | 说明 |
|---|---|---|---|
| **打开网站** | 打开{site}、上{site}看看、去{site}、访问{site} | `site` (type=str) | 淘宝/京东/百度/B站/知乎/抖音等 20+ 网站 |

### 5.11 🔍 搜索 (1 个参数化宏)

| 宏名 | 触发语 | 参数 |
|---|---|---|
| **搜索** | 搜索{query}、搜一下{query}、查一下{query}、百度一下{query} | `query` (type=str) |

### 5.12 ⚙️ 系统设置 (1 个参数化宏)

| 宏名 | 触发语 | 参数 | 说明 |
|---|---|---|---|
| **打开系统设置** | 打开{panel}设置、打开{panel}、设置{panel} | `panel` (type=str) | WiFi/蓝牙/声音/显示/键盘/壁纸等 |

### 5.13 ⌨️ 通用按键 (2)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 按回车 | 按回车、按一下回车、回车 | 回车键 |
| 按空格 | 按空格、按一下空格、空格 | 空格键 |

### 5.14 📁 文件操作 (5)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 打开下载文件夹 | 打开下载、去下载文件夹、打开下载目录 | `open ~/Downloads` |
| 打开最近文件 | 打开最近、最近文件、最近使用、刚用过的文件 | ⌘⇧F |
| 新建文件夹 | 新建文件夹、创建文件夹、新建目录、建个文件夹 | ⌘⇧N |
| 移到废纸篓 | 移到废纸篓、删除选中、丢垃圾桶、删掉选中的 | ⌘⌫ |
| 压缩 | 压缩、打包、打个包、zip压缩 | Finder zip |

### 5.15 🔌 开关控制 (6)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 打开 WiFi | 打开WiFi、开启WiFi、连接WiFi、打开无线 | `networksetup on` |
| 关闭 WiFi | 关闭WiFi、断开WiFi、关掉WiFi、关闭无线 | `networksetup off` |
| 打开蓝牙 | 打开蓝牙、开启蓝牙 | `blueutil -p 1` |
| 关闭蓝牙 | 关闭蓝牙、关掉蓝牙 | `blueutil -p 0` |
| 打开勿扰 | 打开勿扰、勿扰模式、专注模式、不要打扰我 | DND on |
| 关闭勿扰 | 关闭勿扰、关闭勿扰模式、退出专注、退出勿扰 | DND off |

### 5.16 🗔 桌面导航 (3)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 显示桌面 | 显示桌面、回到桌面、看桌面 | 隐藏所有窗口 |
| 切换窗口 | 切换窗口、下一个窗口 | ⌘Tab |
| 打开下载文件夹 | 打开下载、去下载文件夹、下载目录 | `open ~/Downloads` |

### 5.17 🔋 系统电源 (4)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 关机 | 关机、关闭电脑、帮我关机 | `shut down` |
| 重启 | 重启、重新启动、重启一下 | `restart` |
| 睡眠 | 睡眠、让电脑休息、休眠 | `sleep` |
| 注销 | 注销、退出登录、切换用户 | `log out` |

### 5.18 ▶️ 播放选中文件 (1)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 播放选中文件 | 播放这个视频、播放这个文件、播放选中的、放一下这个、把这个播了 | Finder 打开选中文件 |

### 5.19 🎵 音乐播放 (3)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 播放音乐 | 来点音乐、放首歌、听歌、我想听歌 | Music app 播放 |
| 单曲循环 | 单曲循环、循环播放、就放这一首 | `song repeat to one` |
| 随机播放 | 随机播放、乱序播放、随便放 | `shuffle enabled` |

### 5.20 🗓️ 日期时间 (1)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 报时 | 今天几号、现在几点、几点了、当前时间、今天星期几、报时 | `say` 语音播报 |

### 5.21 📂 打开系统文件夹 (1 个参数化宏)

| 宏名 | 触发语 | 参数 | 说明 |
|---|---|---|---|
| **打开系统文件夹** | 打开{dir}文件夹、去{dir}文件夹、打开{dir} | `dir` (type=str) | 桌面/下载/文稿/图片/音乐/影片/应用/实用工具 |

### 5.22 🔀 切换到应用 (1 个参数化宏)

| 宏名 | 触发语 | 参数 |
|---|---|---|
| **切换到应用** | 切换到{app}、去{app}看看、切到{app} | `app` (type=app) |

### 5.23 🧊 窗口管理增强 (3)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 全部最小化 | 全部最小化、全都收起来、所有窗口都收起来 | ⌥⌘M |
| 新建窗口 | 新建窗口、新开一个窗口、再来一个 | ⌘N |
| 关闭其他应用 | 关闭其他应用、把其他的关了、只留着这个 | 退出非前台应用 |

### 5.24 😊 插入表情符号 (1)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 插入表情符号 | 插入表情、加个表情、加个emoji、打开表情 | ⌃⌘Space |

### 5.25 🧹 清空剪贴板 (1)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 清空剪贴板 | 清空剪贴板、清除剪贴板、清空刚复制的 | `set clipboard to ""` |

### 5.26 ⏰ 倒计时 (1 个参数化宏)

| 宏名 | 触发语 | 参数 |
|---|---|---|
| **倒计时** | 倒计时{minutes}分钟、计时{minutes}分钟、闹钟{minutes}分钟 | `minutes` (type=str) |

后台 `sleep` + `say` 提醒，不阻塞当前操作。

### 5.27 ♿ 辅助功能 (3)

| 宏名 | 触发语 | 动作 |
|---|---|---|
| 朗读 | 朗读、朗读选中、读出来、读一下、念出来 | ⌥⎋ |
| 放大 | 放大、放大画面、放大屏幕、看不清楚 | ⌥⌘= |
| 缩小 | 缩小、缩小画面、缩小屏幕 | ⌥⌘- |

### 5.28 完整汇总

| 类别 | 数量 | 说明 |
|---|---|---|
| 🔊 音量控制 | 7 | 独立 AppleScript |
| ▶️ 播放控制 | 7 | 含快进快退、加减速 |
| 🖥️ 系统操作 | 5 | 锁屏/息屏/深色/清废纸篓/弹出 |
| 📸 截图 | 4 | 全屏/区域/剪贴板/定时 |
| 🗔 窗口管理 | 6 | 隐藏/最小化/全屏/关闭/强退 |
| 📋 通用编辑 | 7 | 撤销/剪切/复制/粘贴/全选/保存 |
| 🌐 浏览器 | 6 | 新建/关闭/恢复标签/刷新/前进/后退 |
| ⏱️ QuickTime 跳转 | 1 | 参数化 `{time}` slot |
| 🤖 应用操作 | 2 | 参数化 `{app}` slot |
| 🌐 网站直达 | 1 | 参数化 `{site}` slot，20+ 站点 |
| 🔍 搜索 | 1 | 参数化 `{query}` slot |
| ⚙️ 系统设置 | 1 | 参数化 `{panel}` slot，15+ 面板 |
| 🗓️ 日期时间 | 1 | `say` 语音播报 |
| 📂 打开系统文件夹 | 1 | 参数化 `{dir}` slot，10+ 路径 |
| 🔀 切换到应用 | 1 | 参数化 `{app}` slot |
| 🧊 窗口管理增强 | 3 | 全部最小化/新建窗口/关闭其他 |
| 😊 插入表情符号 | 1 | ⌃⌘Space |
| 🧹 清空剪贴板 | 1 | 清空 clipboard |
| ⏰ 倒计时 | 1 | 参数化 `{minutes}` slot |
| ⌨️ 通用按键 | 2 | 回车/空格 |
| 📁 文件操作 | 5 | 含打开下载、最近文件 |
| 🔌 开关控制 | 6 | WiFi/蓝牙/勿扰 |
| 🗔 桌面导航 | 3 | 显示桌面/切换窗口/打开下载 |
| 🔋 系统电源 | 4 | 关机/重启/睡眠/注销 |
| ▶️ 播放选中文件 | 1 | Finder 打开 |
| 🎵 音乐播放 | 3 | 播放/单曲循环/随机 |
| ♿ 辅助功能 | 3 | 朗读/放大/缩小 |
| **总计** | **82** | |

## 六、全局宏 vs 项目宏

| 维度 | 全局宏（Global/Preset） | 项目宏（Project） |
|---|---|---|
| `project_id` | `NULL` | 项目 ID |
| `namespace` | `"preset"` | `NULL` 或自定义 |
| 内容 | OS 级系统操作 | 业务自动化流 |
| 审核 | 预设直接 `verified`；沉降的先 `pending_review` | 初始 `pending_review`，需审核 |
| 淘汰 | 永不（飞轮宏 `app_map_id=NULL`） | AppMap 重生成时批量废弃 |
| 匹配 | L0 快速道（trigger_patterns 直接命中） | Agent 上下文检索 + LLM 匹配 |
| 典型示例 | 静音、截图、打开微信 | 在 Chrome 搜报告、导出报表 |

路由索引加载逻辑（`init_spec.py`）：

```python
select(Macro).where(
    Macro.is_active.is_(True),
    Macro.status == "verified",
    (Macro.project_id.is_(None)) | (Macro.project_id == current_project_id),
).order_by(
    case((Macro.namespace == "preset", 0), else_=1),  # 预设宏优先
    Macro.created_at.asc(),
)
```

全局宏和项目宏同时加载，预设宏排序在前。

---

## 七、相关文件索引

| 文件 | 用途 |
|---|---|
| `app/core/execution/macro/schemas.py` | 所有数据模型和枚举定义 |
| `app/core/execution/macro/engine/__init__.py` | 执行引擎主入口 |
| `app/core/execution/macro/runner.py` | 门控检查 + 确定性执行 |
| `app/core/execution/macro/service.py` | 服务层封装 |
| `app/core/execution/macro/lifecycle.py` | 生命周期 CRUD |
| `app/core/execution/macro/compiler.py` | 轨迹编译为宏 |
| `app/core/execution/macro/optimizer.py` | 5 轮优化流水线 |
| `app/core/execution/macro/validator.py` | Agent 验证器 |
| `app/core/execution/macro/macro_creator_service.py` | 飞轮创建 |
| `app/core/execution/macro/healing_policy.py` | 三级自愈策略 |
| `app/models/macro.py` | ORM 模型 |
| `docs/macro_script_reference.yaml` | YAML 格式快速参考 |
