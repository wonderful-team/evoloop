# Repository Guidelines

## 项目结构与模块组织

```
backend/
├── app/                    # 应用源码
│   ├── api/                # FastAPI 路由与端点
│   ├── core/               # 核心业务逻辑
│   │   ├── engine/         # Agent 执行引擎（单 Agent ReAct 主循环、状态、消息、回调等）
│   │   ├── routing/        # 通道无关 L0 路由与动作目录（voice/chat 共用）
│   │   ├── learning/       # 学习与技能合成
│   │   ├── memory/         # 记忆系统
│   │   ├── execution/      # 任务执行与工具链
│   │   └── vision/         # 多模态视觉处理
│   ├── config/             # 配置与 Jinja2 提示词模板（templates/core/）
│   ├── domain/             # 业务域（任务队列/规划/wiki/codebase 等，子包按域组织）
│   ├── models/             # SQLModel 数据模型
│   ├── services/           # 业务服务层
│   └── infrastructure/     # 基础设施（数据库、缓存等）
├── tests/                  # 测试用例（e2e 为主，保留核心 unit/integration 测试）
│   ├── e2e/                # 端到端测试（完整系统，需运行后端服务）
│   ├── unit/               # 核心模块单元测试（如宏引擎）
│   └── integration/        # 宏工具等集成测试
├── bin/                    # CLI 入口（evo 命令）与辅助脚本（bin/scripts/）
└── app/config/templates/   # Jinja2 提示词模板
```

## 构建、测试与开发命令

使用 `uv` 管理依赖，`bin/evo` 作为统一 CLI 入口：

```bash
uv sync                    # 安装所有依赖
bin/evo dev                # 启动开发服务器（热重载）
bin/evo worker             # 启动后台 Worker
bin/evo db migrate         # 运行 Alembic 数据库迁移
bin/evo lint               # 代码检查（Ruff）
bin/evo format             # 代码格式化
bin/evo check              # 全面检查（lint + 类型检查）
```

测试命令：

```bash
bin/evo test               # 运行端到端测试套件（tests/e2e）
bin/evo test cov           # 测试 + 覆盖率报告
bin/evo test e2e           # 同 bin/evo test
pytest tests/e2e -v        # 直接用 pytest 运行 E2E 测试
pytest tests/e2e/test_02_routing.py -v  # 仅测试 L0 路由模块
```

## 代码风格与命名约定

- **Python 版本**：3.12+（`pyproject.toml` 中限制 `>=3.12,<3.13`；OpenHands SDK requires 3.12）
- **格式化与 Lint**：使用 Ruff（`ruff check` + `ruff format`），目标版本 `py311`
- **类型检查**：渐进式引入 mypy/pyright 强类型检查（优先覆盖 Pydantic 模型与核心 Service）
- **命名规范**：
  - 模块/文件名：`snake_case`（如 `context_trimmer.py`）
  - 类名：`PascalCase`（如 `AgentEngine`、`EvoMessageConverter`）
  - 常量：`UPPER_SNAKE_CASE`
  - 类的私有化：**不要加 `_` 前缀**。类私有成员与方法一律按公开方式命名（不加下划线），如 `TransportContext` 而非 `_TransportContext`。
- **导入规范**：统一使用顶层导入（Top-level imports）。**严禁**在函数体内使用 `from app.xxx import yyy` 掩盖模块间的循环依赖；如遇循环依赖应重构模块层次或使用 `typing.TYPE_CHECKING`。仅限第三方重型 C 扩展（如 `llama_cpp`）允许懒加载。
- **禁止事项**：
  - **禁止静默吞掉异常**：严禁使用 `except Exception: pass` 或静默返回假数据/`None`。严禁使用 `logger.error(f"{e}")` 丢弃 Traceback 堆栈，必须使用 `logger.exception(...)` 或 `exc_info=True`。
  - **禁止 6 元组伪捕获**：严禁复制粘贴 `except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError)` 通配绝大多数异常。代码 Bug（如 `TypeError` / `AttributeError` / `KeyError`）必须遵循 **Fail-Fast** 原则直接暴露。
  - **禁止滥用动态反射**：已有明确 Pydantic Model / Dataclass / Domain 实体时，严禁使用 `getattr` / `hasattr` / `setattr`。模型访问统一采用点语法 (`obj.attr`)。
  - **禁止 async 函数中的同步阻塞**：`async def` 中严禁直接调用同步 `open()`、`subprocess.run()` 或同步 `requests`。必须使用 `asyncio.to_thread()` 或 `aiofiles` / 异步子进程。
  - **禁止无锁修改全局状态**：严禁使用 `global` 关键字在并发请求路径中修改全局可变状态，避免 Race Condition。
  - **禁止无意义的对象与 Dict 频繁倒腾**：核心业务、Service 层与函数调用之间，必须全程保持强类型对象（Pydantic Model / Dataclass / ORM 实体）透传。**严禁**把对象 `model_dump()` 转成 `dict` 传给下一级、下一级再 `model_validate()` 转回对象的冗余倒腾。**严禁**先手动组装 `{"a": x}` 字典再调用 `Model.model_validate(...)` 实例化，必须直接使用类构造器 `Model(a=x)` 或 `model.model_copy(update={...})`。仅在 FastAPI Response 返回、数据库 JSON 存储或外部 API 请求边界才允许进行序列化。
  - **禁止重型/无状态服务在函数内重复实例化**：严禁在函数/方法体内随手 `service = ServiceClass()` 重复创建无状态或重型服务实例。无状态服务、工具管理器与共享组件必须统一定义为 **模块级单例（Module Singleton）**（如 `message_publisher = MessagePublisher()`）或通过 **FastAPI `Depends()` 依赖注入** 传递，避免频繁 GC 损耗与连接池/缓存失效。
  - **禁止 print 语句**：不允许 `print` 语句（Ruff T201 规则），测试和脚本目录除外。
