# EvoLoop Backend

EvoLoop 后端服务，基于 FastAPI 构建，提供 API 服务和异步任务处理能力。

## 系统要求

* [Docker](https://www.docker.com/) - 用于运行数据库等服务
* [uv](https://docs.astral.sh/uv/) - Python 包管理和环境管理
* Python 3.11+

## 快速开始

### 1. 安装依赖

```console
$ cd backend
$ uv sync
```

### 2. 启动服务

我们提供了统一的 CLI 工具 `evo` 来管理所有操作：

```console
# 查看所有可用命令
$ bin/evo help

# 启动开发服务器
$ bin/evo dev

# 启动 Celery Worker（需要另一个终端）
$ bin/evo worker
```

### 3. 数据库初始化

```console
# 运行迁移
$ bin/evo db migrate

# 填充测试数据（可选）
$ bin/evo db seed
```

## 项目结构

```
backend/
├── bin/                    # 可执行脚本
│   ├── evo                 # Evo CLI 工具（主入口）
│   ├── run.py              # Python 运行入口
│   └── run_sidecar.py      # PyInstaller 打包入口
├── app/                    # 应用代码
├── scripts/                # 工具脚本（清理、测试等）
├── tests/                  # 测试用例
└── docs/                   # 文档
```

## evo CLI 工具

`evo` 是 EvoLoop 的统一命令行工具，封装了日常开发所需的所有命令。

### 常用命令

```bash
# 开发环境
bin/evo dev           # 启动 API 开发服务器
bin/evo worker        # 启动 Celery Worker
bin/evo stop          # 停止所有服务

# 代码质量
bin/evo lint          # 代码检查
bin/evo format        # 代码格式化
bin/evo check         # 全面代码检查（lint + type check）

# 测试
bin/evo test          # 运行单元测试
bin/evo test cov      # 运行测试并生成覆盖率报告
bin/evo test e2e      # 运行端到端测试

# 数据库
bin/evo db migrate    # 运行数据库迁移
bin/evo db reset      # 重置数据库
bin/evo db seed       # 填充测试数据

# 知识库
bin/evo kb reset      # 清空并重建知识库索引

# 系统清理
bin/evo clean         # 清理运行时缓存
```

查看完整命令列表：`bin/evo help`

## 开发环境配置

### 使用虚拟环境

```console
$ source .venv/bin/activate
```

确保编辑器使用正确的 Python 解释器：`backend/.venv/bin/python`

### VS Code 支持

项目已配置 VS Code 调试器，支持：
- 断点调试
- 测试面板集成
- 代码格式化（Ruff）

### 环境变量

复制 `.env.example` 到 `.env` 并根据需要修改：

```bash
cp .env.example .env
```

关键配置项：
- `POSTGRES_*` - 数据库连接
- `REDIS_URL` - Redis 连接
- `SECRET_KEY` - JWT 密钥
- `OPENAI_API_KEY` - OpenAI API 密钥

Modify or add SQLModel models for data and SQL tables in `./backend/app/models.py`, API endpoints in `./backend/app/api/`, CRUD (Create, Read, Update, Delete) utils in `./backend/app/crud.py`.

## 测试

```bash
# 运行所有测试
bin/evo test

# 运行测试并生成覆盖率报告
bin/evo test cov

# 运行端到端测试
bin/evo test e2e

# 运行特定模块测试
bin/evo test brain
bin/evo test atlas
```

测试覆盖率报告生成在 `htmlcov/index.html`，可在浏览器中查看。

## 部署

### 开发部署

```bash
# 启动完整开发环境（API + Worker）
bin/evo dev        # 终端 1
bin/evo worker     # 终端 2
```

### 生产部署（PyInstaller 打包）

```bash
# 构建可执行文件
pyinstaller evoloop-backend.spec

# 运行打包后的程序
./dist/evoloop-backend api     # 启动 API
./dist/evoloop-backend worker  # 启动 Worker
```

### Docker 部署

使用 Docker Compose 快速启动完整环境：

```bash
# 启动所有服务
docker compose up -d

# 查看日志
docker compose logs -f backend

# 进入容器执行命令
docker compose exec backend bash
```

#### Docker Compose 开发配置

开发环境可使用 `docker-compose.override.yml` 覆盖默认配置：

- 代码热重载
- 调试模式
- 本地代码挂载

```bash
# 开发模式启动
docker compose watch
```

#### 进入容器调试

```console
$ docker compose exec backend bash
root@7f2607af31c3:/app#
```

现在你可以在容器内使用 `evo` 命令：

```console
root@7f2607af31c3:/app# evo dev
```

## bin/ 目录详解

```
bin/
├── evo              # 主 CLI 工具（bash）
├── run.py           # Python 运行入口
└── run_sidecar.py   # PyInstaller 打包入口
```

- `evo` - 开发/运维的统一命令入口
- `run.py` - 可直接用 Python 运行：`python bin/run.py api`
- `run_sidecar.py` - 打包后的桌面应用入口，委托给 `run.py`

### Test Coverage

When the tests are run, a file `htmlcov/index.html` is generated, you can open it in your browser to see the coverage of the tests.

## 数据库迁移

使用 Alembic 管理数据库迁移：

### 创建迁移

修改模型后，创建新的迁移版本：

```bash
# 使用 evo 命令
bin/evo db migrate

# 或直接使用 alembic
alembic revision --autogenerate -m "添加用户字段"
```

### 常用命令

```bash
# 升级到最新版本
alembic upgrade head

# 降级到指定版本
alembic downgrade -1

# 查看当前版本
alembic current

# 查看历史
alembic history
```

### 不使用迁移（仅开发）

如需在开发环境自动创建表（不推荐用于生产）：

1. 在 `app/core/db.py` 中取消注释：
   ```python
   SQLModel.metadata.create_all(engine)
   ```

2. 删除 `alembic/versions/` 下的所有迁移文件

## 进阶配置

## 更多文档

- [evo CLI 完整文档](./docs/EVO_CLI.md)
- [系统清理指南](./docs/SCRIPTS_CLEANUP_PLAN.md)
- [API 文档](http://localhost:8000/docs)（启动后访问）

## Email Templates

The email templates are in `./backend/app/email-templates/`. Here, there are two directories: `build` and `src`. The `src` directory contains the source files that are used to build the final email templates. The `build` directory contains the final email templates that are used by the application.

Before continuing, ensure you have the [MJML extension](https://marketplace.visualstudio.com/items?itemName=attilabuti.vscode-mjml) installed in your VS Code.

Once you have the MJML extension installed, you can create a new email template in the `src` directory. After creating the new email template and with the `.mjml` file open in your editor, open the command palette with `Ctrl+Shift+P` and search for `MJML: Export to HTML`. This will convert the `.mjml` file to a `.html` file and now you can save it in the build directory.
