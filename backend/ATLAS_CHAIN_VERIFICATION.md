# Atlas 源码级 AppMap 后端验证报告

日期：2026-07-15（当日二更） ｜ 范围：P1–P6 后端链路 + P4 工具入口 + LLM 真实调研（不含 P7 前端、真机语音）
环境：macOS arm64 / Python 3.11.15 / 项目 venv / scratch SQLite（`SQLITE_PATH` 环境变量隔离，不碰开发库）
LLM：qwen-plus（DashScope，密钥取自 `evoloop/.env` 的 `DASHSCOPE_API_KEY`）

---

## 一、验证总览

| # | 验证项 | 方式 | 结果 |
|---|--------|------|------|
| 1 | Alembic migration 双向可用 | scratch SQLite 上 upgrade/downgrade | ✅ |
| 2 | P5 上下文注入（模板 + DB 函数） | 模板渲染脚本 + 真实 DB 查询 | ✅ |
| 3 | P6 飞轮双写 + 顺链修复 | 真实 DB 端到端脚本 | ✅ |
| 4 | 全链路（手工 payload → 地图 → 宏 → 路由 → 执行门） | `tests/manual/test_atlas_macro_chain.py`，12 步 | ✅ |
| 5 | P4 工具入口（注册表真实调用） | `tests/manual/test_atlas_p4_tool_entry.py`，8 步 | ✅ |
| 6 | P2 老宏迁移脚本 | 3 种技能形态 + 幂等二跑 | ✅ |
| 7 | LLM 真实调研（qwen-plus 读真实源码产地图） | `tests/manual/test_atlas_llm_survey.py`，4 步 | ✅ |
| 8 | 单元测试回归 | `pytest tests/unit -q` | ✅ 994 passed, 7 skipped |
| 9 | Lint/格式 | `ruff check` / `ruff format` | ✅ 本次改动文件干净 |

---

## 二、Migration 验证

### 指令
```bash
export SQLITE_PATH=/var/folders/.../opencode/atlas_mig_test.db
.venv/bin/python -m alembic stamp 7c9a0b1d2e3f   # 跳过存量链
.venv/bin/python -m alembic upgrade head          # 只跑新 migration
.venv/bin/python -m alembic downgrade -1          # 验证可逆
.venv/bin/python -m alembic upgrade head          # 再装回
```

### 结果
- `a1b2c3d4e5f6_add_app_maps_and_macros.py`（down_revision=`7c9a0b1d2e3f`，已核实为仓库真实 head）
- `app_maps` 18 列、`macros` 20 列全部正确创建；downgrade 后两表消失；可重复 upgrade

### 发现的存量问题（非本次改动）
- baseline `cb2eace845a1` 含 `CREATE EXTENSION vector`（pgvector，Postgres 专属）→ SQLite 全链迁移在 baseline 就失败，项目实际以 Postgres 为准
- venv 脚本 shebang 失效（目录从 `项目/` 改名为 `Projects/`），`bin/evo`、`alembic` 直接调用报 `bad interpreter`，需用 `.venv/bin/python -m alembic` 绕过

---

## 三、P5 上下文注入验证

### 3.1 模板渲染（3 个用例，内联 render_template）
- supervisor ticket 传入 `active_macros=[{id:7, name:'goods.edit', ...}]` → 出现 `## Available Macros` 段和 `goods.edit (ID: 7)`
- worker ticket 传入宏 + operation_map → 出现 `## Attached Macros` + `## Project Operation Map` + `editGoods`
- 空数据 → 两段均不渲染（不产生空标题）

### 3.2 DB 函数（真实初始化 db_resource_manager + create_tables）
测试数据：1 张 active AppMap（entity=goods，含 1 route + 2 action）+ 3 个宏（项目1-verified、项目1-pending_review、项目2-verified）

| 断言 | 结果 |
|------|------|
| `operation_map_summary(1)` 含 `### goods (platform: admin, map v1)`、`editGoods [write/money] — 改价需审核`、`GET /goods/list` | ✅ |
| `operation_map_summary(99)` 返回空串 | ✅ |
| `list_active_macro_index(project_id=1)` 只返回 1 条（verified+active；排除 pending 和其他项目） | ✅ |

---

## 四、P6 飞轮双写验证

真实 DB 脚本：单 session 内 `create_from_synthesis()`（技能）+ `create_macro_from_synthesis()`（宏）。

| 断言 | 结果 |
|------|------|
| `macro.fallback_skill_id == skill.id`（心法链接） | ✅ |
| `macro.app_map_id is None`（飞轮宏无地图，不被重新调研废弃） | ✅ |
| 落地状态 `pending_review` + `is_active=False`（待人工确认） | ✅ |
| `normalize_parameters` 把 SkillParameter 对象归一为 `{'name','type','description','required','default'}` 纯 dict（JSON 列可序列化） | ✅ |
| 顺链修复查询 `WHERE fallback_skill_id=skill.id` 命中 1 条 | ✅ |

---

## 五、全链路验证（核心）

脚本：`tests/manual/test_atlas_macro_chain.py`
指令：`.venv/bin/python tests/manual/test_atlas_macro_chain.py`

### 5.1 测试数据来源（全部为 member-center/backend 真实代码，非编造）

| 条目 | 文件 | 行号 | 实际内容 |
|------|------|------|----------|
| action `lists` | `app/shop/controller/Goods.php` | 50 | `public function lists()` |
| action `editGoods` | 同上 | 430 | `public function editGoods()` |
| action `getGoodsSkuList` | 同上 | 760 | `public function getGoodsSkuList()` |
| element `search_text` | `app/shop/view/goods/lists.html` | 42 | `<input name="search_text" placeholder="请输入商品名称">` |
| element `goods_list` | 同上 | 169 | `<table id="goods_list" lay-filter="goods_list">` |
| element `price` | `app/shop/view/goods/edit_goods.html` | 342 | `<input name="price" lay-verify="price">` |
| element `save` | 同上 | 693 | `<button lay-filter="save">保存</button>` |
| 数据表 `goods` | `b2c_mall.sql` | 9042 | `CREATE TABLE \`goods\`` |

行号通过 `grep -n "public function" Goods.php` 和 `grep -n` 元素符号实际定位。

### 5.2 AppMap payload
entity=`goods` / platform=`admin` / 3 routes（`source_action` 回指 action）/ 3 actions（read-ui、write-money、read-data 各一，覆盖全部 3 个模板）/ 4 elements / 1 db_table

### 5.3 12 步实测输出

```
[1] validate_app_map: 真实引用全部通过（schema + 回源抽检）
[2] 幻觉条目被拒: action 'flyToMoon' 在 Goods.php:10 附近未找到（疑似幻觉条目）
[3] save_app_map: id=1 v1
[4] synthesize: 3 个候选宏 ['查看{query}goods', '改{query}goods价格', '查{query}goods价格']（money 宏带确认门）
[5] persist_candidates + confirm_bulk: [1, 2, 3]
[6] list_active_macro_index: 3 条活跃宏
[7] sync._macro_entries: 3 条 macro 进入路由索引
[8] _run_macro(list_view): done, 6 步脚本, 参数注入正确
[9] money 确认门: confirm_required — 宏「改{query}goods价格」涉及资金操作
[10] 缺参门拦截: 缺少参数: query
[11] 删除后拦截: macro #2 not found
[12] 重新调研 v2 → 旧图宏批量 obsolete (2 条)，活跃索引清空
```

### 5.4 各步验证点
- **[1] 双层校验**：schema 检查（kind/risk 枚举、touches_tables 引用完整性）+ 回源抽检（重读源码文件，±10 行窗口内必须含所引符号）
- **[2] 反幻觉**：伪造 action `flyToMoon`（controller 真实但符号不存在）被拒
- **[4] 模板接地**：`lists`→list_view（6 步：navigate→wait→click→input→key_press→extract）；`editGoods`→crud_write（4 步 + `requires_confirmation=True`）；`getGoodsSkuList`→crud_read（3 步）
- **[8] 执行链路**：`_run_macro` 加载 → is_routable 门 → 参数检查 → MacroScript.from_yaml → VOICE_POLICY 扫描 → MacroEngine.execute（mock 掉浏览器层），断言 `_macro_id`/`_macro_name`/业务参数注入正确
- **[9] money HITL**：推送 `confirm_required` 状态，**不执行**
- **[12] 级联废弃**：同 entity 内容变化重存 → 旧图 superseded → `mark_obsolete_by_app_map` 废弃 2 条旧宏

### 5.5 验证暴露并修复的 2 个缺口

**缺口 1：VOICE_POLICY 误拒 DOM 宏**
- 现象：步骤 8 首次失败 `unsupported macro source for voice: ['dom']`
- 原因：`allowed_sources=frozenset({"desktop"})` 早于 Atlas，而模板厂全部产出 `source: dom`
- 修复：`app/core/execution/macro/runner.py:58` 加入 `"dom"`；mobile 仍拒（既有测试 `test_voice_policy_rejects_mobile_source` 继续通过）

**缺口 2：requires_confirmation 只存不管**
- 现象：全代码库无任何执行路径读取该字段
- 修复：`app/core/routing/executor.py:173` money+requires_confirmation → 推 `confirm_required` 不执行
- 可达性确认：`action_risk` 表中 `input=data`/`click=act`，money 宏步骤风险 ≤ VOICE max(data)，能到达确认门（门不是死代码）

### 5.6 过程中发现并修正的测试自身问题
- element `name` 必须是源码中**字面存在的符号**：首版用描述名 `价格输入框`/`保存按钮` 被回源抽检正确拒绝（恰恰证明校验有效），改为真实符号 `price`/`save`

---

## 六、单元测试

```bash
.venv/bin/python -m pytest tests/unit -q
# 994 passed, 7 skipped (跳过项均为 neo4j/celery 可选依赖缺失，与本次无关)
```

新增单测：
- `tests/unit/core/routing/test_router_macro.py::TestRunMacroGates`（2 个：money 确认门 / dom 通过 source 门）
- `tests/unit/core/atlas/test_source_macro_factory.py`（2 个：重名加后缀 / 英文 list 符号接地）
- `tests/unit/core/atlas/test_source_validate.py::TestBindsCoercion`（2 个：binds list 归一）

P1–P4 已有 25 个单测（模板厂、validate、router 分支）同步回归通过。

---

## 七、Lint / 格式

- `ruff format`：本次全部改动文件已格式化
- `ruff check`：本次新文件/改动文件零告警
- 仓库存量 2688 个 lint 问题（W293 空白等）和 pyright shebang 损坏均为既有问题，未触碰

---

## 八、P4 工具入口验证（注册表真实调用路径）

脚本：`tests/manual/test_atlas_p4_tool_entry.py`（8 步，经 `get_tool_map()` 注册表调用，模拟 Agent 实际执行路径，EvoContext 注入 project_id=77 + working_directory=member-center/backend）

1. 4 个工具在注册表可见（`REGISTRY.scan("app.core.atlas.source")` 生效）
2. `write_app_map` 拒绝幻觉 payload（fakeAction @ Goods.php:10，未落库）
3. 真实 payload 落库 v1
4. `read_app_map` / `list_app_maps` 正常（`generation_thread_id` 溯源正确）
5. `generate_macros_from_app_map` → Huey 派发参数正确（app_map_id/project_id/member_id）
6. 任务体执行产出 2 个 pending_review 候选（未确认不可路由）
7. superseded 地图被拒生成（仅 active 可生成）

**修复的 bug**：`read_app_map` 给 `ControllerResponse.success(details=...)` 传 dict，但模板要求 str（`.strip()` 报错）——已改为 YAML 序列化（tools.py:104）。

## 九、P2 老宏迁移脚本验证

数据：3 个 learned_skills 行——deterministic+macro_script(verified) / deterministic+macro_script(pending) / agentic 纯心法。

| 断言 | 结果 |
|------|------|
| 首跑 migrated=2，publish_macro_mutated ×2 | ✅ |
| verified→宏 verified+is_active（可路由）；pending→pending_review（不可路由） | ✅ |
| 源技能 `execution_mode` 翻回 `agentic`（心法保留，宏独立） | ✅ |
| 纯心法技能不受影响 | ✅ |
| 二跑零迁移零新增（幂等，靠 mode 翻转实现） | ✅ |

## 十、LLM 真实调研验证（qwen-plus + member-center 真实源码）

脚本：`tests/manual/test_atlas_llm_survey.py`。prompt = SKILL.md 契约 + 真实源码（Goods.php 前 800 行 + lists.html + edit_goods.html 全文 + goods 表 DDL，**带行号前缀**）。

