# Tauri v2 桌面端自动化脚本编写指南

## 环境

- macOS 15.7.2
- Tauri v2 (WKWebView)
- 窗口位置: (60, 25), 尺寸: 1860×1055
- app 进程名: `EvoLoop`

---

## 遇到的问题与解决方案

### 1. cliclick 模拟鼠标点击 → ❌ 无效

```applescript
do shell script "/usr/local/bin/cliclick c:810,1045"
```

Tauri v2 的 WKWebView 不响应 cliclick 生成的 CGEvent 鼠标事件。

### 2. AppleScript keystroke 输入中文 → ❌ 乱码

```applescript
tell application "System Events" to keystroke "帮我分析架构"
```

`keystroke` 基于当前键盘布局发送按键事件。如果当前输入法为英文，
中文字符会被转成 Unicode 码点，AI 收到后显示为 `aaaaaaamall-backendaaaaaa`。

### 3. Accessibility API 直接操作 UI 元素 → ✅ 有效

macOS Accessibility API (System Events) 能找到 WebView 内部的 `AXTextArea`、
`AXStaticText`、`AXLink` 等无障碍元素，并直接交互。

### 4. 剪贴板粘贴输入中文 → ✅ 有效

```bash
echo "中文文本" | pbcopy
# AppleScript: keystroke "v" using command down
```

---

## 页面导航（主侧边栏）

侧边栏每个菜单项由两部分组成：`AXLink`（图标，可点击，x=68）和 `AXStaticText`（标签，x=100）。

### 导航到页面

```applescript
tell application "System Events"
    tell process "EvoLoop"
        set allElems to entire contents of window 1
        repeat with elem in allElems
            try
                set r to role of elem
                set p to position of elem
                set x to item 1 of p
                set y to item 2 of p
                -- 按坐标查找 Link
                if r is "AXLink" and x = 68 and y = 217 then
                    perform action "AXPress" of elem
                    exit repeat
                end if
            end try
        end repeat
    end tell
end tell
```

### 侧边栏坐标映射

| 页面 | StaticText | Link (可点击) | y (screen) |
|------|-----------|---------------|-----------|
| EvoLoop (logo) | — | (68, 57) | 82 |
| 聊天 | (100, 116) | (68, 109) | 134 |
| 项目 | (100, 152) | (68, 145) | 170 |
| 待办 | (100, 188) | (68, 181) | 206 |
| 学习 | (100, 224) | (68, 217) | 242 |
| 设置 | (100, 260) | (68, 253) | 278 |

注意：`every link of window 1` 在某些 macOS 版本可能语法报错。
始终使用 `entire contents of window 1` + 按 role/position 过滤的方式。但 `entire contents` 在页面内容多时可能超时（>120s），
建议先导航到空页面再遍历，或使用下面的优化方式。当 `entire contents` 超时后无法再用 `entire contents`
（需等待前一个请求完成），应对方案：直接用 `cliclick` 坐标点（仅对 AXLink 有效）或
`click at` System Events 命令。

## 演示脚本

脚本文件：`frontend/tests/demo/evoloop-demo.applescript`

覆盖三个场景：
1. **AI 聊天**（架构分析 → 依赖分析 → 数据统计）~4min
2. **项目导航**（项目列表 → 文件/任务/百科 Tab）~1.5min
3. **学习中心**（技能库 → 指令库 → MCP 工具）~1min

**未覆盖的场景（需额外准备）：**
- S03-S05 语音 HUD（需麦克风输入）
- S06-S08 移动端（需 Android 实机/模拟器）
- S13 MacOS 桌面操控（Agent 控制桌面应用）
- S14 Android 操控（需 scrcpy + 设备）
- S15 A2A 协作（需多 Agent 会话）
- S19 知识图谱（需预置 Wiki 数据）
- S23 操作录制（需用户实际录制操作）
- S25 宏编辑器（在列表页无直接入口）

