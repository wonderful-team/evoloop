# Repository Guidelines

## 项目结构与模块组织

```
backend/
├── app/                    # 应用源码
│   ├── api/                # FastAPI 路由与端点
│   ├── core/               # 核心业务逻辑
│   │   ├── engine/         # Agent 执行引擎（图构建、节点、状态、消息、回调等）
│   │   ├── learning/       # 学习与技能合成
│   │   ├── memory/         # 记忆系统
│   │   ├── execution/      # 任务执行与工具链
│   │   └── vision/         # 多模态视觉处理
│   ├── config/             # 配置与 Jinja2 提示词模板（templates/core/）
│   ├── models/             # SQLModel 数据模型
│   ├── services/           # 业务服务层
│   └── infrastructure/     # 基础设施（数据库、缓存等）
├── tests/                  # 测试用例
│   ├── unit/               # 单元测试（快速、隔离）
│   ├── integration/        # 集成测试（需外部服务）
│   └── e2e/                # 端到端测试（完整系统）
├── scripts/                # 工具与运维脚本
├── bin/                    # CLI 入口（evo 命令）
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
bin/evo test               # 运行单元测试
bin/evo test cov           # 测试 + 覆盖率报告
bin/evo test e2e           # 端到端测试
pytest tests/unit -v       # 直接用 pytest 运行
pytest tests/unit/core/engine/ -v  # 仅测试引擎模块
```

## 代码风格与命名约定

- **Python 版本**：3.11+（`pyproject.toml` 中限制 `>=3.11,<3.13`）
- **格式化与 Lint**：使用 Ruff（`ruff check` + `ruff format`），目标版本 `py310`
- **类型检查**：mypy strict 模式（排除 `venv`、`alembic`）
- **命名规范**：
  - 模块/文件名：`snake_case`（如 `context_trimmer.py`）
  - 类名：`PascalCase`（如 `AgentEngine`、`EvoMessageConverter`）
  - 常量：`UPPER_SNAKE_CASE`
- **导入规范**：使用 lazy imports 避免重型模块过早加载（参见 `app/core/engine/__init__.py`）
- **禁止事项**：不允许 `print` 语句（Ruff T201 规则），测试和脚本目录除外
- **模板文件**：提示词模板使用 Jinja2，存放于 `app/config/templates/core/`，按功能分目录（`memory/`、`learning/`、`engine/` 等）

## 测试指南

- **框架**：pytest + pytest-asyncio（`asyncio_mode = auto`）
- **测试命名**：文件 `test_*.py`，类 `Test*`，函数 `test_*`
- **测试标记**（`@pytest.mark`）：`unit`、`integration`、`e2e`、`slow`、`llm`、`db`、`performance`
- **超时**：默认 60 秒（`pytest-timeout`）
- **覆盖率**：`pytest-cov`，报告生成至 `htmlcov/index.html`
- **并行执行**：`pytest tests/unit -n auto --dist=loadfile`

## 提交与合并规范

- 提交消息使用中文，格式为简短描述性语句（如"新增多轮对话测试脚本"、"优化聊天界面性能"）
- 重要变更建议加前缀：`新增`、`修复`、`优化`、`重构`、`暂存`
- PR 需包含变更说明，关联相关 issue

## Agent 开发注意事项

- **引擎架构**：基于 LangGraph 的图执行模型，核心节点包括 `supervisor`、`worker`、`chat`、`finish`
- **状态管理**：通过 `app/core/engine/state/` 管理生命周期与工作区状态
- **提示词模板**：修改提示词时编辑 `app/config/templates/core/` 下的 `.j2` 文件，不要硬编码在 Python 中
- **数据库迁移**：模型变更后用 `alembic revision --autogenerate -m "描述"` 生成迁移

## DevOps 测试现状 (2026-06-17)

### 已通过的场景
| 场景 | 文件 | 耗时 | 说明 |
|------|------|------|------|
| `check_config` | `tests/manual/test_devops_lifecycle.py` | ~30s | 配置校验 |
| `release` | `tests/manual/test_devops_lifecycle.py` | ~340s | 版本号同步（含文件恢复） |
| `build` | `tests/manual/test_devops_lifecycle.py` | ~50s | 前端构建 |
| `deploy` + vault 占位符 | `tests/manual/test_devops_deploy.py` | ~500s | 密码箱有凭证时使用 `{{vault.id.field}}` |
| `deploy` + HITL 回退 | `tests/manual/test_devops_deploy.py` | ~100s | 密码箱无凭证时触发 `ask_human` |
| 配置失败不构建 | `tests/manual/test_devops_negative.py` | ~35s | 校验失败时 Agent 停止并报告 |

### 关键安全修复
`app/core/engine/hooks/security.py` 的 `sensitive_file_censorship_gate` 原仅在同一个 `HookContext.extra` 中读取 `injected_secrets`，跨 tool call 后 `extra` 被重置，导致占位符替换后的真实密钥在后续输出中**未被脱敏**。已增加从 `EvoContext.injected_secrets` 回退读取，确保同一次运行中所有工具输出都被打码。

### 工具输出信息确认
`tool_output` 类型的 Message 中：
- `content` 字段仅存储摘要（如 `✅ Command Succeeded.` / `❌ Command Failed (Exit Code N).`），**不含**完整 STDOUT/STDERR
- 完整命令输出存储在 `meta_data` 字段（JSON 格式）
- AI 消息的 `tool_calls` 字段存储工具调用结构体（含命令文本）

因此验证命令是否执行时，**不能**仅依赖 `tool_output.content`（摘要中不含 `devops.sh`/`build` 等关键词）。应同时检查 `meta_data` 和 `tool_calls`。参见 `test_devops_lifecycle.py:415-` 的 `verify_build()` 实现。

### 运行方式
```bash
cd evoloop/backend
uv run python tests/manual/test_devops_lifecycle.py --scenario all --project-id 57
uv run python tests/manual/test_devops_deploy.py --case all --project-id 57
uv run python tests/manual/test_devops_negative.py --project-id 57
```