### 最终轮结果
- LLM 产出 15 actions / 55+ elements / 15 routes / 4 tables
- `validate_app_map`：**schema + 回源抽检零幻觉通过**（所有行号精确命中 grep ground truth：50/286/430/591/645/658/672/687/702/718/737/760/777）
- 落库 v1 → 模板厂 **8 候选宏 / 7 诚实 gap**（deleteGoods 等缺 set_fields/元素，如实留飞轮）
- 重名宏正确加后缀：`改{query}goodsgoods_name（editGoods）`、`查看{query}goods（recycle）`

### 迭代过程（3 轮暴露 4 个真实问题并修复）
| 轮次 | 暴露问题 | 修复 |
|------|----------|------|
| R1 | LLM 自行数行号，系统性偏移 40-60 行，59 条引用被抽检拒 | 测试侧改喂带行号文件（对齐 Agent 用 view_file/grep 的真实条件），非产品缺陷 |
| R2 | LLM 把 `binds` 产出为 list，AppMapPayload 56 个校验错误 | schemas.py 加 `field_validator` 自动 list→str 归一 |
| R3a | `goods_list` 元素 binds=['lay-filter'] 缺中文语义，模板关键字不命中 → 接地失败 | templates.py list_view 结果关键字 += `"list"`（英文符号） |
| R3b | 同名宏重复（addGoods/editGoods 共享 set_fields[0]） | synthesize.py 重名加 `（source_action）` 后缀 |
| R3c | 一轮 LLM 漏收搜索框/结果表/保存按钮 → 0 候选（诚实 gap，行为正确） | SKILL.md 补强制性元素收录要求（搜索框/结果表格/保存按钮/写字段） |

## 十一、原型归档（§4.3）

- `prototype/map_factory/` → `prototype/archive/map_factory/`
- `families.py` 已删（死代码）；归档为只读快照（含一处对 families 的悬挂 import，不用于运行）
- 生产代码 `atlas/source/macro_factory/` 无 families 依赖

---

## 十二、未覆盖项（后续）

| 项 | 阶段 | 说明 |
|----|------|------|
| ~~macros 前端标签页~~ | P7 | ✅ v1 已完成：`MacroLibraryView.tsx`（实体分组/批量确认/重新生成/参数化执行/脚本详情），learning 页新增"宏库"标签；SSE 进度与项目过滤留作后续 |
| 真机语音执行 | P8 | 需运行中的商城后台 + 浏览器环境，执行真实 navigate/click |
| ~~全引擎 Agent 会话调研~~ | P8 | ✅ 已完成，见 §十三 §十四 |
| 路由 LLM 实选 execute_macro | P3 | 单测覆盖 tool_call 解析，未跑真实 LLM 路由 |
| LLM 调研质量方差 | - | 已由机械采集方案解决（§十四），引用全部机器计算 |
| ~~宏命名可读性~~ | - | ✅ `templates.py` 引入 `_entity_cn`/`_field_label`/`_readable_subject`，产物为 `改{query}商品名称`/`查看{query}商品` 形态 |
| ~~采集策略沉淀~~ | - | ✅ SKILL.md Survey Procedure 已改为机械采集流程（侦察→一次性采集脚本→语义富化→逐实体提交） |

---

## 十三、生产路径全生命周期验证（2026-07-15，P8 核心）

**脚本**：`tests/manual/test_atlas_survey_lifecycle.py`（对齐 wiki 生命周期模式：真实 dev DB + EvoCloud 登录 + awaken + dispatch_agent_run + 真实 Huey worker 子进程，无任何 mock）

**目标项目**：mall-backend（repositories id=21，ThinkPHP 商城后台，`~/Projects/mall-backend`）

**前置修复**（本次新发现）：
1. `agent_main.yaml` worker 工具池缺少 4 个 atlas 工具 → 已加入（`agent_config.tools` 动态注入只对 MCP 工具生效，原生工具必须在 YAML 池）
2. 授权门禁对相对路径按**进程 cwd** 解析（`authorization.py:_is_path_safe`），且 mall-backend 无 `.evoloop/project.json` → `get_project_path(21)` 返回空，首个 `list_dir` 即触发 HITL 停摆。修复：写入 `~/Projects/mall-backend/.evoloop/project.json`（`{"project_id": 21, "repo_id": 21}`）+ 任务指令强制绝对路径
3. wiki 老脚本两处已过时（本脚本未沿用）：`app.core.engine.graph_builder` 模块已删（globals.py 为 stub）；`BlackboardState` 已删，技能挂载走 `references=[{type:"skill"}]` → `metadata["explicit_skills"]` → supervisor 路由携带 skill_ids

**运行结果**（kimi-k2-thinking-turbo，1005s）：

| entity | actions | elements | macros | 备注 |
|--------|---------|----------|--------|------|
| goods | 12 | 13 | 3 | |
| order | 14 | 20 | 5 | |
| member | 15 | 19 | 4 | |
| goodscategory | 9 | 13 | 0 | 覆盖缺口诚实上报 |
| goodsbrand | 6 | 10 | 0 | 覆盖缺口诚实上报 |
| memberlevel | 6 | 12 | 2 | |
| orderrefund | — | — | — | worker 50 步截断，supervisor 审查后结束会话 |

- 6/7 实体地图全部 `status=active`（回源抽检通过；过程中 5 次校验拒绝→Agent 自行修正引用后重试成功，防幻觉门生效）
- 14 个宏候选全部 `pending_review`、`risk_tier=money`、`requires_confirmation=True`（金钱门生效）
- Huey worker 真实消费 `synthesize_macros_task`（每图 0.01~0.02s）
- 断言全过：≥3 地图、≥1 宏候选、每图 active 且有 actions
- 单元测试 994 passed / 7 skipped（YAML 变更无回归）

**遗留观察**：
- 宏命名模板产物为 `改{query}goodsgoods_name` 形态（entity+field 直接拼接，可读性差）；重名去重后缀 `（editGoods）` 正常工作
- worker max_steps=50 对 7 实体串行勘测不足 → 第 7 实体截断；supervisor 选择 finish 而非续跑（设计如此，但计划步骤 6/7 时收尾说明"广覆盖"需按实体分批派单或调大步数）

---

## 十四、全量广覆盖验证（2026-07-15 晚，机械采集方案）

**方案转变**：逐实体 LLM 调研（3.5 min/实体）太慢。改为 Agent 侦察少量样本后**自写一次性采集脚本**机械提取，语义富化也由脚本完成（ThinkPHP CRUD 命名启发式），LLM 只做框架侦察与编排。

**新发现的生产 bug（已修复）**：
- `database_logger.on_llm_start` 用 callback run_id 当 message_id，resume 路径（`_chat.py` run_id=`resume-<thread>-<ts>` 不以 `run-` 开头）下同一次 resume 内所有 LLM 调用复用同一 message id → 第二条 AI 消息落库 `UNIQUE constraint failed: messages.id`。**任何 resume 会话（HITL 批准后）都会崩**。修复：message_id 改为每次调用 `uuid4()`（`database_logger.py:107`）。994 单测无回归。
- 授权审批不落 grant（`grant_permission` 无调用方）→ 每个新相对路径都重新 HITL。测试侧以自动审批循环（生产 `/resume` 路径 `resume_graph_background`）兜底。

**测试脚本增强**（`test_atlas_survey_lifecycle.py`）：
- mission 改为机械采集策略（RECON ≤10 次读取 → 写 `_atlas_collect.py` → 执行 → 逐实体富化提交）
- HITL 自动审批循环（`get_pending_hitl_call` → `handle_resume` → `resume_graph_background`）
- 计划未完成时自动发送"继续"续跑轮次（模拟真实用户回复，最多 10 轮）
- 验证对照文件系统全量控制器普查（44 个业务实体），superseded 版本不计入断言；`--verify-only` 模式

**最终结果**（kimi-k2-thinking-turbo，3114s，2 次 HITL 自动审批，3 轮续跑）：

| 指标 | 结果 |
|------|------|
| 实体覆盖 | **43/44（98%）**（唯一缺失 `printer`，小票打印硬件接口） |
| 地图版本 | 43 active + 12 superseded（11 实体在续跑轮次被增量重勘为 v2，版本级联正常） |
| 宏候选 | **173 个**（含 `查看{query}xxx` [ui] 与 `改{query}xxx` [money]，金钱宏 confirm=True） |
| Agent 自组织产物 | `_atlas_collect.py`（采集）+ `_atlas_enrich.py`（启发式富化，23KB）+ `_atlas_trim.py` + `_atlas_payloads/`（43 份完整 payload） |
| HITL | 2 次（均为 execute_command 运行采集脚本），自动审批续跑正常 |
| 断言 | 全绿（≥10 active 图、≥1 宏、active 图均有 actions） |

**结论**：机械采集方案使广覆盖从"小时级 + 频繁截断"变为"52 分钟全量 98% 覆盖"，且引用行号全部机器计算，幻觉源头消除。Agent 自发把语义富化也脚本化（超出 mission 要求），验证了该路径的可行性。

**后续建议**：
- 采集策略可沉淀进 SKILL.md（当前由 mission 文案携带）
- `printer` 等硬件控制器可加入基建排除清单
- 宏命名可读性（`改{query}goodsgoods_name`）仍待优化

## 十五、宏可执行性修复（2026-07-15 深夜，格式审查驱动的模板修复）

**起因**：逐条审查 §十四 的 173 个宏，发现"语法合法但不可执行"的 4+1 个缺陷。

**缺陷与修复**（全部在确定性代码层，零 LLM）：

| 缺陷 | 根因 | 修复 |
|---|---|---|
| URL 不可导航（`shop/goodslabel/lists` 裸路径） | 模板直接引用 route.url | `_full_url`：`extra.base_url` + 归一化路径（补前导 `/`）；base_url 未知时产 `{{base_url}}` 占位 + 自动追加可选参数 |
| selector 无类型（`search` 裸符号） | 元素未记录符号形态 | schema 新增 `element.selector_type`（id/name/class/lay-filter/css/text）；模板 `_selector` 产出 `#x` / `[name='x']` 等前缀形态，未知时兜底 `#x, [name='x']` 联合猜测 |
| 双回车提交（input enter:true + key_press return） | 模板冗余步骤 | 删除 key_press；找到独立搜索按钮时 input 显式 `enter: False` 并点击按钮（贴合 layui），无按钮才用 Enter |
| POST-only 路由产浏览器导航宏 | 未检查 method | `_allows_get` 门：POST-only → 诚实计入覆盖缺口（生产数据均为 GET/POST，无损失） |
| 宏名英文兜底（`goodslabel`） | `tasks.py` 构建 entity_map 时丢弃 `aliases`/`extra` | 补齐两字段，中文命名恢复（`查看{query}商品标签`） |

**配套变更**：
- `write_app_map` 工具新增 `extra` 参数（`{"base_url": ...}`），validate 新增 route url 前导 `/` 与 selector_type 合法性强校验
- SKILL.md 采集规范：selector_type 机械推断 + base_url 发现写入 extra
- `synthesizer._check_candidate` 接地检查适配新形态（剥 base/查询串比路径、selector 双向集合）
- 顺带修复过期测试 `test_money_macro_requires_confirmation`（§16.5 行为：money 宏委派 Agent 多轮确认，非 confirm_required 硬门）

**重生验证**（dev DB，project 21）：
- 删除旧 173 个 pending 宏 → 从 43 张 active 地图重合成 **94 个**
- 复读校验：94/94 解析通过、URL 均可导航（`{{base_url}}/` 或 http）、selector 均带类型、占位符与声明一致（0 失败）
- 173→94 的差值（79）为被新接地规则诚实拦截的"会失败的宏"（向按钮输入文字等）；20 个实体暴露地图数据缺口（采集未录入搜索输入框/结果表格元素，或列表端点 risk 误标 data）→ 重采集可补回，属防虚构机制按设计工作

**测试**：atlas 34 + routing 6 全绿（新增 8 个可执行性格式用例）；改动文件 ruff check/format 通过。

## 十六、机械补采（2026-07-15 深夜，第二轮）

**方法**：一次性脚本（零 LLM）对 43 张 active 地图做四项机械修复：
1. 扫描 `app/shop/view/<entity>/**/*.html`，补录首轮采集遗漏的搜索输入框（`name="search_keys"`）/搜索按钮（`lay-filter="search"`）/结果表格（`<table id=…>`），行号真实可回源
2. 已有元素按引用页面回填 `selector_type`（id/name/lay-filter/class 机械定位）
3. read 动作风险重标：控制器方法体含 `isJson()`+`fetch()` 双形态（ThinkPHP 商城同一 action 同服页面与 JSON）→ data 改 ui
4. 路由 URL 归一化补前导 `/`