## 项目页面

### 导航到项目列表

侧边栏 Link at (68, 145) → `perform action "AXPress"`

### 页面结构

Header 显示 "项目" + 计数。

项目列表卡片，每行 3 个项目，每个项目包含：
- 名称（AXStaticText，可点）
- 描述（AXStaticText）
- 状态标签："已索引"/"进行中"
- 日期

当前系统 9 个项目：Ruoyi-Cloud-Plus、mall-backend、电瓷项目招标、
engineering-bridge、design-branding、evoloop、xianyu_data、
software-ecommerce、ecommerce-admin。

### 进入项目详情

**方法一：cliclick 坐标点击（有效）**

```bash
# mall-backend 在窗口坐标 (1051, 277) → 屏幕绝对坐标 (1111, 302)
cliclick c:1111,302
```

**方法二：AXGroup AXShowMenu / AXScrollToVisible**

每个项目卡片是 AXGroup，可通过菜单或滚动到可见操作。

### 项目详情二级导航

进入项目后，左侧出现二级 Tab 导航（x=120-160）：

| Tab | StaticText | Link (可点击) |
|-----|-----------|---------------|
| 概览 | (160, 138) | (120, 129) |
| 文件 | (160, 178) | (120, 169) |
| 任务 | (160, 218) | (120, 209) |
| 百科 (知识图谱) | (160, 258) | (120, 249) |
| 密码箱 | (160, 298) | (120, 289) |
| 指令 | (160, 338) | (120, 329) |

返回按钮：AXLink "返回项目列表" at (118, 74)

### 项目详情页内容

概览 Tab：项目描述、统计数据（总任务/已完成/进行中）、"发现"按钮

## 待办页面

### 导航

侧边栏 Link at (68, 181) → `perform action "AXPress"`

### 页面结构

筛选栏：状态（全部/待办/已完成）、优先级
项目选择器：AXComboBox
事项列表

## 学习中心

### 导航

侧边栏 Link at (68, 217) → `perform action "AXPress"`

### Tab 切换（4 个标签页）

顶部使用 AXRadioButton 切换（y=178）：

| Tab | 说明 | RadioButton | 操作 |
|-----|------|-------------|------|
| 技能库 | 预置/录制的技能列表 | (373, 178) | `perform action "AXPress"` |
| 移动录制 | 手机操作录制 | (482, 178) | 同上 |
| 指令库 | 语音宏指令 | (602, 178) | 同上 |
| 外部工具 | MCP 服务器管理 | (710, 178) | 同上 |

```applescript
-- 切换到"指令库"Tab
set allElems to entire contents of window 1
repeat with elem in allElems
    if role of elem is "AXRadioButton" then
        set p to position of elem
        set x to item 1 of p
        if x = 602 then
            perform action "AXPress" of elem
            exit repeat
        end if
    end if
end repeat
```

**优化方式：直接访问 UI 元素路径（避免遍历全部）**

```applescript
tell application "System Events"
    tell process "EvoLoop"
        set tabGroup to tab group 1 of group 3 of group 7 of ¬
            UI element 1 of scroll area 1 of group 1 of ¬
            group 1 of window 1
        set r4 to radio button 4 of tabGroup  -- 外部工具
        perform action "AXPress" of r4
    end tell
end tell
```

RadioButton 索引：1=技能库, 2=移动录制, 3=指令库, 4=外部工具

### 技能库（默认 Tab）

7+ 个预置技能，每个技能卡片包含：
- 技能名称（如 csv_文件读取与格式化展示）
- 触发短语（如"写一个Python脚本读取CSV文件"）
- 标签：专家级技能
- 工具链：synthesize_skill, route_to, read_file, edit_file, ...
- 运行次数
- 状态：待审核

### 指令库

87 条预设中文语音宏，每条包含：
- 名称（如"静音"、"音量增大"、"播放暂停"）
- 状态：已验证
- 类型：ui
- 范围：全局/未分配
- 默认指令
- 多个触发短语（同义词列表）

