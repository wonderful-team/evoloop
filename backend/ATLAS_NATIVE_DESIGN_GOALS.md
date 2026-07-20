# Atlas-Native：原生应用确定性宏体系 · 设计目标（草案 v0.3）

2026-07-16。把 Web 侧已验证的"地图→确定性宏"范式平移到 macOS 原生应用，并顺势把 L0 本地动作从手写模板换成生成产物。

**v0.2（2026-07-16，M1 实测回填，详见验证报告 §四十一）**：
- **焦点假设推翻**：AX 测绘与 AXPress 交互**全程免焦点**（后台 Calculator 3×3=9 读回验证，前台不动）。宏执行不打断用户；仅 CGEvent 键盘注入需前台。`macos_driver.dump_ax_tree` 的"仅前台"是实现伪限制，M2 测绘器按 pid dump（`AXUIElementCreateApplication`）。
- **启动配方**：`open -b` + 轮询窗口实体化（windows>0），forceTerminate 后 LS 有再启动冷却须重试 open；存活/终止判定用 `pgrep/pkill -f <executablePath>`（NSWorkspace 快照在无 runloop 进程内不刷新，不可信）。
- **覆盖率分级实测**（9 应用）：A=Calculator/System Settings/Safari/Finder/Notes，B=Music/Terminal，C=WeChat/VSCode（VSCode 的 AXEnhancedUserInterface 开关实测无效）。C 级进 Triage/Agent+OCR，不做确定性承诺。
- **ax_path 重启 Jaccard**：Calculator 1.00 / System Settings 0.96 / WeChat 1.00 / Music 0.69（动态歌名）→ **选择器规则修订：结构（role+index 路径）优先，名称降级为提示，动态内容区接受漂移靠复采**。
- **M1 结论：go**，M2 开工。

**v0.3（2026-07-16，审计回填，R1~R6；P0 driver 修复已落地）**：
- **P0 已修**（`_workspace.py` 新建 + `_ax.py`/`_apps.py`）：①NSWorkspace 快照经 runloop spin 强制刷新（长跑 backend 此前可能永远读到进程启动时的前台 app）；②AXValueRef 全量改 `AXValueGetValue` 解包（此前存量 Atlas 数据 bounds 大量为 0）；③`dump_ax_tree(pid=...)` 支持按 pid 后台 dump。单测 1137 全过，实机验证 bounds 零值率 0~4%。
- **R1**：G1 测绘产物增加每元素 **AXActions 列表**（`AXUIElementCopyActionNames`）与菜单树落库（MenuTree 一等公民）。
- **R2**：M2 前置 **M1.5 动作原语矩阵实测**（AXSetValue/AXConfirm/AXShowMenu/AXIncrement × 各 role）——文本输入若 AXSetValue 可免焦点写入，宏执行器架构随之确定。
- **R3**：G2 增加**菜单宏类型**（menubar ax_path + AXPress/快捷键）——C 级结论细化为"窗口区不承诺，**菜单区可做确定性宏**"（WeChat 窗口区 4 交互命名 vs 菜单栏 148 命名项）。
- **R4**：driver 层统一修复已随 P0 完成（本行存档）。
- **R5**：测绘 BFS 动作黑名单（Quit/Delete/清空类 label 只记录不点击），防菜单项真实触发。
- **R6**：M2 验收量化判据=state 指纹（role,name,path）Jaccard≥0.8 判稳 + 菜单树可达率 + 动作原语覆盖率。

## 0. 定位与已有资产