每张地图过 validate（schema+回源抽检）后存新版本（v3），并就地重合成宏。

**结果**：43 实体全部升版；+26 补录元素；309 元素补齐 selector_type；10 动作重标 ui；宏 94→**109**（覆盖 26/43 实体，money 10 个）；格式复读 0 失败。3 实体无同名视图目录（gamesrecords/goodsbatchset/memberaccount，视图散落他处），其余未覆盖实体经查证为诚实缺口（如 goodscategory 是树形列表、本无搜索表单）。

**执行链路核查结论**（"宏能不能用"）：
- 查看类（99 个）：步骤链完整可执行，唯一前置是 `{{base_url}}` 需在执行参数中提供（或写入地图 extra 重生成）
- 改价类（10 个）：仅在 `query` 为**数字 ID** 时可直接执行；按名称改价需要"搜索→提取 id→跳编辑页"两段式，当前引擎 `extracted_data` 不回填 `params`，不支持跨步引用 —— 待修（引擎小改 + 模板升级）
- 真机冒烟未做：浏览器会话、ThinkPHP URL 大小写、layui 渲染时序均需实机裁决

## 十七、两段式写宏 + 真机冒烟（2026-07-15 深夜，P8 尾项）

**引擎修复（2 处）**：
- `MacroEngine.execute_steps`：extract 步骤后 `extracted_data` 回填 `params`（显式参数优先，None 不覆盖）→ 跨步 `{{entity_id}}` 引用可用
- `_extraction._unwrap_controller_value`：剥离 ControllerResponse ✅/❌ 信封，get_attribute 提取值从 `✅ Attribute ...\n\n100` 还原为 `100`；❌ → None → 配合新增 navigate 守卫（URL 含未解析 `{{}}` 即失败）防垃圾跳转

**模板升级**：crud_write 改两段式（列表搜索→`get_attribute [lay-id='表'] tr[data-index='0'] [data-x-id]` 提取行 id→`编辑页?id={{entity_id}}`→填值→保存）；新增 `data-attr` selector_type；补采第二轮机械收录 17 个 `data-*-id` 行内元素；`extra.base_url=http://127.0.0.1:9002` 注入全部地图（v4）→ 105 宏 URL 全绝对化；list_view 提取修正为 `[lay-id='表'] .layui-table-body`（layui 隐藏源表）并在搜索点击后补 1s AJAX 等待

**真机冒烟**（`tests/manual/smoke_atlas_macro.py`，真实 Chrome CDP + 真实后台 admin 登录）：
- 查看宏（query=个人基础版）：搜索→过滤→提取单行 `订阅会员（个人基础版）￥0` ✓
- 改库存宏两段式 dry-run（步骤 1-7）：搜索→`data-goods-id=100`→打开 `editgoodsstock?id=100`，编辑页标题正确 ✓（保存未执行，money 门保留）
- 领域发现：后台搜索匹配 `sku_name` 非 goods_name，软删 SKU 的商品搜不到——宏语义正确，首轮失败是测试数据选择问题

**测试**：1014 passed / 7 skipped（新增两段式引擎 3 例 + 模板两段式 3 例）；改动文件 ruff 通过。

## 十八、接力语义与多意图参数解析（2026-07-15 深夜）

**失败接力**：宏执行失败不再推 failed 死胡同 → `_run_agent` 派发失败简报（原始指令/失败步骤/错误/已提取数据/截图），Agent 接力完成意图；引擎失败返回新增 `step_number`/`event_type`。策略门失败（source/risk/未确认/缺参）不接力。

**与自愈机制对齐**：梳理确认 MacroService 路径的自愈（三级策略门+建议事件）与 resolver 零重叠；但 voice relay 绕过了 `SelfHealingPolicy`，已对齐——接力前先过自愈策略门（macros 无 skill 级开关，查全局+执行级），禁用则推 failed+原因。

**方案甲 resolver 落地（编排层）**：`app/core/routing/resolver.py`——`{{1.price}} * 0.9` 白名单 AST 求值（数值强制转换 "￥99"→99.0，算术+round/min/max/abs，拒绝注入/除零/缺失引用），求值失败即 ResolveError → 该意图交 Agent（方案乙兜底）。21 例单测全绿。

**剩余编排**：拆意图（LLM 前置）+ route_many 顺序执行 + 前序 extracted_data 传递 —— 下一轮。

## 十九、多意图编排闭环（2026-07-15 深夜）

**链路**：`decompose`（连接词启发式守门 → 小模型拆意图，输出 depends_on/param_exprs）→ `router.route_many`（每个子意图独立检索+单发路由，依赖标记随 params 携带）→ `executor.execute_many`（顺序执行，前序 extracted_data 经 resolver 算出绝对值参数；resolve 失败该步交 Agent（方案乙）后续步不受影响）。

**顺带修复的生产 bug**：`voice_ws.py` 原 `if target_type in ("skill", "agent")` 排除了 macro —— 语音路由到的宏从未被派发执行（冒烟一直绕过此路径）。已修并切到 execute_many。

**降级矩阵**：无连接词→零额外 LLM 调用；小模型不可用/输出非法→单意图原路径；单决策→execute 原签名行为；resolver 失败→方案乙 Agent 接力。

**测试**：1043 passed / 7 skipped（新增多意图 14 例：解析校验/启发式守门/降级/链式求值/失败续跑）。

## 二十、真实小模型拆分质量验证（2026-07-15 深夜，tests/manual/test_decompose_real_model.py）

**首轮 5/10**，暴露三类真实问题并修复：
1. qwen3-4b 的 `depends_on` 输出形态漂移（`[]`/`[1]`/`{"i":1}`）被严格校验整体作废 → `_norm_depends_on` 宽容归一（int/list/dict/str → int，非法才作废）
2. 提示词未约束参数名（模型用 `value` 而宏参数是 `new_value`）→ 提示词补参数名规则 + 完整输出示例 + "汇报尾巴不拆"规则
3. 启发式缺英文连接词 → 补 `and then / then / and also`

**修复后 10/10**：依赖链产出 `round({{1.value}} * 0.9, 2)` 标准式；"改成88"产出常量表达式（resolver 可直接求值）；三意图混合依赖正确；"然后告诉我"陷阱正确保持单意图；英文指令拆出的子意图自动中文化（利于中文检索语料）。

## 二十一、多意图全链 E2E 三链全绿（2026-07-15 深夜，tests/manual/test_multi_intent_e2e.py）

真拆意图 + 真检索 + 真路由 + 真顺序执行（商城后台 :9002），从 4 处失败迭代到 ALL CHAINS PASS。暴露并修复 5 个真实缺陷：

1. **路由索引嵌入占位符噪声（sync.py）**：宏名/触发词带 `{query}`/`{{query}}` 占位符直接入向量，bge 按字面 token 处理，正确宏得分塌到门限下（0.03 vs 0.15）。修复：`_entry_embed_text` 剥 `{{}}`/`{}` 占位符后嵌入。
2. **decompose 空 content（decompose.py → adaptive.py）**：进程内首次 LLM 调用正常，`bind_tools(tool_choice="required")` 之后所有裸调用返回空 content。根因：`AdaptiveChatOpenAI.bind_tools` **原地变异 self** 且 `LLMFactory` 按配置缓存实例——路由绑定污染了缓存实例，后续裸调用带 tool_choice=required，模型回 tool_call、content 为空。修复：`bind_tools` 返回浅拷贝副本（所有调用方本就用返回值）。另给 decompose 加空输出重试 + reasoning_content 兜底。
3. **实体查询词无法区分兄弟宏（route.prompt.j2 + ROUTE_MIN_SCORE 0.15→0.05）**："查询订阅会员的信息" embedding top 竟是订单宏（0.155 > 商品宏 0.072）——实体词不在任何嵌入文本里，余弦恒近tie，bge 无法分辨；bge 查询指令前缀实测更差（0.44 vs 0.55 仍订单赢）。修复：路由提示词补 `{query}` 占位符说明 + "具体业务名词选业务域最近宏，不要 delegate" + 动词匹配规则（含反例："查询X的库存"选查看宏不选改库存宏）+ query 参数抽取规则（"查一下X"→query=X 类别词）；门限 0.15→0.05（只挡无望检索，最终裁决交给路由 LLM）。效果：信息/价格/库存三种查询句式全部命中商品宏。
4. **宏引擎 EXTRACT 步零容错 + playwright 异常逃逸（engine/__init__.py）**：EXTRACT 步无 try；ACTION 的 catch 元组不含 playwright Error（选择器超时 15s 直接 crash 整个语音派发）。修复：`_STEP_EXCEPTIONS` 纳入 playwright Error，EXTRACT 包同级失败路径（截图 + step_number/event_type 返回 + 失败接力），截图逻辑提为 `_debug_screenshot`。
5. **宏62选择器与真实页面不符（数据修复）**：订单列表页是服务端渲染的 `table.order-list-table`（8行），不是 layui table widget，无 `lay-id='order_list'`。已在 DB 修补宏62提取选择器为 `table.order-list-table tbody`。**遗留**：生成器 `_list_surface` 对非 layui 服务端渲染表格的适配（需三轮补采修 AppMap 源数据，否则重新生成会回退）。

**链B 遗留观察**："查询订阅会员的库存" 曾误路由到改库存宏54（名词匹配压过动词语义）——写操作宏被查询意图命中的安全相关误路由类别；提示词反例修复后三种查询句式均正确命中查看宏52。money 门（§16.5 HITL）在误路由期间仍兜底拦截，未发生真实写。

## 二十二、三轮补采 + 字段读宏：链C 从兜底升级为真实求值（2026-07-16 凌晨）

**动机**：链C 的 {{1.value}} 此前必然落方案乙兜底——没有任何宏提取纯净数值 value 键；且宏62 的 layui 选择器是 DB 手工补丁，重新生成会回退。

**生成器新增（templates.py/synthesizer.py）**：
- `crud_field_read` 模板：与 crud_write 共享接地（无保存按钮），搜索→首行 id→编辑页→`get_attribute input value`，产出 `value` 键；risk 强制 ui（源自 money action 但零写入）。money/write action 现在产双候选（写宏+字段读兄弟宏）。
- css 结果表格适配：`_rows_container`/`_first_row_id_selector`——css 选择器原样用（服务端渲染表格），id 选择器维持 layui 约定。
- `_stage2_url`：路由条目新增可选 `page_url`（JSON-only 端点的渲染页）与 `id_param`（框架主键参数名）字段；grounding 校验同步收录 page_url。
- 写/字段读宏 description 不再继承批量 action 的 business_rule（"批量设置商品"会稀释嵌入），改为生成的"修改/查询{实体}的{字段}"。

**补采修正（地图 v4 原位更新，宏 id 不变）**：order 列表表格改 css `table.order-list-table tbody`（真实是服务端渲染非 layui）；goods 路由 editGoods/editGoodsStock/batchSet 补 `id_param=goods_id` + `page_url`（控制器 GET 读 `input('goods_id')`，`?id=` 会静默回落列表页——此前两段式写宏的 stage-2 全是错的，dry-run 停在 step7 未暴露）。重生成：goods 12 更新、order 17 更新、新增宏 106/107（查库存/价格）。

**路由层**：`ROUTE_MIN_SCORE` 0.05→-0.1（长实体名 9+ 字时正确宏也只 ~0.05、写措辞负分——嵌入只负责排序，裁决全交给路由 LLM）；提示词补泛化词规则+具体 few-shot（"查询钥匙扣的信息"→选"查看{query}商品"不选字段宏）；decompose 提示词补"忠实原句"规则（曾把"查一下X"臆造成"查询X的价格"）。

**真机数据修正**：测试实体改"夜光亚克力钥匙扣"（goods_id=2, ¥888.00, 库存100）——订阅会员类虚拟商品编辑页 500（模板 foreach 崩溃）；下架商品默认列表搜不到，已上架（goods_state=1）。

**E2E 三链全绿（连跑两次）**：链C 成为首个全真实依赖链——字段读宏提取 `value='888.00'` → resolver 算 `new_value=799.2` → 改价宏60 命中 money HITL 门。链A 接受 52|107 漂移（"查一下X"对 4b 是真实歧义句，已注释说明）。

**遗留**：order 行无 data-order-id（行 id 是不透明串），订单写/字段读宏 108/109 未确认；订单写宏 67/68 的 id_param 未补采。