### 移动录制 Tab

RadioButton at (487, 178)，功能：
- 手机操作录制，通过 ADB/USB 连接 Android 设备
- 页面展示 Android 镜像连接指引
- 实测无设备连接时页面内容为空（无模拟器）

## 项目分析与初始化

项目概览页（`/projects/$projectId`）空状态显示"生成画像"按钮（Rocket 图标），点击弹出 `ProjectAnalysisDialog`：

**对话框内容：**
- 标题：项目分析初始化
- 三个生成项（默认全选）：
  1. **项目画像** — 生成 PROJECT.md（项目简介、技术栈、功能描述）
  2. **Wiki 文档** — 架构文档、模块说明（填充百科/知识图谱）
  3. **SOP 自动化指令** — 界面操作流程、自动化脚本（关联 Macro）
- 额外选项：记录密钥（默认关闭，记录 API Token / 密码）
- 按钮：取消 / 开始生成 (N 项) / 关闭

**触发路径：** 侧边栏项目 → 首页"项目管理"卡片 → 项目列表 → 点击项目 → 概览页"生成画像"按钮

## 项目详情页

### 导航路径

正确的导航路径：
1. 侧边栏"项目"(cliclick c:130,170) → 首页（工作空间面板）
2. 点击"项目管理"卡片(cliclick c:705,819) → 项目列表
3. 点击项目名(AXPress) → 项目详情

### 外部工具 / MCP Tab

RadioButton at (716, 178)，显示预配 MCP 服务器列表：

| MCP 服务器 | 状态 | 命令 |
|-----------|------|------|
| local-postgres | available | npx ... |
| filesystem | available | npx ... |

每个 MCP 服务器行包含：名称、状态、启动命令。

**MCP 添加对话框：**
点击"添加工具"按钮（(1550, 225) screen / window x=1490）弹出模态对话框，包含：
- Title: mcp.addTitle (i18n key)
- Desc: mcp.addDesc
- 字段：工具名称（AXTextField）、运行方式（AXTextField）、附加参数（AXTextField）
- 按钮：取消（(1023,708) AXButton）、添加工具（(1092,708) AXButton）、关闭（(1170,352) AXButton）

### 指令库 Tab

RadioButton at (607, 178)，显示分页的语音宏列表（每页 50 条，共 87 条）。
每条宏包含：名称、状态（已验证）、类型（ui）、范围（全局/未分配）、
默认指令、多个触发短语（同义词列表）。

交互元素：
- "上一页"/"下一页" AXButton 导航
- "未关联实体" AXButton 筛选
- "运行" AXButton 执行宏（虚拟列表，均在 (1535,353)）
- 点击宏名称未打开编辑器；编辑功能可能在右键菜单或设置页

---

## Agent 任务执行（S10-S12）

Agent 通过聊天界面接收指令并执行复杂任务。已验证的指令：

| 指令类型 | 示例 | AI 响应时间 | 结果 |
|---------|------|-----------|------|
| 架构分析 | "帮我分析一下项目 mall-backend 的架构" | ~60s | 返回完整架构分析（技术栈/模块/分层） |
| 依赖分析 | "分析 package.json 的依赖关系，找出需要更新的包" | ~80s | 详细报表（当前版本/状态/建议/优先级排序/更新命令） |
| 项目统计 | "分析文件结构，统计各类文件数量" | ~70s | 文件分布（按模块/类型/大小/磁盘占用） |

Agent 执行过程中会在右侧"Agent 工作台"面板显示：
- 活跃计划 / 空闲状态
- 使用技能名称
- 思考过程（实时显示推理步骤）
- 执行命令记录

## 聊天页面