- **模板文件**：提示词模板使用 Jinja2，存放于 `app/config/templates/core/`，按功能分目录（`memory/`、`learning/`、`engine/` 等）

## 测试指南

- **框架**：pytest + pytest-asyncio（`asyncio_mode = auto`）
- **测试命名**：文件 `test_*.py`，类 `Test*`，函数 `test_*`
- **测试标记**（`@pytest.mark`）：`e2e`、`real`、`slow`、`llm`、`db`、`performance`
- **E2E 运行前提**：必须先启动后端服务，否则整组测试会被自动 skip
- **超时**：默认 60 秒（`pytest-timeout`），E2E 真实链路可在具体用例中覆盖到 180 秒
- **覆盖率**：`pytest-cov`，报告生成至 `htmlcov/index.html`
- **注意**：E2E 测试依赖共享的后端服务实例，不建议使用 `-n auto` 并行执行

## 提交与合并规范

- 提交消息使用中文，格式为简短描述性语句（如"新增多轮对话测试脚本"、"优化聊天界面性能"）
- 重要变更建议加前缀：`新增`、`修复`、`优化`、`重构`、`暂存`
- PR 需包含变更说明，关联相关 issue

## 实施前强制关卡（Pre-Implementation Gates，2026-09 复盘后新增）

> 来源：2026-09-12/13 自主任务循环实施期间的系列返工（OpsTask 重复建表、HTTP 平行通道、商城模板进引擎、凭过时 docstring 断言调度机制）。方案纠正多轮后实现仍跑偏的根因是：修正停留在文档层未回灌实现核查、依赖外部审查而未自查先例。以下四条为**硬约束**，任何新组件动手前逐条执行，任一未过即停。

### 关卡一：资产盘点前置（先例扫描）

新组件动手前，先扫描既有同语义/同层次实现，产出**先例对照表**再写码：

- 全新工具 → 必须先看 facade 先例（`app/domain/planning/facade_tool.py` 的 plan、`app/domain/todo/`）——单一入口、action 分发、`@evoloop_tool` 注册、进 `agent_main.yaml` 工具面才可达。
- 外部输入 → 必须先看 `app/core/channel/` 三类入口形态（InputChannel 归一化 / DutyChannel 轮巡 / MCP 通知订阅 `MPC_SERVER_NOTIFICATION`），任何"外部进数据"的需求必须归入其一，**禁止新建平行传输或平行鉴权**。注意：MCP 通知的任务入队订阅者已收敛到 `app/domain/tasks/event/subscribers.py::InboundMessageSubscriber`（旧 `notification_subscriber.py` 已删除，2026-09 审计时的"未接通骨架"已由该订阅者正式承接）。
- 定时/调度 → 以 `app/main.py` lifespan 循环 + `app/infrastructure/scheduler/service.py` 的实际代码为准（**docstring/注释不作为事实来源**，历史上已有过时注释误导先例）。
- 持久化 → 先查 `app/models/` 既有表与 `alembic/versions` head，确认不是重复建表；多 head 时明确选线并注释。

### 关卡二：分层红线四问（引擎侧改动逐条过）

任一命中即停，先对照 `AGENTS.md`「域驱动能力装配」与项目侧 `.evoloop/` 归属：

