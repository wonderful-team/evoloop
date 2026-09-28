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

- 全新工具 → 必须先看 facade 先例（`app/core/planning/facade_tool.py` 的 plan、`app/domain/tasks/tools/tasks_tool.py` 的 tasks）——单一入口、action 分发、`@evoloop_tool` 注册、进 `agent_main.yaml` 工具面才可达。
- 外部输入 → 必须先看 `app/core/channel/` 三类入口形态（InputChannel 归一化 / DutyChannel 轮巡 / MCP 通知订阅 `MPC_SERVER_NOTIFICATION`），任何"外部进数据"的需求必须归入其一，**禁止新建平行传输或平行鉴权**（现行订阅者以 `app/domain/tasks/event/subscribers.py` 实际代码为准）。
- 定时/调度 → 以 `app/main.py` lifespan 循环 + `app/infrastructure/scheduler/service.py` 的实际代码为准（**docstring/注释不作为事实来源**，历史上已有过时注释误导先例）。
- 持久化 → 先查 `app/models/` 既有表与 `alembic/versions` head，确认不是重复建表；多 head 时明确选线并注释。

### 关卡二：分层红线四问（引擎侧改动逐条过）

任一命中即停，先对照 `AGENTS.md`「域驱动能力装配」与项目侧 `.evoloop/` 归属：

1. 业务词汇/业务事件/业务话术进引擎代码了吗？（归属项目侧——能力包、`.evoloop/` 资产、推送方 payload）
2. 新建了传输通道、鉴权机制、状态存储吗？（先归入既有三类入口 + 既有凭证体系）
3. 与既有机制平行吗？（新 facade vs 旧工具、新通道 vs MCP/InputChannel、新调度 vs tick）
4. 运行时才能做的决策被固化成 schema 字段/类型了吗？（如"当场干还是建提案"属运行时风险门控，不设类型）

### 关卡三：方案 = 假设，代码 = 事实

- 方案文档中的实现性断言，只有标注**本人验证过的 `文件:行号`** 才可作为实现依据；docstring/注释一律不算。方案文档约定归档于 `docs/root/autonomous-task-loop.md`（**缺失时以代码 + `tests/unit/domain/tasks/` 为准**，见下文「自主值守（任务队列）开发约束」）。
- 实现时发现方案与代码事实冲突：**改方案，不硬实现**，并在方案中记录冲突点。
- 每轮方案修正后，回查其推翻的实现假设清单（数据模型/通道/工具面/提示词），同步修订，不带病进入下一阶段。

### 关卡四：执行纪律

- **架构级修改只在验证工具链干净时做**（ruff/pytest 全绿、显示/会话状态正常）；低质量状态下只做机械修补，不做设计决策。
- 写文件一律 `write` 工具 + 机器断言（`ast.parse` + 关键片段 in 检查）；**禁止长 heredoc 内联脚本做内容生成**（历史事故：反复写坏迁移/测试/文档）。
- 校验只信机器输出（pytest 结论、introspection、字节级断言），**终端回显不作为正确性证据**。
- 每完成一个组件，自查一遍"外部审查者会抓什么"（分层/先例/命名/验收状态），通过才算完成。

## Agent 开发注意事项