```applescript
on sendMessage(msg)
    set the clipboard to msg
    delay 0.3
    tell application "System Events"
        tell process "EvoLoop"
            set allElems to entire contents of window 1
            repeat with elem in allElems
                try
                    set r to role of elem
                    set p to position of elem
                    if r is "AXTextArea" and (item 2 of p) > 900 then
                        set focused of elem to true
                        delay 0.3
                        keystroke "v" using command down  -- Cmd+V 粘贴
                        delay 0.5
                        key code 36  -- Enter 发送
                        exit repeat
                    end if
                end try
            end repeat
        end tell
    end tell
end sendMessage
```

### 读取 AI 回复

```applescript
tell application "System Events"
    tell process "EvoLoop"
        set allElems to entire contents of window 1
        repeat with elem in allElems
            try
                set r to role of elem
                if r is "AXStaticText" then
                    set p to position of elem
                    set y to item 2 of p
                    set x to item 1 of p
                    if y > 200 and y < 950 and x > 400 then
                        set v to value of elem
                        if v is not "" then log v
                    end if
                end if
            end try
        end repeat
    end tell
end tell
```

### 聊天输入区元素

| 元素 | 窗口坐标 | 角色 | 说明 |
|------|---------|------|------|
| 聊天输入框 | (423, 982) | AXTextArea | 高36px, 宽1109px |
| 模型选择器 | (423, 1031) | AXComboBox | DeepSeek V4 Flash |
| 技能库 | (624, 1033) | AXPopUpButton | 技能库 |
| 终端模式 | (704, 1033) | AXButton | 进入终端交互模式 (PTY) |
| 上传文件 | (1316, 1033) | AXButton | 上传文件 |
| 朗读 | 消息末尾 | AXButton | 朗读回复 |
| 复制 | 消息末尾 | AXButton | 复制 |
| 引用 | 消息末尾 | AXButton | 引用 |
| 记住 | 消息末尾 | AXButton | 记住 |

## 设置页面

### 导航

侧边栏 Link at (68, 253) → `perform action "AXPress"`

### 结构

Header: "设置"
描述: "管理您的账户和 EvoLoop 配置。"

左侧子导航（AXButton 按钮，y=189/229/269/309/349/389）：

| 页面 | 说明 |
|------|------|
| 常规 | 语言、设备名称、工作空间路径 |
| AI 模型 | 模型选择、连接测试 |
| 语音设置 | TTS 引擎、语音角色、语速 |
| 个人资料 | 昵称、邮箱、修改密码 |
| 外观 | 主题切换、显示思考过程 |
| 危险区域 | 删除账户 |

### 常规设置

| 字段 | 类型 | 默认值 |
|------|------|--------|
| 语言 | AXComboBox | 中文 (Chinese) |
| 设备名称 | AXTextField | Mac-mini.local |
| 工作空间路径 | AXTextField | /Users/huangjinhuan/Projects |

底部还有"重新播放引导"按钮。

### AI 模型

Header: "AI 助手"
描述: "选择你的 AI 模型。系统会自动发现本地运行的服务。"

| 字段 | 类型 | 值 |
|------|------|-----|
| 模型选择 | AXComboBox | DeepSeek V4 Flash (Cloud) |
| 状态 | AXStaticText | 未测试 |
| 测试连接 | AXButton | — |
| 高级设置 | AXButton | — |

### 语音设置 (TTS)

Header: "语音合成 (TTS)"

| 字段 | 类型 | 值 |
|------|------|-----|
| 自动朗读 AI 回复 | AXCheckBox | true (勾选) |
| TTS Engine | AXComboBox | Edge TTS |
| 语音选择 | AXComboBox | Xiaoxiao (female) |
| 试听 | AXButton | — |
| 语速 | AXStaticText + Slider | 0.5 (慢↔正常) |


底部"高级语音设置"按钮。

### 个人资料