1. 业务词汇/业务事件/业务话术进引擎代码了吗？（归属项目侧——能力包、`.evoloop/` 资产、推送方 payload）
2. 新建了传输通道、鉴权机制、状态存储吗？（先归入既有三类入口 + 既有凭证体系）
3. 与既有机制平行吗？（新 facade vs 旧工具、新通道 vs MCP/InputChannel、新调度 vs tick）
4. 运行时才能做的决策被固化成 schema 字段/类型了吗？（如"当场干还是建提案"属运行时风险门控，不设类型）

### 关卡三：方案 = 假设，代码 = 事实

- 方案文档中的实现性断言，只有标注**本人验证过的 `文件:行号`** 才可作为实现依据；docstring/注释一律不算。`docs/autonomous-task-loop.md` 曾遗失、已于 2026-09-21 恢复并按代码事实校订（派发架构/状态机/调度护栏以代码 + `tests/unit/domain/tasks/` 为准，见下文「自主值守（任务队列）关键事实」）。
- 实现时发现方案与代码事实冲突：**改方案，不硬实现**，并在方案中记录冲突点。
- 每轮方案修正后，回查其推翻的实现假设清单（数据模型/通道/工具面/提示词），同步修订，不带病进入下一阶段。

### 关卡四：执行纪律

- **架构级修改只在验证工具链干净时做**（ruff/pytest 全绿、显示/会话状态正常）；低质量状态下只做机械修补，不做设计决策。
- 写文件一律 `write` 工具 + 机器断言（`ast.parse` + 关键片段 in 检查）；**禁止长 heredoc 内联脚本做内容生成**（历史事故：反复写坏迁移/测试/文档）。
- 校验只信机器输出（pytest 结论、introspection、字节级断言），**终端回显不作为正确性证据**。
- 每完成一个组件，自查一遍"外部审查者会抓什么"（分层/先例/命名/验收状态），通过才算完成。

## Agent 开发注意事项

- **引擎架构**：单 Agent ReAct 主循环（对齐 OpenCode）。`app/core/engine/react/loop.py` 的 `run_agent_loop` 是唯一执行体——一条连续消息流，主 Agent 拥有全量工具，直到无 tool_calls 的文本回复结束；无 supervisor/worker/finish 图节点、无 signals、无 ExecutionTicket、无消息过滤。主 Agent 基础工具面见 `app/core/engine/config/agent_main.yaml` 的 `agents.react.tools`（默认 20 个）；**该面会被域驱动能力装配按会话域覆盖/裁剪**（见下方「域驱动能力装配」）。
- **状态管理**：通过 `app/core/engine/state/` 管理生命周期与工作区状态（`AgentState` 精简版，移除图架构字段）。
- **提示词模板**：主 Agent 人格用 `app/config/templates/core/agent/*.txt` 纯文本（非 Jinja2），动态块（环境/记忆/`<available_skills>`/`<available_macros>`/`<available_agents>`）由 `app/core/engine/react/prompts.py` 代码层拼接；其余内部合成 prompt 仍用 `.j2`（二期迁移）。
- **域驱动能力装配与能力包（Capability Profiles + Packages，v2）**：Agent 的提示词/原生工具/MCP 按**域预选 + 能力包分发**渐进式装配。机制：`capability_profiles.py`（域注册表与预选）+ `react/skills/`（包=SKILL.md 扩展格式）+ `tools/manager.py`（包可见性过滤）。规则：
  - **三权分立**：域（host_declared > classified > ambiguous）只决定**包目录**（哪些包进索引）；**页面**（host_context.route/package）决定**预挂**（单包工具直接可用）；**Agent 持有最终裁量**（按索引自主加载其他包）。
  - **包 = 分发单元**：SKILL.md frontmatter 扩展 `capability` 键——`domain` / `tools`（`[{mcp_server, include?}]` 跨 server 归属）/ `preload` / `confirm_tools`（写操作清单，G4）/ `route_patterns`（引擎兜底匹配）。无 `capability` 键 = 普通技能零改动。
  - **业务内容归项目侧，引擎保持通用**：引擎级 `capability_profiles.yaml` **不得声明业务域**（测试 `test_engine_yaml_remains_domain_agnostic` 锁定）；业务域 profile + 能力包放项目侧 `.evoloop/capability_profiles.yaml` 与 `.evoloop/skills/<name>/SKILL.md`。
  - **新域接入三步**（引擎零改动）：①项目侧 profile 声明 `packages` 列表；②`.evoloop/skills/` 放包（frontmatter `capability` + SOP 正文）；③宿主 host_context 带 `domain`+`package` 双字段（matrix-context.js DOMAIN_MAP/PACKAGE_MAP）。
  - **可见性模型**：MCP 工具面 = 预选集（每轮由 domain+page 重算，`preselected_packages`）∪ 加载集（Agent 经 `skill` 加载，thread 级持久 `loaded_packages`）。**G4**：预挂包按 `confirm_tools` 排除写工具（SOP 未读须显式加载包后放开）。`include` 缺省 = server 全量。无任何包 = 全量兜底（零回归）。
  - **server 侧不做分域**：MCP_PROFILE 已退役（C1）——server 全量加载（97 工具），可见性由包层承担；`elements/core|ext` 目录保留（代码复用边界）。
  - **历史字段**：`mcp_allowlist` 已删除（C3）。**工具声明只有一种写法（v3.1 统一）**：`capability.tools`（唯一装配权威）——`requires.{tools,mcp}` 已**废弃**（纯文档性、从未有运行时作用；导入器自动合并进 capability 并打 deprecation warning；存量 SKILL.md 已批量迁移）。普通技能不写任何工具声明（native 面由 profile 管）。
  - **观测**：`[ToolManager] domain=... assembled surface` 日志、`[CapabilityProfiles] domain resolution: hint=... -> feedback=...` 候选裁决链日志、`[SkillTool] session domain feedback` 反哺日志、`[ProjectSkills] synced N skill(s)`、`[CapabilityProfiles] preload`。L1 分类器标签集（域词汇表）与项目域命名是两套词汇表，排障入口见 `docs/capability-packages-refactor.md`「域词汇表」小节（契约测试 `test_domain_labels_doc_synced` 锁定文档与模型产物同步）。
  - 契约测试：`test_capability_packages.py`（格式/可见性/零回归）、`test_preselection.py`（预选/合成/G4）、`test_project_skill_importer.py`（发现幂等）。方案全文：`docs/capability-packages-refactor.md`。