| 已有 | 状态 | 复用方式 |
|---|---|---|
| `atlas/models.py` 空间模型（AtlasApp/State/Element/Transition，ax_path/menu_tree） | 建成 | 原生地图的数据格式 |
| `atlas/engine.py` 认知引擎（EventBus 摄入→分类→SQL→Agent 查询，DynamicAppTriage） | 建成（被动） | 存储与查询层 |
| `macos_driver.dump_ax_tree()`（HIServices/pyobjc 纯 Python，role/name/path/bounds 递归） | 建成 | **测绘器核心原语**（限当前前台 app，需先 activate） |
| `macos_driver.perform_ax_action(path, "AXPress")` | 建成 | **原生宏执行原语**（AXIncrement/AXSetValue 待确认扩展；文本走 type_text） |
| 桌面元素解析链 ax_tree(实时)→atlas(空间记忆)→ocr(兜底)（`_element_mixin.py`） | 建成 | 原生宏运行时的元素定位策略，生成宏内嵌 ax_path+回落此链 |
| `_trigger_atlas_harvest_macos`（AX dump→AtlasEngine 事件管道） | 建成 | 测绘落库复用 |
| `UsageRanker`（macOS 使用频度）+ Explorers LLM triage 脚手架 | 建成 | 测绘目标优先级、init_spec app_usage_rank 同源 |
| `DesktopController`（open_app/click/type_text/key_press/dump_ui/applescript） | 建成 | 原生宏执行原语 |
| 宏引擎 `native`/`applescript` 步骤 | 建成（无门） | 脚本逃生舱（G5 补门） |
| init_spec 下发通道 + 客户端 L0 匹配器/执行器 | 生产在跑 | 原生宏下发与快速道（分离构型） |
| Web 侧方法论（地图驱动/模板生成/语料准入/生成式穷举/双端 parity/运行时零 LLM） | 已验证 | 全部平移 |

**缺口三段**：主动测绘（AtlasTransition 无人产生）→ 空间地图→原生宏生成 → 下发与客户端宏执行。

**执行构型澄清（2026-07-16 补）**：DesktopController 跑在**服务端**。单机构型（backend 与语音客户端同机，当前部署形态）下原生宏可直接由服务端 DesktopController 执行，**G4 客户端宏执行器不是必需品**；仅当 backend 远程部署（客户端在他机）时才需要 G4 与 init_spec 下发通道（G3 的 native_macros 段）。两构型共用 G1/G2/G5。本设计默认先落地单机构型（成本最低的闭环），分离构型作为后续扩展。

## 1. 设计目标

### G1 主动测绘器（Atlas Native Surveyor）
- 对指定 macOS 应用**主动遍历** AX 树：菜单树 BFS + 窗口状态快照，产出 AtlasApp（states/transitions/menu_tree）入 AtlasEngine 存储。
- **按 pid dump，免焦点**（`_workspace.py` 原语）；测绘输出含每元素 **AXActions 列表**（`AXUIElementCopyActionNames`）——生成器需知道元素支持什么动作。
- **菜单树一等公民**：menubar 区与窗口区分开测绘、分开计分（菜单栏普遍完整，会掩盖内容区残缺）；C 级应用窗口区残缺时菜单区仍可出确定性宏。
- 测绘安全：默认**只读+导航类点击**；识别出的 write 动作标注但不触发（测绘沙箱）；**BFS 动作黑名单**——Quit/Delete/清空/删除类 label 只记录不点击。
- 动态应用按 DynamicAppTriage 分流：只存基础设施元素，不硬凑全图。
- 产出即 `ui_tree_observed` 事件流的系统化版本，与被动引擎同库；**state 按结构签名（role,name,path 集合）upsert，不按 app 整体覆盖**（修复存量"记忆不累积"缺陷）。

### G2 原生宏生成器（native_factory）
- 输入 AtlasApp → 生成确定性原生宏：步骤 = DesktopController 原语（open_app/AX 点击/键入/key_press/applescript）。
- **宏类型三种**：①窗口宏（窗口区 ax_path + AXPress）②**菜单宏**（menubar ax_path + AXPress/菜单快捷键——C 级应用的首选确定性路径）③键入宏（**AXSetValue 免焦点点写 + 读回验证**（M1.5 定案），CGEvent 仅作逐键/IME 场景 fallback；生成期自检=set+读回+恢复，容器内无 AXWindow 的伪字段禁用）。
- **选择器稳定性分级**：结构路径（role+index）> role+label > bounds（坐标永不单独使用）；label 不做首选（本地化漂移+动态内容漂移，Music 实测重启 Jaccard 仅 0.69）。
- **解析终点是 ax_path 不是坐标**：存量 `_resolve_element` 返回 (x,y) 坐标点击的链路逐步切换为 ax_path + `AXUIElementPerformAction`（免焦点），坐标仅兜底。
- 沿用 risk_tier（ui|data|money）：money/data-write 宏默认 pending_review + HITL。
- 生成即数据，**运行时零 LLM**；缺陷归生成器/地图，与 Web 侧同一原则。