| 字段 | 类型 | 值 |
|------|------|-----|
| 昵称 | AXTextField | preterchan |
| 邮件 | AXTextField | (空) |
| 当前密码 | AXTextField | •••••••• |
| 新密码 | AXTextField | •••••••• |
| 确认密码 | AXTextField | •••••••• |
| 更新密码 | AXButton | — |

### 外观

主题选择（AXRadioButton）：
- 浅色 (Light, v=0)
- 深色 (Dark, v=1) ← 当前选中
- 跟随系统 (System, v=0)

对话显示：
- 显示思考过程: AXCheckBox (v=1, 已勾选)

### 危险区域

Header: "删除账户"
警告: "注销账号将永久删除您的所有数据，此操作无法撤销。是否继续？"
操作: AXPopUpButton "删除账户"

---

## 综合示例：完整对话流程

```applescript
-- 1. 确保 app 在前台
tell application "System Events"
    set frontmost of (first process whose name contains "EvoLoop") to true
end tell
delay 1

-- 2. 发送消息（剪贴板粘贴）
set the clipboard to "帮我分析一下项目 mall-backend 的架构"
delay 0.3

tell application "System Events"
    tell process "EvoLoop"
        set allElems to entire contents of window 1
        repeat with elem in allElems
            try
                set r to role of elem
                set p to position of elem
                if r is "AXTextArea" and (item 2 of p) > 900 then
                    set focused of elem to true
                    delay 0.3
                    keystroke "v" using command down
                    delay 0.5
                    key code 36
                    exit repeat
                end if
            end try
        end repeat
    end tell
end tell

-- 3. 等待 AI 回复（约 60-70 秒）
delay 70

-- 4. 读取回复
tell application "System Events"
    tell process "EvoLoop"
        set allElems to entire contents of window 1
        repeat with elem in allElems
            try
                if role of elem is "AXStaticText" then
                    set p to position of elem
                    set y to item 2 of p
                    set x to item 1 of p
                    if y > 200 and y < 950 and x > 400 then
                        set v to value of elem
                        if v is not "" then log v
                    end if
                end if
            end try
        end repeat
    end tell
end tell
```

---

## 关键按键映射

| 操作 | key code |
|------|---------|
| Enter (发送) | 36 |
| Tab | 48 |
| Cmd+V | `keystroke "v" using command down` |
| Esc | 53 |
| Delete | 51 |
| 方向键上 | 126 |
| 方向键下 | 125 |

---

## 注意事项

1. **权限**: 系统设置 → 隐私 → 辅助功能 → 允许 Terminal
2. **entire contents 耗时**: 首次调用约 10-30 秒；页面内容过多时可能超时（>120s）
3. **entire contents 死锁**: 一旦超时，必须等前一个请求完成才能再次调用，当前进程会阻塞。
   解决方案：如果超时，用 `cliclick` 或 `click at` 坐标点击替代，或使用直接路径访问
4. **AI 生成时间**: 复杂分析约 60-70 秒，要给足 delay
5. **try...end try**: 遍历时大量元素无 value/description，必须用 try 包裹
6. **cliclick 的局限性**: WKWebView 内部表单不响应 cliclick CGEvent，但 AXLink/AXStaticText
   的 cliclick 点击可生效（应该是 CLK 事件 vs HID 事件的区别）
7. **click at 命令**: System Events 的 `click at {x,y}` 接受屏幕绝对坐标，比 `cliclick` 更可靠
   （不经过 CGEvent 层）

## OCR 辅助调试

```bash
screencapture -x -R60,25,1860,1055 /tmp/shot.png
tesseract /tmp/shot.png stdout -l chi_sim+eng 2>/dev/null
```

## 像素分析

```python
from PIL import Image
img = Image.open('/tmp/shot.png')
# 暗色主题:
#   主背景 (13,13,13), 输入框 (17,17,17)/(28,28,28)
#   文本 (127-204,127-204,127-204)
#   强调色 (24,84,76) 青
#   代码高亮 (188,155,108) 金
```
