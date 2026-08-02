# Atlas 源码级 AppMap 设计文档

> 状态：设计稿（v2.0）· 2026-07-15
> 解决核心命题：**"第一天就宽覆盖，不等录制"**

---

## 一、Atlas 升级（新增 `source/` 子包）

### 1.1 定位

现有 Atlas 管理运行时 UI 拓扑（"这个按钮在哪？"）。新增 `source/` 子包管理源码结构（"这个项目有什么操作？"），两者互补。

### 1.2 目录结构

```
app/core/atlas/
├── __init__.py               ← 现有（不动）
├── engine.py                 ← 现有：AtlasEngine.on_ui_tree_observed（不动）
├── models.py                 ← 现有：AtlasElement / AtlasState / AtlasApp（不动）
├── strategy.py               ← 现有：AppStrategy / InteractionStrategy（不动）
├── config_manager.py         ← 现有（不动）
├── schemas.py                ← 现有（不动）
├── tasks.py                  ← 现有（不动）
├── event/                    ← 现有（不动）
├── adapters/                 ← 现有：sql_store / graph_store（不动）
└── ports/                    ← 现有：IAtlasStore（不动）
│
└── source/                   ← 新增子包
    ├── __init__.py
    ├── models.py             ← AppMap SQLModel
    ├── schemas.py            ← Pydantic 模型（供 LLM 输出/工具调用）
    ├── validate.py           ← AppMap 产出校验（schema + 回源抽检）
    ├── macro_factory/        ← 模板工厂（自 prototype/map_factory/ 移入）
    │   ├── __init__.py
    │   ├── synthesizer.py    ← 选模板 + 填槽产出 Macro 候选
    │   └── templates.py      ← 3 个模板函数
    ├── persistence.py        ← AppMap 保存/版本管理，发布领域事件
    ├── tools.py              ← Agent 工具（write_app_map 等）
    ├── subscribers.py        ← 订阅 APP_MAP_CREATED → 前端 SSE 通知（"新地图"），不触发合成
    └── event/
        ├── types.py          ← AppMapEventType（模块内事件）
        └── publishers.py     ← publish_app_map_created / superseded
```

不做 `runtime/` 搬迁——现有 atlas 平铺文件 import 众多，移动无收益。

### 1.3 AppMap 数据模型（`app_maps` 表）

一次源码调研的产出。一个项目多个实体（goods/article/user），每个实体一份地图。

```python
class AppMap(Base):
    __tablename__ = "app_maps"

    id: Mapped[int]                          # PK
    project_id: Mapped[int]                  # 所属项目，index
    entity: Mapped[str]                      # 实体名：goods / article / user
    platform: Mapped[str]                    # Agent 自报：web / android / macos / electron / cli / mixed
    aliases: Mapped[list[str]]               # ["商品","铰链","goods"] 触发别名

    # 五层结构化数据（JSON 列）
    routes: Mapped[list[dict]]        # [{name, url, method, source_action}, ...]
    actions: Mapped[list[dict]]       # [{name, kind, risk_tier, business_rule,
                                      #   touches_tables, set_fields, pk, controller, line}, ...]
    elements: Mapped[list[dict]]      # [{name, page, line, binds}, ...]
    db_tables: Mapped[list[dict]]     # [{table, pk, cols}, ...]
    extra: Mapped[dict]               # 平台特有数据

    # 版本与追溯
    map_version: Mapped[int]                 # 每次重新生成自增
    content_hash: Mapped[str]                # 内容哈希，变更检测
    generation_thread_id: Mapped[str|None]   # 生成它的 Agent 线程

    # 生命周期
    status: Mapped[str]                      # active | superseded | archived
    member_id: Mapped[int]                   # 隔离
```

关键点：
- `entity + project_id` 唯一键（map_version 用于版本回溯）
- `actions` 的 `kind`（read/write）与 `risk_tier`（ui/data/money）是模板选择和 policy 门控的输入
- `content_hash` 用于源码未变时短路重生成

### 1.4 Agent 调研管道

调研项目的事全部交给 Agent，同 `wiki.py` 模式。不通治探测/预提取加速器。

**入口 API**：