### G3 下发通道
- VoiceInitSpec 扩展 `native_macros` 段（trigger_patterns + 步骤原语 + AX 选择器，紧凑数据格式）。
- 原生宏进 route_index（复用现有机制），decision 标 `execution_mode=client_native` → 客户端执行而非服务端 Playwright。
- 客户端 L0 匹配器可对原生宏 trigger_patterns 建快速道（规则同 §三十四五条），主路仍是 embedding+LLM。

### G4 客户端宏执行器
- LocalActionExecutor 扩展为步骤序列执行器（AX 点击/键入/AppleScript），复用现有确认流（isDestructiveAction）。
- L0 手写 `_TEMPLATES` 迁移策略：**系统级固定动作（媒体/音量/锁屏）保留手写**（无"应用"可测绘），app 内功能逐步换生成产物。

### G5 安全门（补齐既有缺口）
- `native` 步骤：解释器+脚本路径白名单 + 内容 hash 校验（生成期登记，运行时核对）。
- `applescript` 步骤：生成期静态审查（限制 tell application 范围，禁 shell 逃逸 `do shell script` 除非白名单）。
- destructive 100% 过客户端确认门；money-write 绝对值 + HITL（沿用 Web 侧规则）。

### G6 验证方法论（延续，不打折）
- 新匹配/生成逻辑必过标注语料；AX 模板×字典×语气词做生成式穷举；双端 parity。
- 真实 E2E 实测（语音→动作完成）作为验收，不接受模拟通过。

## 2. 非目标

- 不做 Android/iOS 原生（mobile 基底不动）；不做被 DynamicAppTriage 标记应用的全图。
- **不测绘浏览器内网页内容**（2026-07-16 用户确认）：Chrome/Safari 只测绘浏览器外壳（标签栏/地址栏/菜单/书签菜单），页面 DOM 操作走 Web 侧 Playwright AppMap 既有管线——两侧在"打开 URL/激活标签"处交接，原生测绘器不越界。
- 不动 Web 侧现有 103 宏管线与 L0 匹配规则。
- 不追求宏覆盖长尾——Agent 路径保持兜底，宏只做高频确定性路径。
- 不做跨应用编排（LOOP/IF 引擎路径待有模板产物再验）。

## 3. Pilot 与验收标准（可测）

**Pilot 集（v0.4 改=高频应用，2026-07-16 用户指正）**：Chrome（A，窗口+菜单双通）、iTerm2（A）、WeChat（B，菜单 168 + 窗口基础设施）、Lark/飞书（C，菜单-only）。原 Calculator/Settings/Music 仅作 M1/M2 方法论验证存档，不再作生产目标。Electron 增强开关（AXEnhancedUserInterface/AXManualAccessibility）对本机 Lark/WeChat/Chrome 设置**直接返回错误**，C 级 Electron 应用=菜单宏 + Agent/OCR 兜底，不硬撑。钉钉未安装不覆盖。

| 指标 | 标准 |
|---|---|
| 测绘覆盖 | 菜单树节点可达率 ≥90%（实测：四应用 99.7~100% ✓），产出 AtlasApp 入库存 |
| 生成宏 E2E | 每应用 ≥30 条语料，成功率 ≥95%（clarify/诚实失败不计为错误） |
| 执行延迟 | 原生宏客户端执行 <500ms（app 冷启动除外） |
| 安全 | destructive 确认门 100%；native 白名单校验 100%；AX 测绘期零 write 触发 |
| 回归 | Web 103 宏 smoke ≥29 基线；L0 140 语料全绿；后端单测全过 |

## 4. 里程碑