## 二十三、全量验证轮：写宏真写、批量冒烟、自愈、命中率、并发（2026-07-16 凌晨）

**#1 写宏真实保存 PASS**（tests/manual/verify_write_macro_real.py）：宏54 引擎层全 11 步真机执行，库存 100→142（DB 确认）→100（同一宏恢复），price/name/state 零副作用。过程暴露并修复两个生成器缺陷：①**页签隐藏域**——price/goods_stock 位于 layui"价格库存"页签（未激活面板 display:none，input 等可见性 3s 超时），元素新增 `tab` 标记 + 地图补 text 页签元素，crud_write 自动插页签点击步（页签未采到则诚实缺口）；②**save 按钮错配**——`_find_element("保存",...)` 先匹配到列表搜索按钮（binds 含"提交"），新增 `_find_save_button`（优先 binds"保存"、排除搜索按钮）。另发现 layui 保存走 AJAX，引擎返回时 POST 未必落库，验证脚本需等 2.5s。

**#4 批量读宏冒烟 20/103**（tests/manual/batch_smoke_read_macros.py）：83 失败分类 step3×66（搜索输入框运行时不存在）、step5/6×15（提取面不存在）、step9×2（订单行 id，已知）。抽查会员/相册/消息页：页面本身正常，**采集 agent 从源码模板过度声称了运行时没有的搜索元素**——这是规模最大的数据质量问题，需"运行时 DOM 复采"专项（逐页 dump 真实 DOM 元素），单独立项。

**#3 自愈策略门真机 PASS**（verify_self_healing_real.py）：改坏宏52 选择器→MacroService 真机失败→`fallback_required`+advisor 建议 1 条；`_allow_self_healing=False`→正确拦截（source=execution）。注意：建议事件依赖 `auto_discover_handlers()`（main.py/run_worker 启动时都跑，独立脚本需手动调）。

**#7 措辞命中率 84%→100%（25 句式×2 轮）**（verify_routing_hitrate.py）：三轮修复——①口语字段词映射规则（多少钱/售价→价格；多少件→库存）；②**删除早退分数门**：实测正确 rank-1 低至 -0.21、垃圾query 高达 -0.035，分布重叠无任何阈值可分（"帮我写个周报"-0.214 vs 正确"详细信息"-0.214），`ROUTE_MIN_SCORE` 默认 -1.0（有候选就交给路由 LLM 裁决，LLM 是唯一胜任的过滤器）；③垃圾指令拒选反例规则（防"不要 delegate"压力过强把天气也路由到商品宏）。

**#8 {{base_url}} 占位分支 PASS**（verify_base_url_placeholder.py）：无 base_url 地图合成宏→URL 含 `{{base_url}}`+声明 base_url 参数；传参执行成功、缺参被 navigate 守卫正确拦截。

**#10 并发干扰实证+修复**（verify_concurrent_macros.py）：并发双宏同页，A 的 goto 被 B 的 goto 在 100ms 内 ERR_ABORTED——共享单页必须串行。修复：引擎 `_DOM_EXECUTION_LOCK`（含 DOM 步的宏执行互斥），修复后并发双成功（B 等锁 6.3s≈A3.1+B3.2）。

**回归**：1044 unit passed；多意图 E2E 三链全绿（引擎锁+提示词+门限变更后）。

**新增验证脚本**：verify_write_macro_real.py / batch_smoke_read_macros.py / verify_self_healing_real.py / verify_routing_hitrate.py / verify_base_url_placeholder.py / verify_concurrent_macros.py。

**遗留**：83 个采集失真的读宏（运行时 DOM 复采专项）；订单行 id 方案（#67/68/108/109）；crud_read data 类宏仍零真机（无候选产出，诚实缺口）；LOOP/IF 引擎路径无模板产物可验。

## 二十四、ASR 噪声鲁棒性（2026-07-16，verify_routing_noise.py）

**结论先行：路由 LLM 对同音噪声的容错远超预期，但这不是可以高枕无忧的意思。**

**基线 95%（21/22）→ 100%（22/22）**：对 25 句式做 ASR 典型变异（同音字：亚克力→压力克/库存→裤存/价格→价各/订单→定单/售价→售假；语气词混入；数字文字化"五十/两百"；连接词"然后→然候"），零修改基线即 95%——qwen3-4b 靠上下文纠错，同音字段词几乎全对。唯一误例"钥匙扣裤存调到两百"→改价宏60（"两百"被读成价格），提示词补近音纠错映射（裤存=库存/价各=价格/定单=订单/售假=售价）后 100%，干净套件无回归。

**安全结论分层**：
- **字段/动词误判被 money HITL 结构性兜底**：唯一错例是写宏之间的混淆（54 vs 60），两个都是 money 级，人工确认页会看到真实字段和值——ASR 错得再离谱，写操作都有人最后一眼。
- **实体词同音错（"压力克"）不影响选宏**（靠类别词/字段词），但会让宏的 query 搜索无结果——诚实空输出，不编造。这是体验问题不是安全问题，根治靠实体纠错词典（未做）。
- **未覆盖的噪声形态**：本套件只测了同音/语气词/数字文字化；漏字（"钥匙"）、断句错误（多意图连读）、中英混杂（"帮我check一下订单"）、方言口音导致的非音近错字未测。

## 二十五、中文数字与单意图写参数（2026-07-16）

**用户追问暴露的重度缺陷**：噪声套件只验了路由目标没验参数值。实测：
- **多意图路径正常**：decompose 把"五十"→`{'new_value': '50'}`、"降两成"→`round({{1.value}} * 0.8, 2)`，全对。
- **单意图写路径 100% 坏**：route LLM 抽参产出 `inventory: 50`（宏要的是 `new_value`）、`price: '六十六'`（名错+未转数字）、甚至缺参数——每条单意图写指令都会在 `missing_required_params` 处死掉。**根因**：`sync.py:_params_to_schema` 不处理 list 类型参数（宏的 parameters 是 JSON list），路由提示词里的 params_schema 恒为 `{}`，LLM 看不见参数名只能瞎编。

**修复**：①`_params_to_schema` 补 list 分支（携带 required/description）；②提示词补两条：参数名必须逐字用 schema 键名（写宏固定 new_value，禁造 inventory/price）；数值参数中文数字转阿拉伯数字（五十→50、两百→200）。修后四条中文数字写指令全部产出正确 `new_value` 数字。

**副产物**：schema 进提示词改变了歧义句 tie-break，"查一下夜光亚克力要是扣"稳定漂到 107——泛化词规则补噪声 few-shot 例2 后噪声套件 100%×2、干净套件 100%。

**回归**：1044 unit passed；E2E 三链全绿。

## 二十六、持续性多轮对话：会话帧+指代改写+导航跳步（2026-07-16）

**范围界定（用户拍板）**：多轮只支持**持续对话内**——帧生命周期=对话生命周期，ws 断开（connection.unregister）即清帧，无持久化、无 TTL 策略（session_frame.py 仅内存 dict+30min 安全网）。非持续对话（新开窗口/重连）明确不做。

**三件套（全部确定性代码，零 LLM 新增）**：
1. **list_open 导航宏**（templates.py）：read/ui 动作产双候选——`查看{query}X` + `打开X列表`（navigate+wait+提取当前页行，无 query 参数）。原位重生成后激活 #110 打开商品列表 / #118 打开订单列表；23 个按动作复制的兄弟（打开X列表（action））降 pending_review 只留正主。
2. **会话帧**（routing/session_frame.py）：`thread_id → {current_page, current_entity}`。`_run_macro` 成功后回写——current_page=脚本最后一个 navigate URL（{{}}参数以执行值代入）；current_entity 仅在有 query/entity_id/value 时更新（导航宏不清空实体）。`resolve_anaphora` 确定性替换首个指代词（它/他/她/这个/那个/这件/该商品/此商品→上轮的 query；裸"该/此"排除——"应该把它下架"不误伤），wire 在 route_many 顶部（改写先于 decompose 和检索，嵌入与 LLM 都看到自足句）。
3. **导航跳步**（engine/_executors.py）：navigate 前比 page.url（含 query——?goods_id=2 与 3 必须不跳），已在目标页则跳过 goto+stability，每多轮步省 ~2s。

**E2E 三轮商品场景 PASS**（tests/manual/test_multiturn_goods_e2e.py，单 thread 三轮）：
- T1"打开商品列表"→宏110，帧 page=goods/lists；
- T2"查一下夜光亚克力钥匙扣的价格"→宏107 真提取 value='888.00'（step1 navigate 被跳步），帧实体=夜光亚克力钥匙扣(id=2)；
- T3"把它的库存改成142"→指代改写"把夜光亚克力钥匙扣的库存改成142"→宏54 query 正确 new_value=142→money HITL 委派。

**顺手挖出的存量炸弹**：round3 的 routes 修复（id_param/page_url）当年是**原地改 JSON 列字典**，SQLAlchemy 脏检查看不见、从未落库——宏之所以一直对，是因为同进程内用了修过的内存对象；round4 重合成直接从 DB 读旧地图把 54/60/107 的 stage-2 URL 回滚成 `batchset?id=`（全错）。修复 atlas_round3_regen.py 为**整体重赋值**（`am.routes = routes`）+ 补注注释，重跑 round3+round4 后地图与宏双双归位。教训已适用于一切 JSON 列：原地 mutation = 静默丢失。

**回归**：1044 unit passed / 7 skipped；多意图 E2E 三链全绿。

**仍未做（按优先级）**：clarify 续接回路（缺参数时问一句"你指哪个"而不是直接失败）；帧验证探针（执行前比 page.url 与帧，页面被手动切走则清帧——持续对话内概率低，目前是廉价保险未装）；方案 C（宏降级为 agent 工具统一轨）对照原型；83 个采集失真读宏的运行时 DOM 复采专项。

## 二十七、clarify 续接 + 帧探针 + 运行时 DOM 复采（2026-07-16）

**clarify 续接回路（全确定性）**：持续对话内"缺实体"不再直接失败——①触发：无帧实体+含指代词+**单句**（含连接词则交 decompose，同句另一子句自带实体——这条守卫是回归炸出来的：链B"查X，然后把它…"被 clarify 误拦）；②存 `frame.pending={kind:missing_entity,text:原句}`，路由返回 `status=clarify` 决策（voice_ws 不执行只回显"请问是哪个商品/订单？"）；③下一句作答被 `consume_pending` 拼接回原句（有指代词则替换、无则前缀）重新路由。执行层缺 query 参数同样走 pending+clarify（route() 给 macro 决策带 `_text` 原文）。

**帧验证探针**：route_many 在指代改写**之前**比对 page.url 与 frame.current_page（frame 有 current_page 说明浏览器必然在跑，不会为探测白启动），不符即清帧→指代无实体→走 clarify。E2E 实证：用户手动切到订单页后"把它的库存改成142"不再误用陈旧实体，而是正确发问。

**E2E 五轮 PASS**（test_multiturn_clarify_e2e.py）：冷指代→clarify→作答→宏54 HITL；真查价建帧→手动切页→探针清帧→clarify→作答→宏54 HITL。

**运行时 DOM 复采专项**（atlas_runtime_resurvey.py，round-5）：逐实体访问列表页 dump 运行时 DOM（inputs/lay-filter/lay-id+hasTable/tables），地图级修复三类元素——搜索框（运行时替代：name/placeholder 启发式，无替代标 `runtime_absent`，模板三个 finder 跳过→诚实缺口）；搜索按钮（lay-filter 校正）；结果表（优先含 .layui-table 的 lay-id 容器，否则**带特异性 class 的服务端渲染 table**——orderrefund 与订单同款 order-list-table，被首轮"非 layui 才算纯 table"规则漏掉后补规则复活）。踩坑三连：lay-id='' 和 lay-id='1' 这类内部容器须过滤/hasTable 校验；已标 absent 的元素要有复活通道；JS dump 模板折行触发 ASI 语法错误，改单行。

**空表提取修复**：`inner_text` 等可见性，空 tbody 零高必超时——rows 提取步新增 `payload.state='attached'`（引擎透传→控制器 text_content），空表诚实读""。

**冒烟 20→29/103，剩余 67 失败全部定性**：(action) 重复宏指向 JSON/非列表端点（约40，全部 inactive 噪声，不会被路由）；空结果连表都不渲染的条件渲染页（退款搜'test'后表消失=诚实失败）；member/account/message/diy 页面真无搜索框（诚实缺口，宏已 pending）；相册是图片墙无表格概念。**结论：失败清单里已没有"选择器错误"这一类，剩下的都是数据存在性/诚实缺口/不活跃噪声。**