```
POST /api/v1/atlas/app-maps/generate
Body: { "project_id": 57,
        "entity": "goods",            // 必填，指定调研哪个实体
        "force_regenerate": false }

→ dispatch_agent_run(
    thread_id=f"appmap-gen-{project_id}-{entity}-{ts}",
    skill_ids=[app_map_analysis_skill.id],
    system_instructions=<输出契约：五层 schema 必填、kind/risk 合法、money 字段只吃绝对值、调 write_app_map 回写>,
    tools=[write_app_map, read_app_map, create_plan, update_step_status]
          + 只读文件工具（排除 edit_file/execute_command）,
  )
→ bg_tasks.add_task(run_agent_background)
→ 返回 {"status": "accepted", "task_id": thread_id}

POST /api/v1/atlas/app-maps/{id}/generate-macros
→ 显式触发模板工厂对该 AppMap 生成宏候选（Agent 调研自审后调，或用户点"生成宏"按钮）
→ 返回 {"status": "accepted", "task_id": thread_id}
```

**SKILL.md**（`app/config/skills/app_map_analysis/SKILL.md`）：

```yaml
name: AppMap Analysis
description: 调研项目源码结构，产出 AppMap 供模板工厂批量生成宏
trigger_patterns: ["生成源码地图", "分析项目结构", "铺满技能"]
```

内容：分阶段 SOP（扫目录 → 读关键文件 → 结构化 → 回写 → 自审完整性），含各类项目的调研关注点表（Web 看路由/控制器/DB、Android 看 Manifest/Layout、macOS 看 ViewController 等），Agent 自行参照。

**Agent 工具**（调研阶段只写不产，宏生成是独立步骤）：

```python
@evoloop_tool(is_state_mutating=True, required_benefit="app_map_generation")
async def write_app_map(entity, platform, aliases, routes, actions, elements, db_tables, config) -> str:
    """回写调研出的 AppMap。仅保存，不生成宏。"""

async def read_app_map(entity, project_id) -> str:
    """读取已有 AppMap（增量更新时比对用）"""

async def list_app_maps(project_id) -> str:
    """列出项目所有 AppMap"""

@evoloop_tool(is_state_mutating=True, required_benefit="app_map_generation")
async def generate_macros_from_app_map(app_map_id: int) -> str:
    """调研完成后显式触发模板工厂，对指定 AppMap 生成宏候选。"""
```

调研 SOP 最后一步：写完 AppMap → 自审完整性 → 调 `generate_macros_from_app_map` 产出宏。

### 1.5 产出校验（`validate.py`）

校验分两层，均确定性、无 LLM：

- **schema 校验**：必填字段、`kind ∈ {read, write}`、`risk_tier ∈ {ui, data, money}`、action 引用的表存在于 `db_tables`、route 有 url
- **回源抽检（防 AppMap 幻觉）**：actions 带 `controller`+`line`、elements 带 `page`+`line`——按行号回读源码，核对符号在该位置真实存在

返回问题列表（空=通过），不过则 `write_app_map` 拒收。

### 1.6 模板工厂（`macro_factory/`）

移入自 `prototype/map_factory/`，砍掉 `native_read`/`native_write` 形态（产品无 SQL 直连执行器），砍掉 `families.py`（三模板统一 UI macro 后无意义）。**纯 Python 代码，无 LLM**。

**模板选择**：

```python
def pick_template(action: dict) -> Template | None:
    kind, risk = action["kind"], action["risk_tier"]
    if kind == "read"  and risk == "ui":    return list_view_template
    if kind == "read"  and risk == "data":  return crud_read_template
    if kind == "write" and risk == "money": return crud_write_template
    return None  # 不符模板 → 不合成，留给飞轮
```

**三个内置模板**（统一产出 UI 步骤 `macro_script` YAML）：

| 模板 | 匹配条件 | 产出 | 确认门 |
|------|---------|------|--------|
| `list_view` | kind=read, risk=ui | 打开列表 URL → 搜索 → 提取结果表 | 无 |
| `crud_read` | kind=read, risk=data | 打开详情/列表 → 提取目标字段值 | 无 |
| `crud_write` | kind=write, risk=money | 打开编辑页 → 填绝对值 → 保存 | **强制** |