- **工具面**：`@evoloop_tool` 注册（26 个，2026-09 工具面收敛完毕——Atlas/Skill CRUD/Macro CRUD/UI 辅助/MCP Server/MCP 客户端运行时管理/macro 独立工具等 54 个已删除，见 `docs/dead-code-report-2026-09.md` §六/§七），react 主 Agent 声明面 18 个（`agent_main.yaml`：核心 12 bash/read/glob/grep/edit/write/task/webfetch/websearch/plan/tasks/skill/question + image/video + vault/macro + remember；browser/mobile/desktop 已于 2026-09-22 移出声明面——CDP 操控型工具直面平台风控，替代路径为 Agent Reach 技能，如需恢复取消注释即可），运行时注册 26 = 声明面 18 + browser/mobile/desktop/ask_confirm/cancel_command/sql_query（vision/benefit 运行时过滤）。声明面缺工具按门控处理（`remember` 随 `ENABLE_MEMORY=False` 整组不注册，见 `registry.py` 注释）；源码声明 35 vs 运行时 26 的差额全部为显式门控组（ENABLE_WIKI_TOOLS / ENABLE_MEMORY），见 `wiki_tools.py` 尾部门控块（knowledge 概念工具 save_concepts/query_concepts 已于 2026-09-26 连同 harvest_concepts_task/record_episode_task 死任务壳整体删除——记忆基建 store_concept/record_episode 与 /memory/concepts API 保留，completion 管线等其他消费者不受影响）。低频/垂直能力走 `skill`/`macro`/`task` 索引+按需加载。**重工具渐进披露**：desktop/browser/mobile/macro 的长 SOP 不进 description（实测四者原占工具面 55%），分别由「Desktop/Browser Automation SOP、Mobile Device SOP、Macro Authoring Guide」引擎技能承载（`app/config/skills/`，tool description 内含指向），契约测试 `test_embodied_progressive_disclosure` 锁定。
- **子代理与 A2A**：统一收敛到 `task` 工具——`action='run'`（本地 spawn / `remote={'agent_id': ...}` A2A 委派）、`action='complete'`（A2A Worker 回传）、`action='list_agents'`；A2A 派发后主循环挂起，回调经 `a2a_callback` 写回工具消息后恢复。
- **MCP server 故障隔离（强制约定）**：每个 MCP server 的 transport 生命周期在**独立长驻 runner 任务**里（`manager.py::_server_runner`，anyio scope 自包含），单 server 故障（502/超时/失联）只降级为 `ConnectionResult(success=False)`，**严禁向上传播**到 connect_all/safe_handle/lifespan——`except Exception` 接不住 anyio 混入 CancelledError 成分时的 **BaseExceptionGroup**（BaseException 子类）。`connect_from_db` 不按 enabled 过滤（enabled=0 = 不随启动常驻，显式按名连接是按需拉起）。新增 server 连接路径时必跑 `tests/unit/core/mcp/` + 人工验证「坏 server 下服务可启动」。
- **防循环**：代码层 doom_loop 检测（`inference_engine.doom_loop_detected`，连续 3 次相同工具签名 → `DoomLoopException` → 问用户"停止/继续"：HITL 挂起等人，docker 模式豁免为确定性收尾，见「自主值守（任务队列）关键事实」）；已移除 prompt 反循环协议（verification_blocked/unverifiable/report_outcome）。
- **上下文管理**：`ContextTrimmer` + executor 统一截断（`react/truncate.py` 超限输出折叠+落盘），节点级 filter 已删除。
- **收尾管线**：`engine/react/completion.py` 在 run 结束时发布 SESSION_COMPLETED，并触发 episodic 记忆、宏资格判定、skill 候选生成（代码层，非 prompt 规则）。运行终态事件全貌（AgentRunCompletedEvent 全终态发布、HITL 挂起是唯一例外）见下文「自主值守（任务队列）关键事实」。
- **数据库迁移**：模型变更后用 `alembic revision --autogenerate -m "描述"` 生成迁移