**回归**：1044 unit passed；多轮商品/clarify+探针/多意图三套 E2E 全绿。

## 二十八、语音 WebSocket 全链路多轮（2026-07-16，test_voice_ws_multiturn_e2e.py）

**结论先行：多轮+clarify 不再只是路由层属性——真实 ws 协议下对话真的能续上。**

**形态**：真 uvicorn（app.main:app，127.0.0.1:8123）+ websockets 客户端 + canonical envelope（version=2.0/message_id/timestamp）。服务端与客户端共享**同一 asyncio loop**（uvicorn.Server 作 task）——懒启动的浏览器因此与引擎、预登录同 loop，规避 playwright 跨 loop 冲突。money HITL 在进程内 patch `_run_agent` 捕获并回推 `status=hitl`，ws 管道可见。

**五轮全过**：
- 线程 ws-mt："打开商品列表"→route_result routed #110→result done；"查一下夜光亚克力钥匙扣的价格"→#107→done（真提取）；"把它的库存改成142"→指代改写→#54 query=夜光亚克力钥匙扣 new_value=142→hitl。
- 线程 ws-clarify：同句冷指代→**route_result status=clarify + "请问是哪个商品？"**（无任何执行）；答"夜光亚克力钥匙扣"→续接合成→#54→hitl。

**协议侧确认**：route_result 双形态——路由决策（status=routed/clarify+target/params）与执行结果（status=done/failed/hitl+summary）同通道，客户端按 body 有无 target/summary 区分即可；clarify 决策不会触发 execute_many（target_type∉skill/macro/agent），下一轮作答在同 thread 内被 consume_pending 拼接重路由。

**踩坑**：voice_ws 路由前缀是 `/voice`（全路径 /api/v1/voice/ws）；非规范 envelope（缺 version=2.0/message_id）会被 system.error 拒。

**回归**：1044 unit passed。

**交付状态更新**：读宏、写宏（HITL 前）、多意图编排、多轮会话帧、指代改写、clarify 续接、帧探针——以上在**真机+真模型+真 ws 协议**下全部闭环。剩余 backlog：写宏保存断言（toast/DOM）、crud_read data 类模板、ASR 实体纠错词典、方案 C 统一轨原型、订单行 id（暂缓）。

## 二十九、指代正则的边界与领域词解耦（2026-07-16）

**起因**：代码评审式追问——_ANAPHORA_RE 里写死了"商品"（这个商品/该商品），那是业务域词不是语言规则，换行业后台即失效；且裸 [它他她] 替换会腐败实体名（吉他/维他奶/维也纳/其他）——这是全链路唯一"激进写文本"的正则位。

**两层修复**：
1. **语境化指代**：裸它/他/她必须带语境——前接 把/将/给/让/对/向，或后接 的；"的"分支加 吉/维/其 前置黑名单（打地鼠性质，纵深防御一层，末端还有"搜无结果→诚实空输出"兜底，写操作另有 money HITL）。11 条正反例全过（含"应该把它下架"不误伤"应该"）。
2. **领域名词数据化**：`set_domain_nouns()` 从 AppMap 活跃别名注入 CJK 实体名词（商品/订单/会员…），`sync.rebuild_route_index` 重建时喂入；复合词（这个商品/该订单）按名词集动态编译，换行业（餐饮:菜品/桌台）自动切换；缺名词集时退化为裸 这个/那个/这件（替换后残留名词=保守退化非腐败）。

**单测**：tests/unit/core/routing/test_session_frame.py 22→23 例（新增领域名词注入/切换用例，fixture 恢复全局态）。

**定位结论（回答"正则是稳固还是脆弱"）**：链路里的正则全部在保守位（漏检→回落 LLM/clarify），唯一激进位（指代替换）经本轮收紧后，误伤路径只剩"实体名含人称字且非 吉/维/其 开头"的长尾，代价被 clarify/搜索空结果/HITL 三层兜底。

**回归**：1067 unit passed（+23）；clarify+探针、多轮商品 E2E 全绿。

## 三十、NLU(NLTagger) vs 正则：shadow 对比实验（2026-07-16，tests/manual/shadow_nlu_eval.py）

**问题**：不动链路、只把两个确定性门的匹配器从 regex 换成 macOS NaturalLanguage+词性标注，是否更好？**答案：否——标注语料上的干净负结果。**

**实验 A·检测门（decompose 触发）**：61 单句+8 多意图标注集。regex 基线 0 误报/3 漏报；NLU 动词数 OR 门原始版 77% 误报、"名词后动词不计"调优版仍 28% 误报，召回仅+2。根因：中文单意图动词富集（改成/降成/调到是动词串）+ tagger 把名词碎片标成动词（钥匙扣:Verb、列表:Verb、"周爆"切碎）。**拒绝。**

**实验 B·指代替换否决票（regex 命中且 NLU 同位标 Pronoun 才替换）**：16 条语料（含莎她娜/爱它宠物粮等黑名单未覆盖陷阱）veto **零判定改变**——收紧后的语境 regex（语境前缀+吉/维/其黑名单）已内化全部边界，veto 在现实分布上是死代码。**拒绝。**

**反证留存**：探针显示 NLTagger 把"维他奶"切成 维:Verb+他:Pronoun+奶:Noun——若以 NLU 为主力替换器，会重新引入 regex 已堵住的实体名腐败；tagger 切词不可枚举、无法打补丁。

**已知残余缺口（两匹配器都修不好）**：无连接词多意图（"查一下钥匙扣库存改成142"），regex 漏检→走单意图路径，route LLM 仍执行首个动作，退化可接受。

**方法论价值**：标注语料+shadow 对比的成本远低于上线试错；同一方法可用于日后评估任何匹配器替换提案。

## 三十一、第三方"Layer-0 字典交集+模板正则"方案评审（2026-07-16，tests/manual/shadow_layer0_eval.py）

**背景**：第三方提案=我们现有分层 + 两个增量（方案一 Aho-Corasick 字典交集替代 Layer-0 正则；方案二宏触发词动态编译正则+LLM 终审）。照旧用标注语料投票。

**方案一（字典交集）实测 28 条 L0 语料**：M2 17/19 命中 vs M1（客户端 Init-Spec 模板子串）16/19——唯一真实增益在有槽位动作的双要素要求（"声音小点"M2 命中 M1 漏，"音量键坏了"M2 正确拒）；但**陈述句误报两者同为 4 条**（"下一首歌叫什么"→切歌、"这个截图工具叫什么"→截图），无槽位单词触发的误报类它管不了，"100% 确定"不成立；"彻底解决错别字"内部矛盾（AC 是精确子串，fuzzy 化=阈值重叠老问题）。数据顺带暴露"取消静音→mute"子串包含 bug（需长模式优先）——恰是它宣称要消除的维护灾难。

**方案二（模板编译正则）实测 47 条路由语料**：覆盖率 **2/34=6%**（口语"一下/的/还"插入词打散模板字面量），垃圾误报 0。94% 流量回落现状路径，净增一条无用代码路径。**拒绝。**

**结论**：分层表与我们现状同构；可采纳项仅"有槽位动作双要素+长模式优先"——一行写进客户端模板匹配规范（`_TEMPLATES` 本就是 patterns+slots 数据）。无槽位单词触发的陈述句误报正解是**不许旁路 LLM**（embedding+LLM 靠上下文判得对），与保守原则一致。

**方法论三连胜**：NLU（§三十）、本方案，均先过语料再定去留——任何"更优匹配器"提案的准入门槛已固化。

## 三十二、第三方自证脚本复核与交叉评测（2026-07-16，tests/manual/shadow_cross_eval.py）

第三方脚本（scratch/shadow_fastpath_eval.py）自报 100% 命中/0% 误报/100% 提取，与 §三十一 结论相反。复核发现其测试与我们项目真实情况脱节，三处结构性问题：

1. **基线是稻草人**：其"手写正则基线"仅 5 条 `^...$` 锚定模式+精确相等，未实现 next_track/screenshot/mute/lock_screen——不是我们客户端真实的 `_TEMPLATES`（50 条带槽位子串模式，M1 实测 16/19）。
2. **语料贴合实现**：宣称解决错别字但语料零错别字；生产真实翻车的陈述句陷阱零覆盖；仅有的两条陷阱靠匹配器内硬编码特判通过（`"的歌" in cleaned → None`、`best_app=="列表" and "商品列表" → None`）——不可枚举的补丁，恰是其宣称要消灭的维护灾难。
3. **方案二循环论证**：4 条测试语句与预注册模板字面形状完全一致；我们用 47 条真实路由语料测覆盖率仅 6%。

**交叉评测**（其 FuzzyDictMatcher 原封不动 × 我方 28 条生产语料 + 5 条错别字用例）：**13/28 正确，误报 5，漏/错 10**。误报含"声音真好听"→set_volume、"音量键坏了修一下"→set_volume、"帮我写个静音室的方案"→set_volume、"我在微信里打开了链接"→open_app。错别字实测："打开威信/微心"漏（2 字词错 1 字 partial_ratio=50<85）、"打开网抑云音乐"误开"音乐"（近音名含字典子串）——fuzzy 漏真错别字、误近音名，两头皆错。其 85 分阈值是阈值重叠问题的第三次重现（嵌入门/NLU/本轮）。

**可吸收项**：play_pause 长度守卫（剥"请/一下"后 ≤4 字才算媒体指令）正确拒掉"暂停一下我的理解"，与保守原则同向，可写进客户端匹配规范。§三十一 结论维持不变。

## 三十三、第三方第二轮（Hybrid：锚定结构正则+槽位校验+拼音容错）评审（2026-07-16，tests/manual/shadow_hybrid_falsify.py）

第三方承认问题后改提 HybridMatcher，自报 28/28 + 错别字 5/5。复核结论：**方向收敛、证据再次失真、方案二被静默放弃**。

**实质变化（值得肯定）**：锚定 `^...$` 全句结构匹配替代子串包含——这正是把保守原则应用到客户端 L0 的正解，陈述句陷阱类 FP 被结构性消除（"暂停一下我的理解""下一首歌叫什么"等全部天然拒识）；模式排序修正（mute 先于 set_volume，修掉上轮"取消静音"bug）；**方案二（宏模板正则）整个消失**=默认我们 6% 覆盖率的实测结论。方案范围收缩为纯客户端 L0——即变成"我们已有 `_TEMPLATES` 层的匹配规范改进建议"，不再是竞争系统。

**证据再次失真**：`PINYIN_SPEC` 是 24 条手写答案表（预登记了测试用的 威信/微心，甚至把错拼 "qidung" 写进表里），不是拼音转换。探针 A：未登记的同音字"维信/围信/未信"全部漏检——真实实现须用 pypinyin（我们的 VoiceInitSpec 本就在逐 app 下发 `entry["pinyin"]`，客户端未用于匹配）。

**阈值重叠第四次重现（在他自己的表里）**：探针 B：表中 微型(weixing) 与 微信(weixin) 编辑距离=1 ≤ 其阈值，"打开微型"误开微信。修法：拼音**精确相等**即可（真同音字距离恒为 0，距离 1 只买 FP），同音候选用已下发的 `app_usage_rank` 决胜。

**覆盖率天花板（探针 C，可接受的代价）**："把音乐暂停一下""帮我把音乐关了""截一下屏幕"等未枚举语序全部回落——保守设计使然，由 embedding+LLM 兜住，与我们的分层一致。

**最终可采纳规范（客户端 L0 匹配器，合并 §三十一/三十二）**：①锚定结构模板；②长模式优先+动作排序（否定式先于肯定式）；③有槽位动作双要素（动词+槽位字典命中）；④槽位拼音精确相等兜底同音错别字+usage_rank 决胜；⑤短句长度守卫。五条全部是客户端匹配规则，`VoiceInitSpec` 数据格式零改动。LLM 终审与 embedding+LLM 主路径维持不变。

## 三十四、第三方匹配器提案三轮评审总结（2026-07-16，对方认输，结案）

**三轮轨迹**：①字典交集+宏模板正则（§三十一：边际/6% 覆盖，拒）→ ②FuzzyDict 自证 100%（§三十二：稻草人基线+语料贴合实现，交叉实测 13/28）→ ③Hybrid 锚定正则+拼音（§三十三：方向收敛、证据再次失真、方案二静默放弃）→ 认输。