**接地规则**：模板只实例化 AppMap 里**存在**的条目。宏每一步的 URL / target_selector / 字段名必须能解析到具体 AppMap 条目（`routes[].name`、`elements[].name`、`db_tables[].cols`）。模板内**禁止字面量目标**（原型里 `target_selector: "搜索框"` 必须改为从 `elements` 按 role 查找）。任一槽位缺失 → 该动作**弃产**，记入 `coverage_report.gaps` 留给飞轮，绝不脑补。

**产出校验**（`synthesize()` 后执行）：
1. **接地检查**：每步的 URL/selector/字段均可解析到 AppMap 条目
2. **结构合法**：`MacroScript.parse()` 能正常解析，至少有 1 步

校验失败的宏候选不入库，记入 `validation_report`。



## 二、Macro 从 Learning 独立

### 2.1 现状问题

当前宏作为 `LearnedSkill` 的字段存在（`learned_skills.macro_script`），一个记录同时存 SOP + YAML 脚本。
概念不干净：技能是 LLM 读的 SOP，宏是引擎回放的 YAML 脚本，两者不应共享同一张表。

### 2.2 Macro 数据模型（`macros` 表）

独立存放于 `execution/macro/models/macro.py`：

```python
class Macro(Base):
    __tablename__ = "macros"

    id: Mapped[int]                          # PK
    app_map_id: Mapped[int|None]          # FK → app_maps.id（可空；NULL = 飞轮沉淀的宏）
    entity: Mapped[str|None]                 # 冗余实体名，便于查询

    # 宏定义
    name: Mapped[str]                        # "查看商品列表"
    description: Mapped[str]
    trigger_patterns: Mapped[list[str]]      # ["查看{{query}}商品", ...]
    parameters: Mapped[list[dict]]           # [{name, type, required, description}]
    macro_script: Mapped[str]                # YAML（MacroScript 可解析）
    risk_tier: Mapped[str]                   # ui / data / money
    requires_confirmation: Mapped[bool]      # money 级强制确认门

    # 生命周期
    status: Mapped[str]                      # pending_review | verified | obsolete
    is_active: Mapped[bool]                  # verified 才为 True
    namespace: Mapped[str|None]

    # 配对与溯源
    fallback_skill_id: Mapped[int|None]      # FK → learned_skills.id，飞轮配对的兜底心法
    source_thread_id: Mapped[str|None]       # 合成来源 trace 线程

    project_id / member_id / created_at / updated_at
```

关键点：
- `app_map_id` 是追溯字段：项目改版时 `WHERE app_map_id = 旧id` 整批置 `obsolete`
- 飞轮宏 `app_map_id=NULL`，与 AppMap 宏共存互不影响，不被地图重生成冲掉
- `macro_script` 沿用现有 YAML 格式（`MacroScript.from_yaml()` 可解析），执行引擎零改动

### 2.3 生命周期

**状态机**：

```
[模板厂生成] → pending_review (is_active=False)
      ↓ 用户确认（单个/批量）
   verified (is_active=True) ──→ 进入 RouteIndex
      ↓ 项目改版，重新生成 AppMap
   obsolete (is_active=False) ──→ 从 RouteIndex 移除（保留审计）
```

飞轮沉淀的宏走同样状态机，但 `app_map_id=NULL`，永不因 AppMap 重生成而 obsolete。

**增量更新**（事件驱动）：

```
项目改版
  → POST /atlas/app-maps/generate (force_regenerate=true)
  → Agent 重新调研 → 新 AppMap（map_version+1, content_hash 变化）
  → 旧 AppMap status=superseded → publish APP_MAP_SUPERSEDED
      → macro subscriber: 旧 map 的宏批量 obsolete → publish MACRO_OBSOLETED
  → 新 AppMap 入库 → publish APP_MAP_CREATED
  → Agent 调研完成后调 generate_macros_from_app_map(新id)
      → 批量 INSERT 新宏（pending_review）→ publish MACRO_CREATED
  → 用户批量确认 → publish MACRO_UPDATED
  → routing subscriber 防抖 rebuild（只回捞 verified 宏）
```

**CRUD API**（与 `/api/v1/learning/skills` 对称）：