## 自主值守（任务队列）关键事实（2026-09-13 全量代码审计后固化；2026-09-23 全局收敛增补见下节）

两套"值守"语义不同，禁止混用：**客服值守** = `app/core/channel/duty/`（企微/微信客服轮巡，启停入口 `PUT /projects/{id}/duty` → `provision.py`）；**自主值守** = `app/domain/tasks/` 任务队列（ProjectTask SSOT）：状态机 `service.py`、外部事件摄取 `TaskQueueService.ingest_event`（event/ 只放订阅者，全仓范式）、常量 `constants.py`、跨边界模型 `schemas.py`、Agent 工具面 `tools/`（薄封装，业务在 service）、派发编排 `runtime/dispatcher.py`、死亡收敛 `runtime/reconciler.py`、唤醒信号 `runtime/wakeup.py`、主循环宿主 `runtime/supervisor.py`（连续运行时收进 runtime/ 子包）。**分层红线：infrastructure 是底层，严禁 import app.domain（业务在上、基础设施在下，domain → infrastructure 才是合法方向）**——值守的全部业务逻辑住 domain，main.py lifespan 只负责拉起 `domain/tasks/runtime/supervisor.py::run_supervisor_forever`。

### 阶段九（2026-09-25 轮次化周期工作流；细节以 docs/autonomous-task-loop.md 阶段九为准）

- **触发/编排/执行三分离**：`task_workflows` 承载阶段模板（`inputs.stage_template`）与触发器（`trigger_spec`/`next_run_at`/`round_no`）；supervisor 每拍 `spawn_due_rounds` 实例化轮次（`workflow_round` 一等列 + `dedup_key="wf:{id}:{round}:{stage}"` 幂等 + skip-on-busy 轮次绝不并发）；阶段任务=普通 pending 任务走标准 duty 派发。
- **红线**：recurring 与任务图（parent_id/dependencies）互斥——周期流水线唯一正确形态是工作流提案（`tasks create_workflow` action / `POST /tasks/workflows` API）；`create_workflow` 模板强校验（Kahn 环检测 + 拓扑序 + 触发器严格校验，非法 cron 拒绝而非静默兜底）。
- **依赖门控单一实现**：`TaskQueueService.evaluate_dependency_gate`（recurring lineage-only 豁免 / 依赖缺失不放行），claim 扫描与 dispatcher 派发闸共用；dispatcher 只做断链告警副作用。
- **growth 流水线走通用轮次机制**：roles.py 仅作模板数据源；`EvoloopAgentRuntimeAdapter`/`build_task_prompt`/`complete_task`/`requeue_workflow_task`/dispatcher 特权分支已全部退役，阶段任务由 advance 内嵌 `refresh_status` 聚合，无任何 task_data 驱动的执行路径分叉。

### 2026-09-23 全局收敛后的新不变量（细节以 docs/autonomous-task-loop.md 阶段八为准）