**可吸收（五条客户端 L0 匹配规范，VoiceInitSpec 数据格式零改动）**：
1. 锚定结构模板（`^...$` 全句匹配）——陈述句陷阱类 FP 的结构性消除，本轮最大收获；
2. 长模式优先 + 否定式先排（unmute 先于 mute，修"取消静音→mute"）；
3. 有槽位动作双要素（动词+槽位字典命中才放行）；
4. 拼音**精确相等**兜底同音错别字 + `app_usage_rank` 决胜（`entry["pinyin"]` 本就在下发；距离≤1 会引入 微型/微信 类 FP，真同音字距离恒为 0）；
5. 短句长度守卫（剥语气词后 ≤4 字才算媒体指令）。

**拒绝（均有实测数据）**：fuzzy 阈值匹配（rapidfuzz 85/80、拼音距离≤1——阈值重叠四次重现：嵌入门/NLU/fuzzy/pinyin）；AC 字典交集替代模板；宏模板编译正则（口语覆盖率 6%）；一切硬编码特判（"的歌"guard、"商品列表"guard、PINYIN_SPEC 答案表——不可枚举补丁=其宣称要消灭的维护灾难）。

**元教训**：①shadow 语料评测作为匹配器准入门槛已固化，四轮提案（fast-path NLU、NLU 换正则、字典交集、Hybrid）全部先过语料再定去留；②自建语料必贴合自建实现（对方两轮皆然），只有生产语料+交叉评测（他的匹配器×我们的语料）能破局；③对方的真实贡献是**把保守原则在客户端 L0 落地为具体匹配规则**——方向始终在我们架构内，最终沉淀为规范而非新系统。

## 三十五、L0 参考匹配器落地与实测（2026-07-16，全绿结案）

§三十四 五条规范已实现为后端参考匹配器 `app/core/routing/local_matcher.py`（客户端照此移植），配套数据修正与依赖落地：

- `local_matcher.py`：锚定结构匹配（语气词前后缀剥离）+ 最长字面优先 + 槽位字典校验（delta/key 最长键包含、app 精确/别名）+ 拼音**精确相等**同音兜底（`app_usage_rank` 决胜；拉丁名 len≥4 允许编辑距离 1）+ 保守回落（不匹配即 None 交 embedding+LLM）。
- `init_spec.py`：截图模板补"截个图"；发货模板经 `sorted_templates` 最长字面优先（"取消静音"先于"静音"）；**pypinyin 已入依赖**（uv add），本机 87 个 app 条目拼音覆盖率 87/87（此前为可选依赖、实际未装）。
- 单测 `tests/unit/core/routing/test_local_matcher.py` 47 例全过；全量 1114 passed / 7 skipped；ruff/mypy 干净。

**实测（tests/manual/shadow_final_matcher_eval.py，40 条）**：19 生产指令全中（含 M1 原漏的"声音小点/取消静音/截个图"）；9 陈述句陷阱全拒（锚定结构性消除）；错别字全对——含第三方答案表外的"维信/围信"（真 pypinyin 转换）、"打开VSCod"（拉丁距离 1）、"打开网抑云音乐"→网易云音乐（拼音全等，**解析到正确的 app**；原陷阱针对的是子串误抓"音乐"）；"打开微型"正确拒（weixing≠weixin，距离≤1 方案在此必翻车）；未枚举语序（"把音乐暂停一下"等）保守回落零误触。**40/40，误报 0，漏检 0，单次匹配 0.006ms。**

**结论**：三轮评审沉淀的五条规范从纸面落到代码并以生产语料+交叉语料验证；客户端按 `local_matcher.py` 移植即可，VoiceInitSpec 数据格式零改动。

## 三十六、穷举测试与客户端移植（2026-07-16，双端全绿）

**后端穷举测试（tests/unit/core/routing/test_local_matcher_exhaustive.py，生成式非抽样）**：
- 全组合正例 **8736 条**（32 无槽模板 + app×9 动词模板×8 条 + 音量 4 模板×10 delta + 按键 3 模板×14 key，全量 × 7 前缀×6 后缀），每条须命中**自己的** action/槽位=交叉碰撞审计；
- 陈述框架 12×12=144 条全拒；槽位污染 48 条全拒；拼音边界四角（微信/微型/维信/威信）；真实 spec 审计（build_init_spec 88 个真实 app 全部 打开/关闭/切换 自解析+同音组审计）。
- **穷举立刻抓到 40 条语料漏掉的真 bug**："按下左"→Down（应 Left）——排序键取模板级最大字面长，press_key 模板内"按{key}"排在"按下{key}"前吞掉"下左"。修为按**模式自身**字面长排序（local_matcher.py）。

**客户端移植（evoloop-voice-buddy Layer0Matcher.mm，与参考实现逐条对齐）**：
- 语气词前后缀剥离（**原文+规范化双变体匹配**——单剥会打断"停一下/按一下"这类以后缀字结尾的模板）；模板编译期按模式字面长排序；map 槽位补最长键包含（"调小一点"→-10）；app 槽位后缀噪声剥离（浏览器/软件）；拉丁模糊门槛对齐 len≥4。
- CJK 拼音经 **CFStringTransform** 本端计算+编译期缓存，相等性判定+app_usage_rank 决胜。
- **移植抓到跨引擎多音字坑**：pypinyin"音乐"→yinyue，CF→yinle——后端下发的 entry["pinyin"] 与客户端现场转换不相等。修法：客户端条目拼音一律本端引擎计算（同引擎一致性优先于罗马化"正确性"：网抑云音乐/网易云音乐同转 wangyiyunyinle）。

**实测**：客户端 voice-unit-tests **210/210**（新增 testLayer0Rules534：语气词/11 条陈述陷阱/按下左/拼音四角/网抑云/VSCod），ctest 2/2（含真实 LM Studio 的 test-writer），bench p95 **5.4µs**；后端 1119 passed / 7 skipped，ruff/mypy 干净。Layer0MatcherTests.mm（XCTest 镜像）同步补例。

**结案**：五条规则从评审→参考实现→穷举验证→客户端移植全链路闭环；穷举方法论再次证明语料抽样的盲区（8736 抓 1 bug，40 条抓不到）。

## 三十七、抽样扩至 140 条与复合句半截执行缺陷修复（2026-07-16）

40 条抽样扩为 **140 条人工标注、9 类独立统计**（tests/manual/shadow_final_matcher_eval.py）：A 裸指令全字面量 32、B 语气词 16、C 音量/按键 17、D app 14、E 同音错字 12（含"打开终湍"非谐音必拒）、F 陈述陷阱 28、G 复合句 9、H 边界标点 7、I 英数混排 5。

**扩样立刻抓到新缺陷类——复合句半截执行**："把音量大一点再静音"→set_volume(+10)（放大执行、静音丢弃；比纯误报更糟）。修法：**map 槽位包含匹配的余量必须是填充字符**（delta: 调给我到一点下把；key: 键一下），余量含实义触发词→逐键降级→整体拒识回落 L1（"大一点再静音"所有键余量均脏→None）。正面用例同步保住："音量调到一半"（余量"调到"）→50、"按一下回车键"（余量"键"）→Return。顺带补齐客户端标点剥离对齐（"暂停。"可命中）。

**实测（修复后）**：140/140，FP 0，MISS 0，0.005ms/条；后端 1127 passed；客户端 221/221，bench p95 5.4µs，ctest 2/2。

**方法论再验证**：测试规模每上一个量级就抓一个新缺陷类——40 条（抽样）→ 140 条（复合句 FP）→ 8736 条（排序 bug）。三层测试体系定型：**语料抽样（manual eval，人读）+ 生成式穷举（unit，CI 门）+ 双端 parity 移植测试**。

## 三十八、L0 匹配延迟分路径实测（2026-07-16，生产形态 87-app spec）

**客户端（Obj-C 发布二进制，-O2，500 预热+5000 次/路径）**：
字面命中 0.85µs | 语气词 1.12µs | app 精确槽位 3.11µs | delta 包含 6.82µs | 拼音路径 45.6µs | 拉丁距离 57.8µs | CJK 回落 44.2µs | 陈述句回落 2.57µs | 复合句拒识 8.28µs | 未知回落 2.77µs。设计目标（§14.6）<50ms——**最差路径 57.8µs，余量约 860 倍**；媒体控制类热路径 ~1µs。拼音/拉丁路径的 45~58µs 主要是单次 CFStringTransform/编辑距离扫描 87 条目的成本，仅在 app 槽位话语触发。

**后端 Python 参考实现（同 spec，300 预热+3000 次）**：2.3µs（字面）~23µs（拉丁），app 槽位类 ~19µs（87 条目线性扫描），陈述/未知回落 ~3.4µs。

**对比 Layer-1**：embedding+LLM 服务端路由为数百 ms~秒级——L0 命中节省 **3~4 个数量级**延迟且离线可用；回落代价（~3µs）相对后续网络往返可忽略。

## 三十九、语音指令→动作完成 全链路性能实测（2026-07-16，Agent 路径除外）

**链路分段（生产形态：sherpa-onnx zipformer + L0 + 真实执行 / 服务端 LLM 路由 + Playwright 宏，商城 9002 真实环境，两轮取一致值）**

**L0 本地路径（媒体/系统指令）**：
| 段 | 耗时 | 说明 |
|---|---|---|
| 语音端点检测 | 800 ms | 固定管道成本（config vad.silence_sec=0.8） |
| ASR 解码 | 12~75 ms | RTF≈0.02（暂停 12ms/968ms 音频 16ms/3.2s 长句 75ms；`say` Ting-Ting 生成真实语音） |
| L0 匹配 | 0.001~0.06 ms | §三十八 |
| 本地执行 | 1.1~8.5 ms（暖）/ 47~129 ms（冷） | play_pause 暖 1.1ms、set_volume 暖 1.6ms、open_app 8.4ms；冷启 AppleScript/Music ~119ms |
| **合计（语音止→动作成）** | **≈0.82~0.9 s** | 端点检测占 ~90% |

**L1 服务端路由路径（商城宏指令，text→done 经 voice_ws 实测）**：
| 指令 | 路由决策 | 宏执行 | 全程 |
|---|---|---|---|
| 打开商品列表（冷） | 1273 ms | 2176 ms | 3450 ms |
| 查钥匙扣价格 | 3329 ms | 4209 ms | 7538 ms |
| 查钥匙扣库存 | 3223 ms | 5306 ms | 8529 ms |
| 打开订单列表 | 3603 ms | 2193 ms | 5796 ms |
| **暖态均值** | **3385 ms** | **3903 ms** | **7288 ms** |

加上语音侧（端点 0.8s + ASR ~0.1s），**L1 语音指令→动作完成 ≈ 4.3~9.4 s**。

**瓶颈排序**：①宏执行（浏览器 navigate/等待/提取，2.2~5.3s）≈ ②路由 LLM（3.4s）＞ ③端点检测（0.8s，L0 路径的唯一大头）＞ ASR/L0 匹配（可忽略）。优化方向（未做）：路由决策流式化/缓存、宏执行 wait 策略收紧、端点检测 silence_sec 调优。

## 四十、路由决策缓存落地（2026-07-16，开关 ROUTE_CACHE_ENABLED，默认开）

**设计（保守原则全保留）**：`app/core/routing/route_cache.py` + `router.route_many` 接入，插入点在**指代改写之后**（会话相关文本永不成为键）——键=`(LanceDB 数据集版本:行数, 归一化文本)`（仅剥标点/空白/小写，**拒绝语义相似键**=阈值重叠不复活）；索引重建/宏变更→版本变→全量隐式失效；TTL 24h + LRU 512 兜底；**clarify 决策永不入缓存**（单测断言）；开关 `ROUTE_CACHE_ENABLED=1|0`。

**单测 10 例**（归一化/版本失效/TTL/LRU/开关/route_many 集成：第二次不调 route()、禁用后每次都调、clarify 不入缓存）全过；全量 1137 passed。

**生产实测（perf_voice_chain.py 每指令发两遍，真 LLM+真浏览器）**：
| 指令 | miss 路由 | hit 路由 | 提速 |
|---|---|---|---|
| 查钥匙扣价格 | 3359 ms | **79 ms** | 42x |
| 查钥匙扣库存 | 3306 ms | **78 ms** | 42x |
| 打开订单列表 | 3547 ms | **63 ms** | 56x |

hit 后全程 = 缓存路由(~0.08s) + 真实宏执行（导航类 ~1.0s/查询类 ~5.3s）≈ **1.1~5.4s**（原 3.5~8.8s）。一次观察："打开商品列表"第二遍未命中=服务器启动时后台 rebuild 竞态致版本跳变——缓存行为正确（miss 后按新版本重存），稳态版本经探针验证恒定。