- **引擎架构**：单 Agent ReAct 主循环（对齐 OpenCode）。`app/core/engine/react/loop.py` 的 `run_agent_loop` 是唯一执行体——一条连续消息流，主 Agent 拥有全量工具，直到无 tool_calls 的文本回复结束；无 supervisor/worker/finish 图节点、无 signals、无 ExecutionTicket、无消息过滤。主 Agent 基础工具面见 `app/core/engine/config/agent_main.yaml` 的 `agents.react.tools`（声明面 15 个，默认注册 14——remember 随 ENABLE_MEMORY=False 不注册）；**该面会被域驱动能力装配按会话域覆盖/裁剪**（见下方「域驱动能力装配」）。
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
   - **观测**：`[ToolManager] domain=... assembled surface` 日志、`[CapabilityProfiles] domain resolution: hint=... -> feedback=...` 候选裁决链日志、`[SkillTool] session domain feedback` 反哺日志、`[ProjectSkills] synced N skill(s)`、`[CapabilityProfiles] preload`。L1 分类器标签集（域词汇表）与项目域命名是两套词汇表，排障入口见 `docs/capability-packages-refactor.md`「域词汇表」小节（**缺失时以契约测试 `test_domain_labels_doc_synced` 与模型产物为准**）。
   - 契约测试：`test_capability_packages.py`（格式/可见性/零回归）、`test_preselection.py`（预选/合成/G4）、`test_project_skill_importer.py`（发现幂等）。方案文档约定归档于 `docs/capability-packages-refactor.md`（**缺失时以契约测试为准**）。
 - **工具面**：`@evoloop_tool` 注册，注册事实源 = `app/core/tools/registry.py::_ensure_scanned` 的显式扫描根清单；react 主 Agent 声明面见 `agent_main.yaml`（bash/file/glob/grep/agent/webfetch/websearch/plan/tasks/skill/question/media/vault/macro/remember）。规范：
   - 新能力一律 facade 收敛（单一入口 + action 分发，先例见关卡一），**禁止平行新工具**；低频/垂直能力走 `skill`/`macro`/`agent` 索引 + 按需加载。
   - 声明面缺工具按门控/禁用处理（`remember` 随 `ENABLE_MEMORY=False` 整组不注册，见 `registry.py` 注释），不算悬空引用。
   - browser/mobile/desktop 为 CDP 操控型，不在声明面（替代路径 Agent Reach 技能；确需恢复取消注释即可）。
   - **重工具渐进披露**：desktop/browser/mobile/macro 的长 SOP 不进 description，由引擎技能承载（`app/config/skills/`，tool description 内含指向），契约测试 `test_embodied_progressive_disclosure` 锁定。
 - **子代理与 A2A**：统一收敛到 `agent` 工具（2026-09 由 `task` 改名）——`action='run'`（本地 spawn / `remote={'agent_id': ...}` A2A 委派）、`action='complete'`（A2A Worker 回传）、`action='list_agents'`；A2A 派发后主循环挂起，回调经 `a2a_callback` 写回工具消息后恢复。
- **MCP server 故障隔离（强制约定）**：每个 MCP server 的 transport 生命周期在**独立长驻 runner 任务**里（`manager.py::_server_runner`，anyio scope 自包含），单 server 故障（502/超时/失联）只降级为 `ConnectionResult(success=False)`，**严禁向上传播**到 connect_all/safe_handle/lifespan——`except Exception` 接不住 anyio 混入 CancelledError 成分时的 **BaseExceptionGroup**（BaseException 子类）。`connect_from_db` 不按 enabled 过滤（enabled=0 = 不随启动常驻，显式按名连接是按需拉起）。新增 server 连接路径时必跑 `tests/unit/core/mcp/` + 人工验证「坏 server 下服务可启动」。
- **防循环**：代码层 doom_loop 检测（`inference_engine.doom_loop_detected`，连续 3 次相同工具签名 → `DoomLoopException` → 问用户"停止/继续"：HITL 挂起等人，docker 模式豁免为确定性收尾，见「自主值守（任务队列）开发约束」）；已移除 prompt 反循环协议（verification_blocked/unverifiable/report_outcome）。
- **上下文管理**：`ContextTrimmer` + executor 统一截断（`react/truncate.py` 超限输出折叠+落盘），节点级 filter 已删除。
- **收尾管线**：`engine/react/completion.py` 在 run 结束时发布 SESSION_COMPLETED，并触发 episodic 记忆、宏资格判定、skill 候选生成（代码层，非 prompt 规则）。运行终态事件全貌（AgentRunCompletedEvent 全终态发布、HITL 挂起是唯一例外）见下文「自主值守（任务队列）开发约束」。
- **数据库迁移**：模型变更后用 `alembic revision --autogenerate -m "描述"` 生成迁移

