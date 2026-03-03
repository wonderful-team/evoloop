# EvoLoop CLI 工具

统一的命令行工具，封装所有开发、测试、清理、验证操作。

## 安装

```bash
# 方式1: 直接执行 (在项目 backend 目录)
bin/evo help

# 方式2: 创建全局命令
chmod +x bin/evo bin/run_sidecar.py
sudo ln -s $(pwd)/bin/evo /usr/local/bin/evo

# 然后可以在任何地方使用
evo help
```

## 快速参考

```
╔══════════════════════════════════════════════════════════════╗
║                    EvoLoop CLI 工具                          ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  【开发环境】                                                 ║
║    evo install          安装依赖                             ║
║    evo dev              启动开发服务器                        ║
║    evo worker           启动 Celery Worker                   ║
║    evo stop             停止所有服务                         ║
║                                                              ║
║  【代码质量】                                                 ║
║    evo lint             运行代码检查                         ║
║    evo format           格式化代码                           ║
║    evo check            全面代码检查                         ║
║    evo fix              自动修复代码问题                     ║
║                                                              ║
║  【测试】                                                     ║
║    evo test             运行测试套件                         ║
║    evo test cov         运行测试并生成覆盖率报告              ║
║    evo test e2e         运行端到端测试                       ║
║    evo test brain       运行 Brain 模块测试                  ║
║    evo test atlas       运行 Atlas 模块测试                  ║
║                                                              ║
║  【数据库】                                                   ║
║    evo db init          初始化数据库                         ║
║    evo db migrate       运行数据库迁移                       ║
║    evo db reset         重置数据库                           ║
║    evo db seed          填充测试数据                         ║
║                                                              ║
║  【知识库】                                                   ║
║    evo kb reset         清空并重建知识库索引                 ║
║    evo kb clean         仅清空知识库                         ║
║    evo kb rebuild       仅重建知识库索引                     ║
║    evo kb reindex       重新索引所有项目                     ║
║                                                              ║
║  【系统清理】                                                 ║
║    evo clean            清理运行时缓存                       ║
║    evo clean all        完整系统清理                         ║
║    evo clean dry        预览清理内容                         ║
║    evo clean skills     清理技能数据                         ║
║    evo clean memory     清理记忆数据                         ║
║    evo clean expired    清理过期截图和录制                   ║
║    evo clean help       查看完整清理命令列表                 ║
║                                                              ║
║  【存储管理】                                                 ║
║    evo storage stats    查看存储统计                         ║
║    evo storage clean    清理过期存储文件                     ║
║    evo storage test     测试存储功能                         ║
║                                                              ║
║  【Atlas/Mobile】                                           ║
║    evo atlas test       运行 Atlas 端到端测试                ║
║    evo atlas mobile     运行 Atlas 移动端测试                ║
║    evo atlas clear      清空 Atlas 数据                      ║
║                                                              ║
║  【Brain】                                                   ║
║    evo brain test       运行 Brain 完整测试                  ║
║    evo brain real       运行 Brain 实机测试                  ║
║    evo brain letta      运行 Brain Letta 测试                ║
║                                                              ║
║  【验证】                                                     ║
║    evo verify skill     验证技能执行                         ║
║    evo verify storage   验证存储系统                         ║
║    evo verify vector    验证向量维度                         ║
║    evo verify peekaboo  验证 Peekaboo                        ║
║                                                              ║
║  【演示】                                                     ║
║    evo demo final       最终演示                             ║
║    evo demo phase3      阶段3演示                            ║
║    evo demo mobile      移动端演示                           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

## 使用场景示例

### 场景1: 全新环境搭建

```bash
evo install      # 安装依赖
evo db init      # 初始化数据库
evo db seed      # 填充测试数据
evo kb reset     # 建立知识库索引
```

### 场景2: 日常开发

```bash
# 终端1
evo dev

# 终端2
evo worker

# 终端3
evo lint         # 代码检查
evo format       # 格式化
```

### 场景3: 测试验证

```bash
evo test                    # 单元测试
evo test cov               # 覆盖率测试
evo test brain             # Brain 测试
evo test atlas             # Atlas 测试
```

### 场景4: 系统维护

```bash
evo clean                   # 清理运行时缓存
evo clean dry              # 预览清理内容
evo clean all              # 完整清理（⚠️ 危险）
evo clean skills           # 清理技能数据
evo clean memory           # 清理记忆数据
evo clean expired          # 清理过期截图和录制
evo clean help             # 查看完整清理命令列表