**L1 链路最新预算**：重复指令 0.8s(端点)+~0.08s(缓存路由)+宏执行 1~5.3s ≈ **1.9~6.9s**；新指令维持 4.3~9.4s。剩余大头=宏执行等待策略（未动）。

## 四十一、M1 AX 可行性探测：go（2026-07-16，atlas_native_ax_probe_v2.py）

**覆盖率分级**（9 应用，窗口区/菜单栏分开计分——菜单栏普遍完整会掩盖内容区残缺）：
| 层级 | 应用 | 判定依据 |
|---|---|---|
| A(完整) | Calculator, System Settings, Safari, Finder, Notes | 窗口交互命名 16~141，命名率 30~71% |
| B(部分) | Music, Terminal | 交互命名 9~13，可用但覆盖有限 |
| C(残缺) | WeChat, VSCode | WeChat 窗口仅 16 元素/4 交互命名；VSCode 3 交互 0 命名且 AXEnhancedUserInterface 开关 +0（Electron 增强对本机 VSCode 无效） |

**ax_path 重启稳定性**（pilot 4 应用，(role,name,path) Jaccard，进程级 pkill→重启→重 dump）：
Calculator **1.00**（27/27）、System Settings **0.96**（55→57）、WeChat **1.00**（9/9）、Music **0.69**（46→45，内容为动态歌名/专辑名——名称型路径天然漂移，选择器须结构 role+index 优先、名称降级为提示）。

**架构级实测事实**（推翻/修正设计假设）：
1. **AX 全程免焦点**：`AXUIElementCreateApplication(pid)` 可 dump 任意运行中应用（macos_driver 的"仅前台"是实现伪限制）；**AXPress 作用于后台应用经读回验证**（前台保持 VSCode，后台 Calculator 依次按 3×3=，AXStaticText 读回 "3×3"/"9"）。焦点仅在 CGEvent 键盘注入时需要 → **宏执行不打断用户**，G3/G4 客户端执行器可全后台。
2. **启动配方**：`open -b`（非 `-g`）+ 轮询"窗口实体化"（windows>0）而非 pid——`-g` 下应用可能不报 running 且永不建窗；forceTerminate 后 LaunchServices 有再启动冷却，open 需在轮询循环内重试。
3. **NSWorkspace 快照陷阱**：`runningApplications()/frontmostApplication()` 是通知喂的快照，无 runloop 的进程内永不刷新（此前"杀不掉/启动失败"全是假象）。存活判定改 `pgrep -f <executablePath>`（路径取自 NSBundle），terminate 改 `pkill -f`；frontmost 验证前须 spin NSRunLoop。
4. `AXValueRef` 位置尺寸必须 `AXValueGetValue` 解包，直接读属性会得到 0 bounds（已修）。

**M1 结论：go**。A/B 级 7/9 应用可做确定性宏；C 级（WeChat/VSCode）按既定策略进 DynamicAppTriage/Agent+OCR 兜底，不做确定性承诺——pilot 三应用（Calculator/Settings/Music）全在 A/B 内，M2 主动测绘器开工无阻塞。选择器设计约束写入 G2：结构优先、名称降级、动态内容（Music 型）接受路径漂移并靠复采。

## 四十二、M1.5 动作原语矩阵：文本可免焦点写入（2026-07-16，atlas_native_action_matrix.py）

**核心问题（决定 G2/G4 架构）：文本能否免焦点写入？答案：能。** 全程后台（前台=TextEdit/iterm2 期间未切走）：

| 应用 | 目标字段 | AXValue settable | set+读回 |
|---|---|---|---|
| Safari | 智能搜索栏（地址栏） | ✓ | PASS |
| System Settings | 搜索栏 | ✓ | PASS |
| Music | 搜索栏 | ✓ | PASS |
| TextEdit | 真输入框 ×18 | ✓ | PASS |
| WeChat | 窗口区无文本角色（C 级实证） | — | 不可测 |
| Calculator | 显示区 | — | （只读，未试写） |

**其他原语**：AXPress 后台再验（Calculator 4×5=20 读回 PASS）；AXShowMenu/AXCancel（TextEdit AXPopUpButton err=0）；动作清单（`AXUIElementCopyActionNames`）：AXButton=[AXPress(,AXShowMenu)]、AXTextField=[AXConfirm,AXShowMenu(,AXShowAlternateUI)]、AXSlider=[AXIncrement,AXDecrement]、AXCheckBox=[AXPress]——**生成器可按 role 预填动作白名单**。

**陷阱与规则**（TextEdit 8 例 set_err=0 但读回原值）：打开面板文件列表的文件名单元格也是 AXTextField 且 settable，但非编辑态写入静默无效（值为'素材与设计稿'/'edited.json'等文件名，AXWindow=None）→ **G2 生成期自检规则：键入宏生成时必须现场 set+读回+恢复，读回通过才允许出 AXSetValue 步骤**；文件列表单元格（container 内、无 AXWindow）不得作键入目标。

**启动配方修订**：`open -b` 启动**冷应用会抢一次焦点**（TextEdit 实测；热启动/已运行应用不抢）。对焦点敏感场景：启动前记录前台 app，启动后如被偷则 `osascript activate` 还原；纯后台宏优先操作已在运行的应用。

**M1.5 结论**：键入宏架构定案=**AXSetValue 免焦点点写 + 读回验证**，CGEvent 键盘仅作 fallback（逐键输入/IME 场景）；G4 执行器全流程免焦点成立。

## 四十三、M2 主动测绘器落地（2026-07-16，surveyor.py + atlas_native_survey_pilot.py）

**组件**：`app/core/atlas/surveyor.py`——按 pid 免焦点测绘；元素带 AXActions 全清单；窗口区/菜单区分开计分；state=结构签名（role,name,path 集合）`sig_<sha1>`（非窗口标题）；探索可选（AXRow/AXTab，标签黑名单，无名行取后代标签——macOS 边栏真实形态）；**合并存储**（历史 state 保留，不再整 app 覆盖）；`needs_resurvey`=实时指纹 vs 全部已存 state Jaccard<0.8 触发。菜单树持久化为 `__menubar__` 特殊 state（免迁移），MenuTree 内存对象供 M3 生成器。

**顺手修两个存量 bug**：①`sql_store.save_app_model` 更新路径 `app_record.states` 懒加载在 async 下必崩 MissingGreenlet（改显式 select）——即"覆盖保存"从未在 async 成功过；②探索点击原语升级 `activate_at_path`（无 AXPress 的行先试 AXSelected=True，NSOutlineView 边栏行标准模式）。

**Pilot 三应用实测（真库）**：
| 应用 | tier | sig states | transitions | menubar 项 | 菜单可达率 |
|---|---|---|---|---|---|
| Calculator | A | 1 | 0 | 155 | 100% |
| System Settings | A | 15 | 22 | 183 | 100% |
| Music | B | 4 | 4 | 234 | 100% |

**验收对照**：菜单可达率 ≥90% → **100%×3**（指标口径经 System Events 交叉验证：无名 AXMenuItem=separator，现代 macOS 上也带 AXPress/AXPick/AXCancel 动作）；三 AtlasApp 入库 ✓（含 __menubar__ 与 transitions）；重测 state_id 全部已存在 ✓；needs_resurvey=False ✓；探索期零写动作（黑名单+仅导航行）。

**单测 16 例**（签名稳定性/黑名单/菜单树层级/可达率口径/只读测绘/探索转移记录/无名行后代标签/合并保历史/复采三态），全量 **1153 passed**。

**已知边界**：探索是贪心链式（非全 BFS 回溯）；Music 边栏行部分不触发新 state（行内已选中态）；窗口区动态内容（Music 歌名）仍会产生新 sig state——靠合并累积+复采收敛，符合设计。

## 四十四、Pilot 改=高频应用（2026-07-16 用户指正，替代 Calculator/Settings/Music 生产定位）

**高频四应用测绘实测**（M2 测绘器，只读策略）：
| 应用 | tier | 窗口交互命名 | 菜单项(命名交互) | 菜单可达率 |
|---|---|---|---|---|
| Chrome | A | 38 | 2001(1957) | 100% |
| iTerm2 | A | 33 | 465(364) | 99.7% |
| WeChat | B | 14 | 168(141) | 100% |
| Lark(飞书) | C | **0** | 150(128) | 100% |

**结论**：①菜单通道四应用全通——R3"C 级菜单宏"路径对高频 Electron 应用成立（Lark 窗口 0 命名交互但菜单 128 项全可达）；②Chrome 菜单含书签/历史等动态内容（2001 项）→ 生成器须区分静态菜单基础设施 vs 动态菜单内容；③Electron 增强开关死路：AXEnhancedUserInterface/AXManualAccessibility 对 Lark/WeChat/Chrome `AXUIElementSetAttributeValue` **直接返回错误**（M1 VSCode 是 rc=0 但 +0，本批更彻底）——C 级 Electron=菜单宏+Agent/OCR 兜底，不硬撑；④UsageRanker 的 Spotlight last_used 全空、评分均匀（0.2）——目标选择按用户指定，测绘目标优先级机制暂不可用；⑤钉钉未安装不覆盖。

**M3 目标改**：Chrome 全链 E2E（A 级双通道）+ WeChat/Lark 菜单宏作 C 级验证样本。

## 四十五、M3 原生宏生成器+执行链路（2026-07-16，native_factory + ax_actions + engine 扩展）