- **M1 可行性探测（决策点）**：✅ **go**（2026-07-16，§四十一）。9 应用 A/B/C 分级 + pilot 重启 Jaccard + 免焦点 AXPress 验证全部完成。
- **P0 driver 修复**：✅（2026-07-16）NSWorkspace 快照刷新 + AXValueRef 解包 + 按 pid dump（`_workspace.py`），存量 Atlas bounds 零值与"永远 dump 错 app"隐患消除。
- **M1.5 动作原语矩阵（决策点）**：✅ **定案**（2026-07-16，§四十二）。**文本可免焦点写入**（AXSetValue 读回 PASS：Safari 地址栏/Settings 搜索/Music 搜索/TextEdit ×18）——键入宏=AXSetValue+读回验证，CGEvent 仅 fallback；动作白名单可按 role 预填（AXButton→AXPress、AXTextField→AXConfirm、AXSlider→AXIncrement/Decrement）。**生成期自检规则**：键入宏必须现场 set+读回+恢复验证（文件名单元格伪字段 set_err=0 但静默无效）。**启动配方修订**：`open -b` 冷启动抢一次焦点，焦点敏感场景须记录-还原前台。
- **M2 主动测绘器**：✅（2026-07-16，§四十三）。`surveyor.py` 落地：菜单可达率 100%×3、三 pilot 入库（Settings 15 states/22 transitions）、state 指纹稳定、复采判据生效；修存量 bug=save_app_model 更新路径 async 懒加载崩溃。已知边界：探索为贪心链式非全 BFS。
- **M3 生成器+单 app 端到端**：✅（2026-07-16，§四十五）。native_factory（菜单宏/字段宏）+ ax_actions 运行时 + engine ax_* 步骤；582 宏生成（四应用），E2E 4/4（Chrome 地址栏写值+读回 PASS、新标签页、WeChat/Lark 菜单），全程免焦点。实战修正：字段解析 label 优先（存库 ax_path 会漂移）、Apple 根菜单跳过、枚举叶过滤、持久化幂等。
- **M4 下发+客户端执行+三应用语料实测**，安全门落地：✅ 单机构型版（2026-07-16，§四十六）。470 宏入 route_index；语料 122 条：总 74%、**qualified 95%**；执行 4/4；G5 双门（applescript 静态审查 + native 默认拒绝白名单）落地。backlog：~~bare 歧义偏置~~（✅ §四十七 native_bias，显式名+frontmost 双信号）；bare 剩余 miss 主因中英叶名不匹配→生成期英文菜单叶中文别名翻译；分离构型 G3/G4 客户端下发未做。
- **M5**：✅（2026-07-16 晚，§四十七）。评估=L0 手写模板全为系统级固定动作，按 G4 无退役；迁移产物={app} 槽词典中文别名生成化（应用菜单根标签=口语别名），微信/飞书/计算器/系统设置已入 L0 slot 词典。

## 5. 风险与开放问题

- **ax_path 漂移**：系统/app 版本更新→选择器失效。对策=复采机制+失败时诚实回落 Agent，不静默错点。M1 必须量化漂移率。
- **AX 树残缺应用**（Electron 需 AXEnhancedUserInterface）：覆盖率诚实上报，进 DynamicAppTriage，不硬撑；**C 级细化=窗口区不承诺、菜单区仍可出确定性宏**（WeChat 菜单栏 148 命名项实测）。Triage 判据从 LLM 二元分类升级为 AX 实测探针分级（可量化、可复测），LLM 降为无法 dump 时的 fallback；`get_dynamic_apps` 缓存失败应保守返回"未知按 dynamic 处理"（现行为空集=全 static，方向反了，待修）。
- **权限**：Accessibility 授权客户端已假设（init_spec capabilities.accessibility）；Input Monitoring 用于键入，首次需引导。
- **测绘副作用**：导航点击会真实改变 app 状态——测绘在专用用户会话进行，或测绘后恢复初始状态（open question：是否值得做状态快照恢复）。
- **init_spec 体积**：原生宏全量下发可能膨胀——按 app_usage_rank 裁剪 top-N，或改按需拉取（open question）。