- **一等列，不再读 task_data**：title/priority/category/tags/dependencies/acceptance_criteria/workflow_id/dispatch_count/last_result/last_error/review_pending/workflow_retry_count/version 全部是 `project_tasks` 列；读用 `service.py` 顶部 `task_title()/task_priority()/…` 兼容函数（列优先、存量 JSON 兜底）。新代码**禁止**往 `task_data` 写这些键。
- **version 乐观锁**：take/claim/advance/acceptance/requeue/edit 全部 `WHERE version=?` + 递增；`advance_task(thread_id=…)` 校验执行权归属。
- **fail-closed 三则**：external → proposed；缺 risk 的 one-shot self_check → waiting_acceptance（不默认 T3）；accept 必须有 result。recurring 轮次完成优先回队（不走验收）。
- **单一 SSOT**：`/api/v1/tasks/*` 只有队列面；EvoCloud 代理在 `/api/v1/evocloud/tasks/*`；subtasks API/subtask_service/旧任务工具岛已删除（`REGISTRY.scan("app.core.project.tools")` 已摘）。
- **task_runs 过程记录层**（`models/task_run.py`）：claim 开行、终态收行，只做审计观测，不参与状态机判定；`list_task_runs` 供队列 API 内联。
- **reconciler 覆盖 `wakeup_` + `agent_`**（workflow 崩溃恢复）；HITL 24h 过期在 `reconcile_stranded` 开头接线（先过期再算豁免）。
- 评审派发失败**保持 waiting_acceptance**（绝不 fallback auto-accept），30min 超时兜底。

### 运行终态与事件（做连续运行 / 看门狗 / reconcile 设计的唯一事实源）

- `AgentRunCompletedEvent` 由 `app/core/monitoring/activity.py` 的 `run_scope.__aexit__` / `end_run` 在**全部终态**发布（DONE / CANCELLED / FAILED / QUOTA_EXHAUSTED，终态去重保证恰好一次）。`max_steps` 耗尽 = `TRUNCATED` 正常返回（`engine.py`），**是安全终态不是断链**。
- **HITL 挂起是唯一不发布终态的出口**：`AgentHumanInterruptException` 在 `agent/runner.py` 被外层吞掉正常 return，`run_scope` 不 end_run 不发事件 → `AgentActivity` 悬挂 running。挂起后调用方的 await 正常返回，**值守循环不会被挂起卡死**，但状态记账三层（活动 / 任务 / 看板）均不可见——这是设计挂起相关功能时的核心缺口，不是"挂起=失败"。
- `stop_agent`（`session/manager.py`）对 `run_agent_background` 直跑的 run（如值守 wakeup）**只剩协作式标志**——这类 run 不在 `session_manager._sessions` 也不在 `agent_run_registry`；硬取消必须持有 asyncio.Task 句柄（CancelledError 会被 run_scope 接住 → end_run(CANCELLED) → 事件照发）。
- `dispatch_agent_run` 多租户 fail-closed：member_id 必需且从 Conversation 回填——全新 thread（无 Conversation，如 `wakeup_*`）回填失败会 raise，值守派发必须显式携带 `ProjectTask.member_id`。

### HITL / 权限边界

- `hitl_enabled()`（`hitl/core.py`，非 docker 即启用）是单一出处；docker 豁免三处生效：`ask_human` 自动应答、`authorization_gate` 自动批准（`hooks/authorization.py`，matcher=".*" **覆盖全部工具含 MCP**）、`raise_hitl_interrupt` 抑制中断（doom guard 落入确定性收尾）。
- **docker auto-approve 对 MCP 业务写没有沙箱兜底**（调用出进程直达真实业务系统）——"跑 docker mode 解决权限"仅对 bash/文件成立；MCP 业务动作的决策边界在任务级（risk_level T1-T4 + waiting_acceptance/提案确认），不在工具门控。
- **信任纪律（连续运行的前提）**：连续运行靠信任支撑——Agent 在完全清楚时一撸到底；历经多轮努力仍摸不清、或 T1/T2 有疑虑时**必须问人**，严禁静默乱猜乱决策。挂起等人是合法决策机制而非故障；值守设计的目标是**挂起便宜（单任务现场暂停、值守循环不停摆）、应答快速（看板/推送触达）、纪律可审计（问人频率是值守健康度指标）**。禁止用结构约束（禁用 ask_human、强制自动应答）替代这一运行时判断（与关卡二第 4 问同理）。

### 断裂修复记录（2026-09-13 修复，语义以代码为准）

原五处断裂已全部修复，改动即当前事实：