```
GET    /api/v1/macros?project_id=&app_map_id=&status=
GET    /api/v1/macros/{id}
PUT    /api/v1/macros/{id}                              ← 编辑名称/触发语/参数/YAML
DELETE /api/v1/macros/{id}                              ← publish_macro_mutated("delete")
POST   /api/v1/macros/{id}/confirm                      ← 单个确认
POST   /api/v1/macros/confirm-bulk                      ← 批量确认 {macro_ids:[...]}
POST   /api/v1/macros/{id}/execute                      ← 手动执行
```

所有状态变更走 `publish_macro_mutated` → routing subscriber 防抖 rebuild（Worker 唯一写者），不做内联索引写入。

### 2.4 迁移（兼容期策略）

存量 `learned_skills` 中 `execution_mode='deterministic'` 且有 `macro_script` 的记录：

1. `macro_script` 搬入 `macros` 表（`app_map_id=NULL`, `status='verified'`, `is_active=True`）
2. `fallback_skill_id` 指回原技能行——老技能的心法保留在 `learned_skills`
3. 原技能行 `execution_mode` 改 `agentic`（只留心法），或标记 deprecated 自然淘汰
4. `learned_skills.macro_script` 和 `execution_mode` 字段保留不删（兼容期），前端列表过滤只显示 agentic 技能

迁移后：`learned_skills` 只存 SOP（agentic）；`macros` 存 YAML 脚本（deterministic）。概念干净。

### 2.5 事件契约

**模块内事件**（`atlas/source/event/types.py`）：

```python
class AppMapEventType(str, Enum):
    CREATED    = "atlas.app_map.created"
    SUPERSEDED = "atlas.app_map.superseded"
```

payload：`{app_map_id, project_id, entity, map_version, content_hash, thread_id}`

**跨域事件**（加入 `core/events/registry.py` 的 `SystemEventType`）：

```python
MACRO_CREATED   = "learning.macro_created"
MACRO_UPDATED   = "learning.macro_updated"
MACRO_DELETED   = "learning.macro_deleted"
MACRO_OBSOLETED = "learning.macro_obsoleted"
```

配套 `core/events/publishers.py` 新增 `publish_macro_mutated(macro_id, action)`，镜像现有 `publish_skill_mutated`。

**订阅关系**：

| 事件 | 订阅者 | 动作 |
|------|--------|------|
| `APP_MAP_CREATED` | `atlas/source/subscribers.py` | 前端 SSE 通知（"新地图已保存"），**不触发合成** |
| `APP_MAP_SUPERSEDED` | `execution/macro/event/subscribers.py` | `lifecycle.mark_obsolete_by_app_map(old_id)` → 逐条 `publish_macro_mutated("obsolete")` |
| `MACRO_CREATED/UPDATED/DELETED/OBSOLETED` | `routing/subscribers.py::InitSpecRefreshSubscriber` | 防抖 `rebuild_route_index`（Worker 唯一写者，与 skill 同一约定） |

### 2.6 飞轮双写

现有 `WorkflowSynthesizer.synthesize()` 一次运行产出**一对制品**——心法（`instructions` SOP）+ 宏脚本（`macro_script` YAML）。两者是配对关系：

```python
# create_from_synthesis() 改造
skill_id = None
if instructions:                                          # 心法 → 技能包
    skill_id = await create_skill(...)                    # → learned_skills

if macro_script and verification_passed:                  # 宏 → 宏表
    await create_macro_from_synthesis(
        fallback_skill_id=skill_id,                       # 链接心法
        source_thread_id=thread_id,
        app_map_id=None,                                  # 飞轮宏无地图
    )                                                     # → macros
```

配对的价值：
- 宏执行失败 → 自愈触发 → Agent 读 `macro.fallback_skill_id` 对应技能的 SOP 做恢复
- AppMap 模板宏无配对（`fallback_skill_id=NULL`），失败时走通用 Agent 兜底
- 飞轮宏带心法，失败时恢复质量更高

**三条管道修改**：

| 管道 | 改动 |
|------|------|
| `record_episode_task` | 双写：心法→skills，宏→macros（`fallback_skill_id` 链接） |
| `learn_from_trace` 工具 | 同上 |
| `reconcile_skill_macro_task` | 修复对象定位改为宏表；同时可顺链更新 `fallback_skill_id` 对应技能 |

---

## 三、流程链路

### 3.1 生成链路（调研 → 宏产出）