## 自主值守（任务队列）开发约束

> 本节只放**开发约束**（不变量/红线/规范）。设计叙事、护栏清单、阶段记录与终局裁决约定归档于 **docs/root/autonomous-task-loop.md**（缺失时以代码 + `tests/unit/domain/tasks/` 为准），AGENTS 不重复。

两套"值守"语义不同，禁止混用：**客服值守** = `app/core/channel/duty/`（企微/微信客服轮巡，启停入口 `PUT /projects/{id}/duty` → `provision.py`）；**自主值守** = `app/domain/tasks/` 任务队列（ProjectTask SSOT）：状态机 `service.py`、常量 `constants.py`、跨边界模型 `schemas.py`、Agent 工具面 `tools/`（薄封装，业务在 service）、派发编排/死亡收敛/唤醒/主循环宿主 `runtime/`。**分层红线：infrastructure 是底层，严禁 import app.domain（domain → infrastructure 才是合法方向）**——值守业务逻辑只住 domain，main.py lifespan 只拉起 `domain/tasks/runtime/supervisor.py::run_supervisor_forever`。

### 任务队列不变量（违反即返工）

- **单 drainer**：project_tasks 派发只发生在 supervisor（scheduler tick 只剩渠道轮巡定时器）；生产部署硬约束 `WORKERS=1`（in-flight 态在进程内存，多 worker 会重复派发）。
- **状态机**：一切转移以 `constants.py QUEUE_TRANSITIONS` 为准；所有写走 `version` 乐观锁（take/claim/advance/acceptance/requeue/edit）；`advance_task(thread_id=…)` 校验执行权归属。
- **fail-closed 四则**：external 来源 → proposed（需确认）；缺 risk 的 one-shot 自检 → waiting_acceptance（不默认 T3）；accept 必有 result；T1/T2 创建必须 `acceptance_criteria` 非空（缺失即拒，API 层 422）。
- **一等列铁律**：title/priority/category/tags/dependencies/acceptance_criteria/workflow_id/workflow_round/dispatch_count/last_result/last_error/review_pending/version 均为 `project_tasks` 列，读走 `service.py` 顶部兼容函数；**禁止往 task_data 写这些键**。
- **依赖门控唯一实现**：`TaskQueueService.evaluate_dependency_gate`（claim 扫描与派发闸共用；recurring lineage-only 豁免；dispatcher 只做断链告警副作用）。
- **熔断/防毒**：dispatch_count≥5 强制 failed（推进成功时清零，防健康 recurring 被误杀）；reconcile 回队 `REQUEUE_LIMIT=3`；failed 自动重试预算 1 次/10min（内容审查/配置类错误永不重试）；escalated 任务禁自动重试。
- **派发即认领（claim-then-persist）**：派发前原子认领（pending→in_progress+last_thread_id+dispatch_count++），FAILED/异常回滚 pending。**收敛不变式：run 结束后任务必须已认领或已达终态**——否则 DutyWakeupSubscriber（AgentRunCompletedEvent 必发）立即重派形成热循环。
- **recurring**：认领即推进 next_run_at 落盘；到期门控 one-shot 走 due_at、recurring 只认 next_run_at；自检回队（self_checked→pending）是正确终态。
- **周期编排唯一形态 = 工作流**（`tasks create_workflow`/`POST /tasks/workflows`，Kahn 环检测+拓扑序+触发器强校验；spawn 幂等 dedup + skip-on-busy 轮次绝不并发）；recurring 与任务图（parent_id/dependencies）互斥。
- **评审纪律**：reviewer rejected ≤2 轮 → failed+escalated（杜绝评审-返工无限循环）；评审派发失败保持 waiting_acceptance（绝不 fallback auto-accept，30min 超时兜底）；verdict 判定以落库消息为准，**排序必须 `sequence_number`**（`Message.id` 是随机 UUID）。
- **message 引用 metadata 直通**：`engine/message/reference.py` message 分支必须保留调用方 `metadata/meta_data`（值守评审引用携带 thread_id/task_id，前端执行会话胶囊依赖它；契约测试 `test_message_reference_metadata_passthrough.py` 锁定）。
- **评审结论互链**：结论结构化挂到评审回复消息（`meta_data.duty_task`）→ Chat 端 TaskStateChip 跳画布（sessionStorage `duty:focus-task` 一次性交接）。
- **UI 约束**：节点页会话入口单一化（按状态选线程，禁止叠加第二会话入口）；画布轮次投影（工作流任务只渲染选中轮，`workflow_round` 已进队列 API）；画布仲裁三键已由原开发者接线（rerun/cancelled/update+rerun，taskAdapter 注入 arbitration 规格，节点页控制台渲染，`DutyArbitration.test.tsx` 锁定）。
- **执行形态**：每任务一个 wakeup run（`wakeup_{pid}_{task_id}` 每轮新线程）；任务描述 = 第一条 human 消息全文（零模板包装）；任务元信息走 `metadata.duty_task` → `main.duty.task.txt`；feedback 由 Python 侧组装；`resolve_wakeup_domain` 对 pid=0 fail-open 不跑 L1（域装配事故回归锁定）。
- **single SSOT**：`/api/v1/tasks/*` 只有队列面；EvoCloud 代理在 `/api/v1/evocloud/tasks/*`；subtasks API/旧任务工具岛已删除；`task_runs` 是过程审计层，不参与状态机判定。