1. **rejected 回队**：`submit_acceptance` rejected → `pending`（原 in_progress 死局）；feedback 经 `tasks list`（`feedback` 字段）与 wakeup payload（`task.feedback`）回流 Agent；`task_data.requeue_count` 随失败回队累计。
2. **值守开关接管队列**：`claim_due_tasks` 跳过 `customer_service_duty.enabled=false` 的项目（无配置/云端项目不阻断，向后兼容）；`provision.stop_project` 同时切断 `wakeup_{project}_%` 线程（原只匹配 `duty_` 前缀）。
3. **事件入口接线**：`domain/tasks/__init__.py` 导入 `event`（注册 `event/subscribers.py` 的 InboundMessageSubscriber）——MCP `task_event` 通知现可入队（旧 `notification_subscriber.py` 已删除）。
4. **watchdog/reconcile**：`domain/tasks/runtime/reconciler.py::reconcile_stranded`——启动时遗留 running 一律判死；稳态超期（35min）且无 pending HumanRequest 判死；终态线程上的悬置任务回队（requeue_count 上限 3 转failed，防毒任务）。`dispatcher.py` 对单 run 加 30min 硬截止（`asyncio.wait_for` 硬取消 → CANCELLED 终态事件照发）。任务归属解析 `TaskQueueService.resolve_member_id`（task.member_id → repositories 回填）。
5. **单 drainer**：任务队列派发只发生在 supervisor（tick 已摘除），API/worker 双 tick 的跨进程双派发窗口关闭。
6. **派发即认领（one-shot claim-then-persist，2026-09-21）**：`dispatch_due_tasks` 派发前系统侧原子认领（pending→in_progress + last_thread_id + `task_data.dispatch_count` 递增），`DispatchStatus.FAILED` / 派发异常回滚 pending——与 recurring「认领即推进 next_run_at」的 claim-then-persist 语义对齐。**收敛不变式：每次 run 结束后任务必须已被系统认领（in_progress+绑线程）或已达终态，严禁出现「run 完成但任务仍 pending 且无认领占位」**——该态会经 DutyWakeupSubscriber（AgentRunCompletedEvent 必发）立即重派发形成热循环（2026-09-21 实测：探针任务未调 tasks 工具 → ≥12 次重复派发烧 LLM）。护栏分工：`take` 幂等（同线程重复 take 视为已绑定）；认领后 run 未推进的任务由 reconcile「线程终态+in_progress」回队网收敛（`REQUEUE_LIMIT=3`）；`dispatch_count ≥ 5`（`DISPATCH_CLAIM_CIRCUIT_LIMIT`）熔断强制 failed，覆盖派发失败回滚等不经 reconcile 的重试环——**计数在 `advance_task` 成功推进时清零**（否则 recurring 跨轮累计会把健康周期任务第 5 个 cron 误杀，2026-09-22 实测售后 5 轮真实巡检全成功仍被熔断）；recurring 自检回队（self_checked→pending）是本轮正确终态，`tasks` 工具返回已带显式 note 防 agent 误读（实测曾 33 次 illegal transition）。
7. **recurring 的 next_run_at 门控修复（2026-09-21 实测）**：`claim_due_tasks` 原扫描条件 `due_at IS NULL` 分支对 recurring 任务恒命中（recurring 行 due_at 恒 NULL）——next_run_at 门控形同虚设，明日首跑的每日巡检被判"到期"，开闸后爆发式连跑。修复：one-shot（无 trigger_spec）走 due_at 门控，recurring 只认 `next_run_at <= now`；存量测试 `test_recurring_requeues_on_self_check` 依赖 bug 行为的"完成后立即再认领"断言已修正为正确契约（轮次间隔由 trigger 门控）。
8. **stopping 僵尸判死（2026-09-21 实测）**：协作取消请求后进程死亡（急停/重启），activity 永久停在 `stopping`——既非 `running`（判死查询不匹配）也非终态（回队 `_SKIP_STATUSES` 显式跳过"停止中"），任务永久悬挂 in_progress（实测 4 条卡死，人工代运维判死后回队）。`reconciler.py` 判死查询扩为 `RUNNING+STOPPING`，陈旧 stopping 与陈旧 running 同权判死；`end_run(FAILED)` 后走标准回队语义。

Supervisor 主循环（`domain/tasks/runtime/supervisor.py::run_supervisor_forever`，main.py lifespan 启动）：`reconcile(startup) → dispatch_due_tasks → wait(duty_wakeup, 60s)`。事件源：AgentRunCompletedEvent（仅 `wakeup_` 前缀线程，`DutyWakeupSubscriber`）+ 队列变更（create/advance 回队/acceptance rejected 直接 `notify_duty_wakeup`）。HITL 挂起现以 `human_interrupt` 终态落库并发布事件；dashboard 新增 `awaiting_human` 聚合（前端消费待接）。

## API 响应规范（新代码必须遵循）

- **统一信封**（见 `docs/api-response-envelope.md`）：
  - 成功单对象 → `DataResponse`（`{success, message, data}`）
  - 成功列表/分页 → `ListResponse`（`{success, message, data, total, page, page_size}`）
  - 错误 → 全局 handler（`app/api/errors.py`）自动生成 `{success, code, message, detail}`，路由层直接 `raise HTTPException`，**禁止手动返回错误 JSON**
  - **禁止新增自定义 `XxxResponse` 信封模型**，统一从 `app/api/schemas/responses.py` 导入