```
Agent 读源码
  → write_app_map → persistence.save_app_map()           ← 只存地图，不产宏
      → publish APP_MAP_CREATED                           ← 前端通知"新地图已保存"

  → Agent 自审完整性后，调 generate_macros_from_app_map(app_map_id)   ← 显式触发
  （或用户在前端点"生成宏"按钮 → POST /app-maps/{id}/generate-macros）
      → macro_factory.synthesize()
          → pick_template() for each action
          → templates fill slots from AppMap
          → run 2 checks (grounding + structural)
          → lifecycle.persist_candidates()
              → batch INSERT macros (pending_review)
              → publish MACRO_CREATED
                  → routing subscriber 防抖 rebuild RouteIndex
              → SSE 推前端"N 个新宏待确认"
```

**关键决策**：写地图和产宏是两步。AppMap 是调研中间产物，Agent 需要时间自审完整性；
Agent 确认完整后调 `generate_macros_from_app_map` 一次或分批生成宏。

### 3.2 执行链路（语音/Agent/前端 → 设备执行）

#### 路径 A：语音路由（主要路径）

```
用户语音 → macOS 客户端 ASR
  → {type: "voice.route", body: {text: "查商品列表", thread_id}} over WS
  → voice_ws.py:_handle_route()
      ├─ retriever.retrieve(text, top_k=20)         ← 向量搜索 RouteIndex
      │   候选含 4 种 type: local / skill / macro / agent
      ├─ router.route(req, candidates)
      │   → 渲染 route.prompt.j2 → 路由 LLM（tool_choice="required"）
      │   从 4 工具中选：
      │   · execute_macro(macro_id, params)          ← 命中宏
      │   · execute_skill(skill_id, params)           ← 命中技能
      │   · local_action(action, params)              ← 本地动作
      │   · delegate(task)                            ← 兜底 Agent
      │   → _from_tool_call() 验证 id 在候选集
      │   → RouteDecision{target_type: "macro", target: {id: macro_id}}
      ├─ push voice.route_result 回客户端
      └─ executor.execute(thread_id, decision)
           → target_type="macro"
           → _run_macro():
               load_macro(id)
               gate: is_active + status=verified + params check
               VOICE_POLICY: family/risk scan
               money + requires_confirmation → HITL 确认门
               write macro_id to session.metadata     ← 供自愈 reconcile
               MacroScript.from_yaml() → MacroService.run()
               → MacroEngine.execute_steps()
               → push_voice_result(done|failed)
```

#### 路径 B：聊天 Agent 调用

```
Worker LLM 在对话中：
  → 识别到需要已有宏 → list_macros() 浏览
  → run_macro(macro_id, params)
      → domain/tools/execution/macro.py
          → 查 macros 表（兼容期回退查 learned_skills）
          → MacroService.run()
```

#### 路径 C：前端手动执行

```
用户点击"执行"按钮
  → POST /api/v1/macros/{id}/execute
      → API handler 直接调 MacroService.run()
```

三条路径汇于 `MacroService.run()`，执行引擎零区别。

### 3.3 飞轮链路（兜底执行 → 沉淀）

```
Agent 兜底执行（无现成宏）
  → 完成任务 → SESSION_COMPLETED
  → record_episode_task
      → WorkflowSynthesizer.synthesize()
          → 产出 {instructions, macro_script} 一对
          → create_from_synthesis() 双写：
              instructions → learned_skills（心法）
              macro_script → macros（宏，fallback_skill_id 链接）
      → publish_macro_mutated("create")
          → routing subscriber 防抖 rebuild RouteIndex
```

---

## 四、改造清单

### 4.1 新建文件