### 运行终态与事件（连续运行/看门狗/reconcile 设计的事实源）

- `AgentRunCompletedEvent` 由 `app/core/monitoring/activity.py` 在**全部终态**发布（DONE/CANCELLED/FAILED/QUOTA_EXHAUSTED，恰好一次）；`max_steps` 耗尽 = TRUNCATED，是安全终态不是断链。
- **HITL 挂起是唯一不发终态的出口**：`AgentHumanInterruptException` 被外层吞掉正常 return，`AgentActivity` 悬挂 running（内部记账语义；reconciler 以 `RUN_SKIP_STATUSES` 豁免 + 35min 判死例外承接）；**用户可见性已闭环**：hitl-pending → 状态条「⚠ N 项审批等待你」+ 列表徽标 + 选中节点决策卡对位替换输入框 + 企微/手机推送。
- `stop_agent`（`session/manager.py`）对直跑 run（值守 wakeup）**只剩协作式标志**——硬取消必须持有 asyncio.Task 句柄（CancelledError 被 run_scope 接住 → end_run(CANCELLED) → 事件照发）。
- `dispatch_agent_run` 多租户 fail-closed：member_id 必需且从 Conversation 回填——全新 thread（如 `wakeup_*`）回填失败会 raise，值守派发必须显式携带 `ProjectTask.member_id`。

### HITL / 权限边界

- `hitl_enabled()`（`hitl/core.py`，非 docker 即启用）是单一出处；docker 豁免三处生效：`ask_human` 自动应答、`authorization_gate` 自动批准（matcher=".*" **覆盖全部工具含 MCP**）、doom guard 落入确定性收尾。
- **docker auto-approve 对 MCP 业务写没有沙箱兜底**（调用出进程直达真实业务系统）——MCP 业务动作的决策边界在任务级（risk_level T1-T4 + waiting_acceptance/提案确认），不在工具门控。
- **信任纪律（连续运行的前提）**：完全清楚时一撸到底；历经多轮努力仍摸不清、或 T1/T2 有疑虑时**必须用 `question` 提问等人**，严禁静默乱猜乱决策。挂起等人是合法决策机制而非故障——目标是**挂起便宜、应答快速触达、问人频率可审计（值守健康度指标）**。禁止用结构约束（禁用 ask_human、强制自动应答）替代这一运行时判断（与关卡二第 4 问同理）。

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