- **保留场景**（不改，契约特殊）：SSE/流式、文件下载/上传、Webhook、云透传代理（`{code, data}`，tasks/subscription/member）
- 存量 ~233 端点按文档指引**渐进式**迁移，不做一次性全量改造

## 安全与工具输出约定

### 错误呈现单出口（ErrorEmitter）——强制约定

用户可见的错误呈现**只有一个出口**：`app/core/engine/error_emitter.py` 的 `error_emitter.emit(thread_id, error)`。任何层（session 主循环、runner、通道处理）捕获到需告知用户的异常，一律调用它，**禁止**自行实现「分类→事件→SSE」。

- 契约（`tests/unit/core/engine/test_error_emitter.py` 锁定，改呈现链路前必跑）：
  - `quota_exhausted`（含订阅过期）→ `QuotaExhaustedEvent`（前端续费横幅）
  - `llm_auth` → `LLMAuthErrorEvent`（toast + 设置跳转）
  - `auth_expired` → `AuthExpiredEvent`
  - 其余（限流/超时/网络/未知）→ system 错误消息块（`channels={"sse"}`，仅 Web）
- 分类器全表锁（`tests/unit/core/engine/test_error_classifier.py`）：每个 error_type 的关键词文本 → 类型/终态性映射，分类关键词改动先跑它
- 新增错误类型两步：`error_handler.py` 分类器加关键词 + 契约测试加参数——呈现链路自动继承，**不要**新建出口
- `InferenceError` 自带分类（LLM 调用边界产生），emit 直接复用不二次分类
- runner 通道（`agent/errors.py::handle_task_exception`）的活动状态收尾（end_run）、Mobile push、富格式落库块保留在调用侧，事件发布已收敛至 emit
- 前端对齐：`agentStore._handleServerError` 是错误事件统一分发中枢（与后端契约一一对应），ChatConnection 回调只接线不实现呈现

### 关键安全修复
`app/core/engine/hooks/security.py` 的 `sensitive_file_censorship_gate` 原仅在同一个 `HookContext.extra` 中读取 `injected_secrets`，跨 tool call 后 `extra` 被重置，导致占位符替换后的真实密钥在后续输出中**未被脱敏**。已增加从 `EvoContext.injected_secrets` 回退读取，确保同一次运行中所有工具输出都被打码。

### 工具输出信息确认
`tool_output` 类型的 Message 中：
- `content` 字段仅存储摘要（如 `✅ Command Succeeded.` / `❌ Command Failed (Exit Code N).`），**不含**完整 STDOUT/STDERR
- 完整命令输出存储在 `meta_data` 字段（JSON 格式）
- AI 消息的 `tool_calls` 字段存储工具调用结构体（含命令文本）

因此验证命令是否执行时，**不能**仅依赖 `tool_output.content`（摘要中不含 `devops.sh`/`build` 等关键词）。应同时检查 `meta_data` 和 `tool_calls`。

## 历史手动测试清理说明

历史 `tests/manual`、`scripts` 等目录已清理，相关 DevOps 手动回归脚本不再维护。

当前测试布局：
- `tests/e2e`：真实后端链路的端到端验证入口；
- `tests/unit`：核心模块的单元测试（如宏引擎 `tests/unit/core/macro/`、`tests/unit/core/engine/tools/`）；
- `tests/integration`：宏工具集成测试（如 `tests/integration/test_macro_agent_tools.py`）。

新增/修改单元或集成测试时，优先按现有目录结构放置，并遵循 `pytest` 命名与标记规范。

不用检查与配置 LLM_MODEL，因为只要用户是登录过后有 token 的请求 EvoCloud Gateway 的话，Gateway 在不传 LLM_MODEL 的情况，会分配默认模型去请求 LLM 的

## 前端
### 宿主上下文桥（main.tsx initHostContextBridge）部署契约
- **生产必须配置 `VITE_HOST_ORIGINS`**（构建时注入，逗号分隔宿主 origin 列表，如 `https://host.example.com`）——漏配时 iframe 内嵌场景会 `console.error` 提示，宿主上下文桥不启动，内嵌搭子的域判定/渐进披露静默降级。
- 配置来源：根目录 `.env`（vite envDir 指向 evoloop/ 根，单文件 SSOT）的 `VITE_HOST_ORIGINS`——开发默认 `localhost:9003/127.0.0.1 + 5173`；**代码零硬编码**。改白名单只改 `.env`（+`.env.local`），模板同步 `.env.example`。
- 消息安全：`matrix_context` 只接受白名单 origin 的 postMessage（防任意网页伪造宿主上下文诱导 Agent 操作错误实体）。