**组件**：①`app/core/atlas/ax_actions.py` 运行时原语（locate/press/activate/**press_menu_labels 标签链菜单导航**/set_value+读回/**find_by_role_label 运行时解析**）；②`app/core/atlas/source/native_factory/` 生成器（菜单宏=open_app+ax_menu_press 标签链；字段宏=ax_set_value{{text}}+AXConfirm——payload 带 role+label 优先、ax_path 兜底；规则=动态根跳过/黑名单叶跳过/退出类需确认/深度≤3/枚举叶+长标签过滤/文件名单元格容器拒绝/字段标签 stopwords）；③engine `_execute_desktop_step` 新增 ax_press/ax_menu_press/ax_set_value 分支+open_app focus=false 免焦点启动；④事件类型入 MacroActionType+风险映射（ax_press/ax_menu_press=act、ax_set_value=data，family 全 act，语音策略天然放行）；⑤持久化 namespace="native_macos"、app_map_id=None、**幂等**（同名先删后插）。

**E2E 实测（atlas_native_macro_e2e.py，真引擎真应用）**：生成 **582 宏**（Chrome 172/iTerm2 272/WeChat 76/Lark 62，含需确认 4/5/3/2）——Chrome 打开网址→**地址栏读回 'https://example.com' PASS**；Chrome 新标签页 ok；WeChat 微信>关于微信 ok；Lark 飞书>关于飞书 ok；4 宏 verified+routable。**全程免焦点**。

**实测逼出来的三个设计修正**：①**存库 ax_path 会随 UI 演化失效**（首轮 E2E 地址栏路径已漂移致 FAIL）→ 字段宏执行改 role+label 运行时解析、ax_path 仅兜底，改后第二轮 PASS——选择器分级在"结构会漂移"场景下的实战印证；②Apple 根菜单是 OS 级垃圾（最近使用项/徽标后缀"App Store…，9项更新"），整根跳过（206→172）；③标签页/窗口菜单动静混合→枚举叶（^\d+[\.、)]）+超长标签过滤保留静态命令。

**运维教训**：E2E 脚本永不执行 com.googlecode.iterm2 的宏（自残守卫：关窗/退出会杀掉宿主终端）；重复执行经幂等持久化+pending 清理收敛（曾两轮堆 1324 行重复）。

单测新增 11 例（生成规则全谱），全量 **1161 passed**。

## 四十六、M4 路由接入+语料实测+G5 安全门（2026-07-16，atlas_native_m4_pipeline.py）

**G5 落地**：`script_gate.py`——applescript 静态审查（禁 do shell script/with administrator privileges/sudo/嵌套 osascript，接入 DesktopController applescript 唯一 choke point）；native 步骤默认拒绝白名单（env EVO_NATIVE_STEP_WHITELIST，command+script_prefix+sha256 三重，接入 `_handle_native`）。单测 17 例。

**管线**：安全子集批量验证（ui 层免确认）→ rebuild_route_index → **122 条路由语料（只路由不执行）** → 白名单执行子集。

**路由语料结果（真 LLM qwen3-4b + 真 LanceDB）**：
| 应用 | 命中 | 备注 |
|---|---|---|
| Chrome | 26/32 | |
| iTerm | 27/30 | |
| 微信 | 17/30 | |
| 飞书 | 20/30 | |
| **总体** | **90/122 (74%)** | |
| **按类型：qualified(app+命令)** | **38/40 (95%)** | **生产主导形态** |
| bare(裸命令)/polite(帮我+) | 25/40、26/40 | 标准菜单跨应用同名歧义 |

**执行子集 4/4**（Chrome 新标签页/iTerm New Tab/WeChat 关于微信/Lark 关于飞书）+字段宏读回 PASS（§四十五复测）。

**语料驱动的生成器三轮净化**：①剔除 Apple 根菜单遗留垃圾（249 条已验证旧宏污染索引，全清+重建）；②根级宏（链长1，"Chrome Chrome"式）过滤；③macOS 标准窗口平铺子菜单（全屏幕拼贴/移动与调整大小）全应用全同+近亲对——最大混淆簇（27 miss 中 15 条）→ 整类过滤；④persist 按应用前缀替换（曾整 namespace 清空致逐批互抹）。现存 miss 主类=标准编辑/窗口命令（全选/放大/进入全屏/全部最小化）裸命令跨应用歧义——**qualified 语句 95% 证明宏质量本身达标**；bare 歧义的根治方向=路由层按 usage_rank/活动应用偏置或 clarify-on-ambiguity（记 backlog，不在 M4 范围）。

**验收对照**：宏 E2E 执行成功率 100%（≥95% 达标）；路由 qualified 95%；语料 122 条 ≥30/应用 ✓；单测全量 **1180 passed**。

## 四十七、维护任务+路由偏置+M5 别名+真语音 E2E（2026-07-16 晚）

**垃圾宏治理（设计评审结论）**：不定独立"扫描删除"任务——垃圾只有两源：生成规则演进后的旧数据残留、测绘漂移。对策=把清理做成管线内在属性：`app/core/atlas/maintenance.py`（needs_resurvey→只读测绘→再生成→**按应用前缀整批替换**→批量验证安全子集→重建索引；单应用宏数>500 护栏告警）+`tasks.py` Huey 12h 周期（错开 6h init-spec 重建）；`EVO_NATIVE_SURVEY_APPS` env 覆盖测绘集。9 编排单测。

**bare 命令路由偏置（`routing/native_bias.py`）**：两条确定性信号，不动 LLM——①显式应用名纠偏（'飞书左侧' 永不落 Chrome，候选名自带别名做子串判定）；②frontmost 应用兜底（真·裸命令时用户盯着谁就是谁，NSWorkspace frontmost）。**缓后应用铁律**：偏置在 route_cache 读取之后执行，活动应用上下文绝不烘进缓存决策。别名取**候选集内区分 token**（'窗口'在所有应用头段出现，自动剔除），防误判。12 单测。M4 语料复跑：总 74%、qualified 95% 保持、飞书类显式误路由清零；bare 未显著变化（批跑时 frontmost=终端，且剩余 miss 主因是中英叶名不匹配——'放大' vs 'Make Text Bigger'，生成期别名翻译记 backlog）。

**M5 L0 别名生成化**：评估结论——L0 手写模板（音量/媒体/锁屏/截屏/open_app 槽模板）全是系统级固定动作，按 G4 **无退役**；可生成的是 **{app} 槽词典的中文别名**（原先 `_probe_apps` aliases 恒为空，'打开微信'在 L0 无法解析）。实现：别名=测绘数据里**第一个 AXMenuBarItem 标签**（应用菜单根惯例居首，跳过 Apple 根）≠canonical 即为口语别名；bundle_id 优先匹配（安装探针实为运行快照，可能只有 'Lark Helper'，Atlas 数据兜底补独立条目）。`init_spec.enrich_spec_with_atlas_aliases` 挂入 `tasks._rebuild`。真机产物：微信/飞书/计算器/系统设置→WeChat/Lark/Calculator/System Settings 全入 slot 词典。4 单测。

**真语音全链 E2E（`atlas_native_voice_e2e.py`）**：say 合成→**sherpa-onnx python 绑定（客户端同款 streaming zipformer 模型）**→voice.route ws→原生宏真实执行。结果：'关于微信'→ASR '关于关于微信'→**WeChat 微信>关于微信 执行 done PASS**；'新建标签页'→ASR 同音误判'新建标签也'→错路由到'为标签页建组'（执行 done，FAIL 归 ASR 噪声类，§24 已立近音纠错 backlog）。**环境坑归档**：sherpa-onnx **1.13.4 python 绑定与该 2023 模型不兼容**（解码恒空），钉 **1.10.46**；语音名是 `Tingting` 无连字符；整文件一次性灌流需 `decode_streams`+numpy float32+0.66s 尾垫。

**基线：1205 unit passed / 7 skipped。**

## 四十八、语音响应策略收口+全分支多样性测试（2026-07-16 晚②）

**修复①：done 空 summary 沉默漏洞**。客户端 `done`+summary 空时静默返回（用户听完"请稍后"后无下文）；native 宏引擎 msg 恒空必踩。服务器侧兜底：macro done 空 msg→`已完成{叶名}`（`executor._run_macro`）；skill deterministic 空 message→`已完成{skill名}`，failed 空→`处理失败`。客户端零改动。

**修复②：clarify 客户端黑洞**。服务器推 `status=clarify` 但 `didReceiveRouteResult` 无分支——澄清问题从未被播报。`Dispatcher.mm` 补 clarify 分支：清超时+TTS 播报问题，用户下一句经 session pending 续接。

**多样性测试（全分支）**：服务器 `test_executor_responses.py` 20 例——local 无播报无执行/macro done（短文原文|空→叶名兜底|长文不截断）/not-found/未确认/缺 query→clarify/缺非 query→failed/坏脚本/移动源门禁/失败×自愈开（交 Agent 不推 failed）×自愈关（failed+原因）/skill not-found/门禁错/done 兜底/failed/agent 直派无推送/异常兜底/多意图 resolve 失败→方案乙+独立意图续跑。客户端 `testDispatcherRouteResultDiversity` 9 例——routed macro→请稍后/routed local→本地执行零播报/done 短文原文/done ≥100 字→"已完成详情到 Evoloop 查看"/done 空→沉默/failed 原文/failed→error 兜底/failed 全空→处理失败/clarify→播问题。

**基线：后端 1225 passed / 7 skipped（+20）；客户端 voice-unit-tests 231 passed（+10）。**

## 五十、大规模真实全链路 E2E 与并发实测（2026-07-16 晚④）

新增 `tests/manual/voice_chain_real_exhaustive.py`：28 条真实 uvicorn+websocket+浏览器+原生应用用例，覆盖 L0 本地动作、Web 读宏、Native 宏、多意图、指代、澄清、路由缓存、未知兜底。结果：**24/28 PASS**。

**挖出的真实问题**：
1. **L0 动作被宏覆盖**："音量大一点" / "打开微信" 被路由成宏（`done`），而不是 `local` 的 `set_volume` / `open_app`。原因：route_index 中同时存在同名/近义宏，检索+LLM 没有给 L0 固定动作足够的优先级。修复方向：L0 模板在服务端 route_index 中加权，或客户端 L0 命中直接短路不送路由。
2. **多意图未分解**："查一下夜光亚克力钥匙扣的价格和库存" / "关于微信然后关于飞书" 都只返回单意图（`intents=None`），LLM 分解失败。修复方向：decompose 提示词/示例增强，或对接连动词显式切分。
3. **浏览器页面对并发不安全**：`tests/manual/voice_chain_concurrent_e2e.py`（3 线程同时读同一句）暴露 `browser_manager.get_page()` 返回单一页面对象，多个宏并发操作同一页导致 selector 等待超时。这是真实系统级竞态，需为每个 voice 线程/每个宏执行分配独立 context/page 或串行化浏览器宏执行。

**仍然健康部分**：澄清复接（"查一下它的价格" → clarify，续接实体 → done）、路由缓存（连续重复同句 76ms/69ms）、指代链（"它的库存"/"这个售价"）、Native 宏多应用执行均 PASS。

**基线保持：后端 1293 passed / 7 skipped；客户端 231 passed。**

## 五十一、真实多轮对话 E2E（2026-07-16 晚⑤）

新增 `tests/manual/voice_chain_multiturn_e2e.py`：4 轮同线程连续对话，测试会话上下文（clarify → 实体 → anaphora → anaphora）在真实 uvicorn+websocket+浏览器 链路上的连续性。

用例：
- T1: "查一下它的价格" → clarify
- T2: "夜光亚克力钥匙扣" → done（建立 `current_entity`）
- T3: "那库存呢" → anaphora 续接，done
- T4: "这个售价是多少" → anaphora 续接，done

结果：**2/4 PASS**。

**挖出的真实问题**：
1. **T2 的宏执行改变了浏览器页面**，路由层发现 `frame probe mismatch`：帧期望 `editgoods?goods_id=2`，实际在 `lists`，导致后续帧被 clear；T4 回退到 clarify（"请问是哪个商品？"）。说明多轮对话中**浏览器导航会冲掉 session_frame**，路由器没有将目标实体与“商品列表”这类页面解耦。
2. **T3 超时未返回**：T2 触发的 agent 后台任务在 `wait_for .layui-table-body tr[data-index='0']` 上 10s 超时，且异常未被及时消化，导致同一 voice 线程被阻塞，后续 T3 收不到响应。这是多轮对话中**后台 agent 与同步 voice.route 竞合**的问题：前一个宏的 agent 未完成，后续用户话语已到达。

**通过部分**：T1 clarify 和 T2 done 正确完成，说明 clarify → entity 的连续链路本身是通的。

## 五十二、API + Worker 真实服务运行与飞轮沉淀验证（2026-07-16 晚⑥）

用户要求启动完整服务并做无死角测试。操作：
1. 用 `bin/evo start` 启动 API（端口 20160）+ Worker（Huey consumer）。
2. 修复 Worker 消费 `record_episode_task` 的导入错误：`trace_recorder.py` 原从 `app.core.memory.models` 导入 `Episode`，但该模型在 `app.core.memory.schemas`，已修正。
3. 修复 `verification_worker.py` 的 Controller 导入路径：原指向不存在的 `app.infrastructure.automation`，已改为 `app.core.environment.controllers.browser` / `desktop`。

重新运行真实链路测试：

- **`voice_chain_real_exhaustive.py`（28 例）**：结果 **24/28**，失败项同 §五十：L0 音量大一点/打开微信被宏覆盖，多意图未分解。
- **`voice_chain_multiturn_e2e.py`（4 轮）**：结果 **2/4**，T3 超时、T4 因浏览器导航导致 frame mismatch 回退到 clarify（同 §五十一）。
- **`voice_chain_concurrent_e2e.py`（3 线程并发）**：失败，确认共享 browser page 在并发写宏时产生 `Page.title: Execution context was destroyed` / 定位超时。
- **新增 `voice_edge_cases.py`（6 例）**：结果 **3/6**。
  - `查一下夜光亚克力钥匙扣的价格，然后把它降10%` → `done` 但 `intents=None`，依赖型多意图未分解。
  - 重复 `message_id` 第二次 → `TimeoutError`：重复检测只静默返回，未给客户端回推结果。
  - 同线程切换实体（`那换成查金属徽章的价格`）→ `TimeoutError`：旧实体被 frame clear 冲掉，新意图执行时找不到元素。
  - 空文本、首次查询、查价格均符合预期。

### 飞轮沉淀验证

Worker 在修复导入后成功消费 `record_episode_task`，产生两条新飞轮产物：
- `learned_skills` id=17 `macos_increase_system_volume`（来源线程 `real-1fed0d`，即 `音量大一点` agent 会话）。
- 配套飞轮宏 `macros` id=1218 `macos_increase_system_volume`（`app_map_id=None`）。
- `learned_skills` id=18 `ecom_product_price_lookup`（来源 `concurrent-2`），但宏指向百度搜索，非内部商城，质量较差。

用新增 `tests/manual/verify_flywheel_skill.py` 直接执行 `macos_increase_system_volume` 的宏（increment=1, max_volume=100）：**执行成功**，系统音量被调高 1%。证明生成的飞轮数据在功能层面是可运行的。

### 单元基线

`pytest tests/unit`：**1293 passed / 7 skipped**（导入修正后无回归）。

### 仍未覆盖/需要下一步验证的边界

- HITL / 高风险 money-tier 写宏确认流（如改价格）。
- 多意图依赖真正被分解并顺序执行（`depends_on` / `param_exprs` 路径）。
- L0 本地动作优先级高于同名宏。
- 并发场景下的 browser page 隔离或串行化。
- 重复 `message_id` 应回推缓存/忽略结果而非挂死。
- 多轮对话中浏览器导航冲掉 session frame 的解耦。