evo storage stats          # 查看存储使用
evo storage clean          # 清理过期文件
```

### 场景5: 知识库维护

```bash
evo kb clean               # 仅清空索引
evo kb rebuild             # 仅重建索引
evo kb reset               # 清空+重建
```

### 场景6: 验证调试

```bash
evo verify skill           # 验证技能
evo verify storage         # 验证存储
evo verify vector          # 验证向量
evo debug                  # 调试消息
evo analyze                # 分析循环
```

## 对比旧 Makefile

| 旧命令 (Makefile) | 新命令 (evo) |
|------------------|-------------|
| `make dev` | `evo dev` |
| `make test` | `evo test` |
| `make test-cov` | `evo test cov` |
| `make db-reset` | `evo db reset` |
| `make kb-reset` | `evo kb reset` |
| `make clean-all` | `evo clean all` |
| `make storage-stats` | `evo storage stats` |

## 扩展

如需添加新命令，编辑 `evo` 文件，在 `case` 语句中添加新的命令处理。

## 服务管理

### 一键启动所有服务

```bash
# 启动 API + Worker + Beat（后台运行，自动记录日志）
bin/evo start
```

输出示例：
```
ℹ 一键启动所有服务...
ℹ 启动 API 服务...
✓ API 服务启动成功 (PID: 12345)
ℹ 启动 Worker 服务...
✓ Worker 服务启动成功 (PID: 12346)
ℹ 启动 Beat 服务...
✓ Beat 服务启动成功 (PID: 12347)

ℹ 日志文件位置:
  API:    /path/to/logs/api.log
  Worker: /path/to/logs/worker.log
  Beat:   /path/to/logs/beat.log

ℹ 查看日志: evo logs
ℹ 停止服务: evo stop
```

### 查看服务状态

```bash
bin/evo status
```

### 查看日志

```bash
# 查看所有日志（合并输出）
bin/evo logs

# 查看指定服务日志
bin/evo logs api
bin/evo logs worker
bin/evo logs beat

# 日志文件位置
ls logs/
# api.log  api.pid  beat.log  beat.pid  worker.log  worker.pid
```

### 停止所有服务

```bash
bin/evo stop
```

### 对比：前台 vs 后台

| 场景 | 命令 | 特点 |
|------|------|------|
| 开发调试 | `evo dev` / `evo worker` / `evo beat` | 前台运行，Ctrl+C 停止，实时看输出 |
| 生产部署 | `evo start` | 后台运行，记录日志，自动管理 PID |

---

## 系统清理命令详解

`evo clean` 命令用于清理 EvoLoop 系统的各种数据。它底层调用 `scripts/cleanup_system.py` 脚本。

### 完整命令列表

| 命令 | 说明 | 对应底层参数 |
|------|------|-------------|
| `evo clean all` | 完整系统清理（所有组件） | `--all --confirm` |
| `evo clean dry` | 预览将被清理的内容 | `--dry-run --all` |
| `evo clean redis` | 清理 Redis 缓存 | `--redis` |
| `evo clean neo4j` | 清理 Neo4j 文件索引 | `--neo4j` |
| `evo clean memory` | 清理记忆数据（概念/历史/偏好） | `--memory` |
| `evo clean skills` | 清理技能数据（DB + 文件） | `--skills` |
| `evo clean index` | 清理 PostgreSQL 文件索引 | `--index` |
| `evo clean messages` | 清理消息历史 | `--messages` |
| `evo clean jobs` | 清理任务队列 | `--jobs` |
| `evo clean screenshots` | 清理截图 | `--screenshots` |
| `evo clean recordings` | 清理屏幕录制 | `--recordings` |
| `evo clean knowledge` | 清理知识库文件 | `--knowledge` |
| `evo clean brain` | 清理 Brain Memory | `--brain` |
| `evo clean expired` | 清理过期截图和录制 | `--expired-only --screenshots --recordings` |
| `evo clean runtime` | 清理运行时缓存（默认） | - |
| `evo clean help` | 查看完整清理命令列表 | - |

### 使用示例

```bash
# 预览将被清理的内容（推荐首次使用）
evo clean dry

# 清理特定组件
evo clean skills
evo clean memory
evo clean messages

# 清理过期文件（日常维护）
evo clean expired

# 完整系统清理（⚠️ 危险，会要求确认）
evo clean all
```

### 清理组件说明

| 组件 | 存储位置 | 清理内容 |
|------|----------|----------|
| **redis** | `redis://localhost:6379/0` | 上下文缓存、意图缓存 |
| **neo4j** | `bolt://localhost:7687` | File、Directory、CodeEntity、CodeChunk 节点 |
| **memory** | `bolt://localhost:7687` | Concept、Episode、Preference、User 节点 |
| **skills** | PostgreSQL + `~/.evoloop/skills/` | 技能表 + 技能文件 |
| **index** | PostgreSQL | code_chunks、code_relations、source_files 等 |
| **messages** | PostgreSQL | messages、conversations 表 |
| **jobs** | PostgreSQL | jobs 表 |
| **screenshots** | `~/.evoloop/artifacts/screenshots/` | 所有截图 |
| **recordings** | `~/.evoloop/artifacts/recordings/` | 屏幕录制视频和帧 |
| **knowledge** | `~/.evoloop/library/` | 知识库 Markdown 文件 |
| **brain** | `~/.evoloop/memory/` | Brain Memory 文件 |

### 注意事项

- `evo clean all` 和 `evo clean memory` 会要求输入 `yes` 确认
- `evo clean skills` 会同时清理数据库表和技能文件
- 清理后重启服务，内置技能会自动从 `app/core/learning/skills/` 复制到 `~/.evoloop/skills/`

