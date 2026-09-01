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

- **Python 版本**：3.11+（`pyproject.toml` 中限制 `>=3.11,<3.13`）
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

## Agent 开发注意事项

- **引擎架构**：单 Agent ReAct 主循环（对齐 OpenCode）。`app/core/engine/react/loop.py` 的 `run_agent_loop` 是唯一执行体——一条连续消息流，主 Agent 拥有全量工具，直到无 tool_calls 的文本回复结束；无 supervisor/worker/finish 图节点、无 signals、无 ExecutionTicket、无消息过滤。主 Agent 工具面见 `app/core/engine/config/agent_main.yaml` 的 `agents.react.tools`（默认 15 个）。
- **状态管理**：通过 `app/core/engine/state/` 管理生命周期与工作区状态（`AgentState` 精简版，移除图架构字段）。
- **提示词模板**：主 Agent 人格用 `app/config/templates/core/agent/*.txt` 纯文本（非 Jinja2），动态块（环境/记忆/`<available_skills>`/`<available_macros>`/`<available_agents>`）由 `app/core/engine/react/prompts.py` 代码层拼接；其余内部合成 prompt 仍用 `.j2`（二期迁移）。
- **工具面**：`@evoloop_tool` 注册（约 80 个），react 主 Agent 默认面 14 个（bash/read/glob/grep/edit/write/task/webfetch/websearch/todo/skill/question/macro/remember）；低频能力走 `skill`/`macro`/`task` 索引+按需加载。
- **子代理与 A2A**：统一收敛到 `task` 工具——`action='run'`（本地 spawn / `remote={'agent_id': ...}` A2A 委派）、`action='complete'`（A2A Worker 回传）、`action='list_agents'`；A2A 派发后主循环挂起，回调经 `a2a_callback` 写回工具消息后恢复。
- **防循环**：代码层 doom_loop 检测（`inference_engine.doom_loop_detected`，连续 3 次相同工具签名 → `DoomLoopException` → react loop 确定性收尾）；已移除 prompt 反循环协议（verification_blocked/unverifiable/report_outcome）。
- **上下文管理**：`ContextTrimmer` + executor 统一截断（`react/truncate.py` 超限输出折叠+落盘），节点级 filter 已删除。
- **收尾管线**：`engine/react/completion.py` 在 run 结束时发布 SESSION_COMPLETED，并触发 episodic 记忆、宏资格判定、skill 候选生成（代码层，非 prompt 规则）。
- **数据库迁移**：模型变更后用 `alembic revision --autogenerate -m "描述"` 生成迁移

## API 响应规范（新代码必须遵循）

- **统一信封**（见 `docs/api-response-envelope.md`）：
  - 成功单对象 → `DataResponse`（`{success, message, data}`）
  - 成功列表/分页 → `ListResponse`（`{success, message, data, total, page, page_size}`）
  - 错误 → 全局 handler（`app/api/errors.py`）自动生成 `{success, code, message, detail}`，路由层直接 `raise HTTPException`，**禁止手动返回错误 JSON**
  - **禁止新增自定义 `XxxResponse` 信封模型**，统一从 `app/api/schemas/responses.py` 导入
- **保留场景**（不改，契约特殊）：SSE/流式、文件下载/上传、Webhook、云透传代理（`{code, data}`，tasks/subscription/member）
- 存量 ~233 端点按文档指引**渐进式**迁移，不做一次性全量改造

## 安全与工具输出约定

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