**Atlas source/**：
| 文件 | 用途 |
|------|------|
| `app/core/atlas/source/__init__.py` | 子包初始化 |
| `app/core/atlas/source/models.py` | AppMap SQLModel |
| `app/core/atlas/source/schemas.py` | Pydantic 模型（LLM 输出/工具调用） |
| `app/core/atlas/source/validate.py` | schema 校验 + 回源抽检 |
| `app/core/atlas/source/persistence.py` | save/load/version management + 发布事件 |
| `app/core/atlas/source/tools.py` | write_app_map / read_app_map / list_app_maps / generate_macros_from_app_map |
| `app/core/atlas/source/subscribers.py` | 订阅 APP_MAP_CREATED → 前端 SSE 通知 |
| `app/core/atlas/source/event/__init__.py` | |
| `app/core/atlas/source/event/types.py` | AppMapEventType |
| `app/core/atlas/source/event/publishers.py` | publish_app_map_created / superseded |
| `app/core/atlas/source/macro_factory/__init__.py` | |
| `app/core/atlas/source/macro_factory/synthesizer.py` | 选模板 + 填槽 + 校验 → 候选 |
| `app/core/atlas/source/macro_factory/templates.py` | 3 模板函数 |
| `app/config/skills/app_map_analysis/SKILL.md` | 调研 SOP |

**Macro 独立**：
| 文件 | 用途 |
|------|------|
| `app/core/execution/macro/models/__init__.py` | |
| `app/core/execution/macro/models/macro.py` | Macro SQLModel |
| `app/core/execution/macro/lifecycle.py` | persist/confirm/bulk-replace/load_macro |
| `app/core/execution/macro/migration.py` | 存量老宏 → 新表迁移 |
| `app/core/execution/macro/tasks.py` | synthesize_macros_task（Huey） |
| `app/core/execution/macro/event/subscribers.py` | 订阅 APP_MAP_SUPERSEDED → 批量 obsolete |

**路由**：
| 文件 | 用途 |
|------|------|
| `app/domain/tools/execution/list_macros.py` | 新 Agent 工具 |
| `app/api/routes/macros.py` | 宏 CRUD API |

**提示词**：
| 模板 | 修改 |
|------|------|
| `app/config/templates/core/engine/fragments/macro_block.j2` | 新建，Worker ticket 宏片段 |

### 4.2 修改文件

| 文件 | 改动 |
|------|------|
| `app/core/routing/sync.py` | 新增 `_macro_entries()`，`rebuild_route_index()` 加入 |
| `app/core/routing/router.py` | `ROUTE_TOOLS` 加 `execute_macro`；`_from_tool_call()` 加分支；幻觉 → delegate |
| `app/core/routing/executor.py` | 新增 `_run_macro()`（含 macro_id→session.metadata）；`execute()` 加 `"macro"` 分支 |
| `app/core/routing/schemas.py` | `RouteDecision.target_type` 注释更新（local/skill/agent/macro） |
| `app/core/events/registry.py` | `SystemEventType` 加 `MACRO_*` |
| `app/core/events/publishers.py` | 加 `publish_macro_mutated()`（镜像 publish_skill_mutated） |
| `app/core/learning/skill_synthesizer.py` | `create_from_synthesis()` 双写分流 |
| `app/core/learning/skill_lifecycle.py` | 同上（接收双写参数） |
| `app/domain/tools/execution/macro.py` | `run_macro` 改为查 `macros` 表（兼容期回退 learned_skills） |
| `app/config/templates/core/routing/route.prompt.j2` | 加 `execute_macro` 第 4 工具 |
| `app/config/templates/core/engine/fragments/supervisor_context_ticket.j2` | 加 `## Available Macros` 独立段 |
| `app/config/templates/core/engine/fragments/worker_mission_ticket.j2` | 加 `## Attached Macros` + `## Project Operation Map` 段 |
| `app/config/templates/core/engine/fragments/worker.prompt.j2` | 加 `list_macros` 工具行 + "宏是确定性脚本，不要逐步跟随" 一句 |
| `app/core/engine/graph_runner.py` | `_restore_resume_context()` hydrate `active_macros` |

### 4.3 删除/归档

| 路径 | 原因 |
|------|------|
| `prototype/map_factory/families.py` | 死代码，模板统一 UI macro 后无意义 |
| `prototype/map_factory/`（其他文件） | 验证完成，代码移入 `atlas/source/macro_factory/`，原型归档 |

### 4.4 依赖关系与排期

```
P1 数据层     ─→ P2 事件桥 ─→ P4 生成管道 ─→ P8 验证
                             ├→ P3 路由打通 ──→ P5 Agent 上下文
                             └→ P6 飞轮分流
P3 ─→ P7 前端
```

| Phase | 内容 | 依赖 | 预估 |
|-------|------|------|------|
| P1 | `app_maps` + `macros` 建表 + SQLModel（Alembic migration）；模板工厂移入（砍 native_read/native_write 形态、砍 families.py） | 无 | 1d |
| P2 | AppMap/Macro 事件类型 + `publish_macro_mutated`；`lifecycle.py`；老宏迁移脚本 | P1 | 1d |
| P3 | `sync.py` `_macro_entries()`；`route.prompt.j2` + router 加 `execute_macro`；`executor.py` `_run_macro()`（含 `macro_id`→metadata）；`run_macro` 工具改查宏表 | P1 | 1d |
| P4 | `write_app_map` + `generate_macros_from_app_map` 工具；`validate.py`；生成 API + 宏 CRUD API；SKILL.md；APP_MAP_CREATED 订阅（仅 SSE）；宏生成 Huey 任务 | P2 | 2.5d |
| P5 | `list_macros` 工具；supervisor/worker ticket 独立段 + Project Operation Map；`worker.prompt.j2` 宏说明；resume hydrate | P3 | 1d |
| P6 | `create_from_synthesis()` 分流 deterministic→macros | P2 | 0.5d |
| P7 | macros 标签页（分组 + 批量确认 + 重新生成 + 批量生成入口 + SSE 进度） | P3 | 1.5d |
| P8 | 商城项目实测：生成 → 确认 → 语音执行 | 全部 | 1d |

---

## 附录 A：风险与决策

| 风险 | 缓解 |
|------|------|
| AppMap 质量不稳定（Agent 幻觉） | SKILL.md 强约束 SOP + `validate.py` 双层校验（schema + 回源抽检）+ 模板厂接地检查，不合格不入库 |
| 模板/宏引用不存在的数据 | 三道闸：①回源抽检打幻觉 AppMap ②接地规则禁字面量目标 ③pending_review 人工确认 + 首跑失败走自愈 |
| Agent 调研单个实体质量可控，多实体长跑"疲劳" | 单实体调研独立 Agent 任务，上下文窄、目标短，完成率高；多实体分别调度即可 |
| 模板 3 个覆盖率不够 | 诚实边界：复杂流走飞轮。后续按需加模板即可（注册函数 + 选型规则） |
| 老 learned_skills 存宏与独立宏表并存期混乱 | 兼容字段保留（不删），迁移脚本搬数据，前端过滤只显 SOP 技能，逐步淘汰 |
| LLM 路由在宏量大时选错 | `top_k=20` 限制 + trigger_patterns 嵌入 + 命名空间分组 |
| money 级宏的安全 | `requires_confirmation=True` 强制 HITL 确认门（执行器自动触发 UI 弹窗）；`VOICE_POLICY` 门控 family/risk |

## 附录 B：与现有系统的关系

| 模块 | 关系 |
|------|------|
| `atlas/` 现有平铺文件（engine/models/strategy/adapters） | **不动**。不做 runtime/ 搬迁 |
| `core/execution/macro/` | 存储层扩展：models/ + lifecycle/migration/tasks；执行引擎零改动 |
| `core/events/` | 桥接层：`SystemEventType` + `publish_macro_mutated`（镜像 skill 模式） |
| `learned_skills` | 保留，只管 agentic 技能。宏字段兼容期后淘汰 |
| 飞轮（synthesizer/tasks） | 写目标分流（双写），逻辑不变 |
| RouteIndex | 加 `type="macro"` 条目；写入仍只走 Worker 防抖重建 |
| `prototype/map_factory/` | 三模板代码移入 macro_factory/，原型归档 |

## 附录 C：词汇表

| 术语 | 定义 |
|------|------|
| AppMap | Agent 调研项目源码产出的结构化数据（五层：routes/actions/elements/db_tables/extra） |
| Macro | 确定性 YAML 步骤脚本，`MacroService.run()` 整体回放，LLM 不读内容 |
| Skill | SOP 指令集（Markdown），LLM 逐步阅读并跟随 |
| 模板工厂 | 纯 Python 代码，读 AppMap → 选模板 → 填槽 → 出 Macro 候选 |
| 接地规则 | 模板每步的目标必须解析到 AppMap 条目，缺槽位弃产记 gap |
| 回源抽检 | validate 按行号回读源码核对 action/element 是否真实存在 |
| 飞轮双写 | 一次合成同时产出心法（→skills）和宏（→macros） |
