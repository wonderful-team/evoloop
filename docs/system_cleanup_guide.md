# EvoLoop 系统清理工具使用指南

## 目录

- [概述](#概述)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [命令行参数](#命令行参数)
- [使用场景](#使用场景)
- [存储组件详解](#存储组件详解)
- [故障排除](#故障排除)
- [安全建议](#安全建议)

---

## 概述

EvoLoop 系统清理工具是一个用于管理和清理 EvoLoop 后端各种存储组件的命令行工具。它支持清理以下数据存储：

- **Redis** - 缓存和临时数据
- **Neo4j** - 图数据库（文件索引和记忆数据）
- **PostgreSQL** - 关系数据库（技能、索引、消息、任务队列）
- **文件系统** - 截图、录制、知识库文件

## 环境要求

- Python 3.11+
- 可选：Redis 服务（用于清理缓存）
- 可选：Neo4j 服务（用于清理图数据库）
- 可选：PostgreSQL 服务（用于清理关系数据）

## 快速开始

### 1. 查看帮助

```bash
cd backend
python scripts/cleanup_system.py --help
```

### 2. 干运行模式（推荐首次使用）

在实际清理之前，先预览将要删除的内容：

```bash
python scripts/cleanup_system.py --dry-run --all
```

### 3. 执行清理

```bash
# 清理所有组件（危险！）
python scripts/cleanup_system.py --all

# 或只清理特定组件
python scripts/cleanup_system.py --redis --skills
```

---

## 命令行参数

### 组件选择参数

| 参数 | 说明 | 数据类型 |
|------|------|----------|
| `--all` | 清理所有组件 | 全局 |
| `--redis` | 清理 Redis 缓存 | 缓存 |
| `--neo4j` | 清理 Neo4j 文件索引 | 文件索引 |
| `--memory` | 清理 Neo4j 记忆数据 | 记忆 |
| `--skills` | 清理 PostgreSQL 技能表 | 技能 |
| `--index` | 清理 PostgreSQL 文件索引表 | 文件索引 |
| `--messages` | 清理 PostgreSQL 消息表 | 消息 |
| `--jobs` | 清理 PostgreSQL 任务队列 | 任务 |
| `--screenshots` | 清理截图文件 | 文件 |
| `--recordings` | 清理屏幕录制 | 文件 |
| `--knowledge` | 清理文件知识库 | 文件 |
| `--brain` | 清理 Brain Memory 文件 | 文件 |

### 选项参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--dry-run` | 预览模式，不实际删除 | `--dry-run --all` |
| `--confirm` | 删除前要求确认 | `--all --confirm` |
| `--expired-only` | 仅清理过期数据 | `--expired-only --screenshots` |
| `--keep-apps` | 保留 Atlas 应用数据 | `--neo4j --keep-apps` |

---

## 使用场景

### 场景 1：开发环境重置

当你需要重置开发环境，清除所有测试数据：

```bash
# 1. 先预览
python scripts/cleanup_system.py --dry-run --all

# 2. 执行清理（带确认）
python scripts/cleanup_system.py --all --confirm
```

### 场景 2：仅清理文件索引（重新索引代码库）

当你更新了代码库，需要重新索引：

```bash
# 清理文件索引
python scripts/cleanup_system.py --neo4j --index

# 然后重新运行代码索引任务
```

### 场景 3：清理过期截图和录制

定期清理以释放磁盘空间：

```bash
# 只清理过期的截图和录制
python scripts/cleanup_system.py --expired-only --screenshots --recordings
```

### 场景 4：清理学习到的技能

当技能数据混乱或需要重新训练：

```bash
# 只清理技能数据
python scripts/cleanup_system.py --skills
```

### 场景 5：清理用户记忆（保留文件索引）

当需要清除用户相关的记忆数据：

```bash
# 清理记忆节点
python scripts/cleanup_system.py --memory

# 同时清理消息历史
python scripts/cleanup_system.py --memory --messages
```

### 场景 6：完整知识库重置

知识库包括两部分：语义知识（Neo4j）和文件知识（文件系统）：

```bash
# 清理两部分知识库
python scripts/cleanup_system.py --memory --knowledge
```

---

## 存储组件详解

### 1. Redis 缓存 (`--redis`)

**存储位置**：`redis://localhost:6379/0`

**数据内容**：
- `evo:context:{thread_id}` - 线程执行上下文
- `evo:intent_cache:{hash}` - 意图匹配缓存
- `system:dynamic_apps:{platform}` - 动态应用分类
- `system:processed_apps:{platform}` - 已处理应用追踪

**清理影响**：
- ✅ 安全的清理操作
- ⚠️ 正在进行的对话上下文会丢失
- ⚠️ 意图缓存需要重新构建

**命令**：
```bash
python scripts/cleanup_system.py --redis
```

---

### 2. Neo4j 文件索引 (`--neo4j`)

**存储位置**：`bolt://localhost:7687`

**数据内容**：
- `File` - 文件引用
- `Directory` - 目录结构
- `CodeEntity` - 代码符号/实体
- `CodeChunk` - 向量化代码块
- `App` - 应用 Atlas 数据
- `State` - UI 状态快照

**关系类型**：
- `(Directory)-[:CONTAINS]->(Directory/File)`
- `(Directory)-[:DEPENDS_ON]->(Directory)`

**清理影响**：
- ⚠️ 代码库索引需要重新构建
- ⚠️ Atlas 学习数据会丢失（除非使用 `--keep-apps`）

**命令**：
```bash
# 清理文件索引
python scripts/cleanup_system.py --neo4j

# 保留 Atlas 应用数据
python scripts/cleanup_system.py --neo4j --keep-apps
```

---

### 3. Neo4j 记忆 (`--memory`)

**存储位置**：`bolt://localhost:7687`

**数据内容**：
- `Concept` - 知识概念（语义记忆）
- `Episode` - 执行历史（情景记忆）
- `Preference` - 用户偏好
- `User` - 用户实体

**向量索引**：
- `concept_embeddings` - 概念向量索引
- `episode_embeddings` - 片段向量索引

**关系类型**：
- `(Episode)-[:RELATED_TO]->(Concept)`
- `(User)-[:PREFERS]->(Preference)`
- `(Concept)-[:REFERENCES]->(File)`

**清理影响**：
- ⚠️ 所有学习到的概念丢失
- ⚠️ 执行历史经验丢失
- ⚠️ 用户偏好设置丢失

**命令**：
```bash
python scripts/cleanup_system.py --memory
```

---

### 4. PostgreSQL 技能表 (`--skills`)

**数据表**：
- `learned_skills` - 学习到的技能
- `trace_events` - 执行追踪事件
- `router_training_data` - 意图路由训练数据

**清理影响**：
- ⚠️ 所有自动化技能丢失
- ⚠️ 执行追踪数据丢失
- ⚠️ 意图路由示例丢失

**命令**：
```bash
python scripts/cleanup_system.py --skills
```

---

### 5. PostgreSQL 文件索引表 (`--index`)

**数据表**：
- `code_chunks` - 向量化代码块
- `code_relations` - 代码实体关系
- `code_entities` - 代码符号实体
- `source_files` - 源文件索引
- `repositories` - Git 仓库元数据
- `tools` - 工具嵌入

**清理影响**：
- ⚠️ 代码向量索引丢失
- ⚠️ 需要重新运行代码索引

**命令**：
```bash
python scripts/cleanup_system.py --index
```

---

### 6. PostgreSQL 消息表 (`--messages`)

**数据表**：
- `messages` - 聊天消息
- `conversations` - 会话线程

**清理影响**：
- ⚠️ 所有历史对话丢失
- ✅ 不影响其他功能

**命令**：
```bash
python scripts/cleanup_system.py --messages
```

---

### 7. 截图存储 (`--screenshots`)

**存储位置**：`~/.evoloop/artifacts/screenshots/`

**目录结构**：
```
screenshots/
├── temp/{date}/          # 临时截图（1天保留期）
├── atlas/{bundle_id}/{date}/  # Atlas 学习截图（90天）
├── debug/{date}/         # 调试截图（7天）
└── dataset/{date}/       # 数据集截图（365天）
```

**清理影响**：
- ✅ 可以安全清理临时截图
- ⚠️ 数据集截图用于训练，谨慎清理

**命令**：
```bash
# 清理所有截图
python scripts/cleanup_system.py --screenshots

# 仅清理过期截图
python scripts/cleanup_system.py --expired-only --screenshots
```

---

### 8. 屏幕录制 (`--recordings`)

**存储位置**：`~/.evoloop/artifacts/recordings/`

**目录结构**：
```
recordings/
├── {date}/               # 录制视频文件
└── frames/{session_id}/  # 提取的视频帧
```

**保留策略**：
- 保留期：30天
- 总容量限制：10GB

**清理影响**：
- ⚠️ 录制数据用于训练，谨慎清理

**命令**：
```bash
# 清理所有录制
python scripts/cleanup_system.py --recordings

# 仅清理过期录制
python scripts/cleanup_system.py --expired-only --recordings
```

---

### 9. 知识库 (`--knowledge`)

**存储位置**：`~/.evoloop/library/`

**内容**：
- Markdown 文件
- 技能定义文件
- 全局知识库文档

**注意**：语义知识（Concept 节点）存储在 Neo4j 中，需要使用 `--memory` 清理。

**命令**：
```bash
python scripts/cleanup_system.py --knowledge
```

---

### 10. Skills (`--skills`)

**存储位置**：`~/.evoloop/skills/`

**数据来源**：
- **内置技能**：`app/core/learning/skills/` → 复制到 `~/.evoloop/skills/`
- **用户技能**：直接在 `~/.evoloop/skills/` 中创建或通过 API 导入

**目录结构**：
```
~/.evoloop/skills/
├── os/
│   ├── macos/
│   │   ├── click/
│   │   │   └── SKILL.md
│   │   └── copy/
│   │       └── SKILL.md
│   └── windows/
├── browser/
│   └── navigation/
│       └── SKILL.md
└── misc/
    └── custom_skill/
        └── SKILL.md
```

**数据内容**：
- 物理技能文件（SKILL.md）
- 每个技能是一个包含 SKILL.md 的文件夹

**清理影响**：
- ⚠️ 所有技能文件将被删除
- ⚠️ 数据库中的技能记录也会被清理
- ✅ 下次启动时会重新复制内置技能

**命令**：
```bash
python scripts/cleanup_system.py --skills
```

---

### 11. Brain Memory (`--brain`)

**存储位置**：`~/.evoloop/memory/`

**目录结构**：
```
~/.evoloop/memory/
├── sys/                  # 系统文件
│   ├── identity.md
│   ├── tools.md
│   └── rules.md
├── working/              # 工作记忆
│   ├── current_task.md
│   └── scratchpad.md
├── knowledge/projects/   # 项目知识
├── knowledge/users/      # 用户知识
└── logs/                 # 执行日志
```

**命令**：
```bash
python scripts/cleanup_system.py --brain
```

---

## 故障排除

### Redis 连接失败

**错误信息**：
```
⚠️  Redis not available: Cannot connect to Redis
```

**解决方案**：
```bash
# 启动 Redis 服务
redis-server

# 或检查 Redis 配置
cat ../.env | grep REDIS_URL
```

---

### Neo4j 连接失败

**错误信息**：
```
⚠️  Neo4j not available: Cannot connect to Neo4j
```

**解决方案**：
```bash
# 启动 Neo4j 服务
neo4j start

# 检查 Neo4j 配置
cat ../.env | grep NEO4J
```

---

### PostgreSQL 连接失败

**错误信息**：
```
⚠️  PostgreSQL not available: Cannot connect to database
```

**解决方案**：
```bash
# 检查 PostgreSQL 服务
pg_isready

# 检查数据库配置
cat ../.env | grep POSTGRES
```

---

### 权限错误

**错误信息**：
```
❌ Failed to delete file: Permission denied
```

**解决方案**：
```bash
# 检查文件权限
ls -la ~/.evoloop/artifacts/

# 修复权限
sudo chown -R $(whoami) ~/.evoloop/
```

---

## 安全建议

### 1. 始终先使用干运行模式

在实际清理之前，先预览将要删除的内容：

```bash
python scripts/cleanup_system.py --dry-run --all
```

### 2. 使用确认参数

对于重要数据，使用 `--confirm` 参数：

```bash
python scripts/cleanup_system.py --memory --confirm
```

### 3. 避免在生产环境使用 `--all`

生产环境应该针对性地清理：

```bash
# 好：只清理过期的临时文件
python scripts/cleanup_system.py --expired-only --screenshots

# 危险：清理所有数据
python scripts/cleanup_system.py --all  # 不要在生产环境使用！
```

### 4. 备份重要数据

在执行大规模清理之前，备份关键数据：

```bash
# 备份 Neo4j
neo4j-admin dump --to=neo4j-backup.dump

# 备份 PostgreSQL
pg_dump evoloop > postgres-backup.sql

# 备份文件
rsync -av ~/.evoloop/ ~/evoloop-backup/
```

### 5. 定期清理过期数据

设置定时任务定期清理过期数据：

```bash
# 添加到 crontab
crontab -e

# 每天凌晨清理过期截图和录制
0 0 * * * cd /path/to/backend && python scripts/cleanup_system.py --expired-only --screenshots --recordings
```

---

## 完整命令参考

### 核选项（清理所有数据）

```bash
# 1. 预览
python scripts/cleanup_system.py --dry-run --all

# 2. 执行（需要输入 DELETE 确认）
python scripts/cleanup_system.py --all
```

### 日常维护

```bash
# 清理过期临时文件
python scripts/cleanup_system.py --expired-only --screenshots --recordings

# 清理 Redis 缓存
python scripts/cleanup_system.py --redis

# 清理旧消息
python scripts/cleanup_system.py --messages
```

### 重新索引代码库

```bash
# 1. 清理文件索引
python scripts/cleanup_system.py --neo4j --index

# 2. 重新运行索引任务
# （根据项目实际情况执行索引命令）
```

### 重置技能系统

```bash
# 清理所有技能相关数据
python scripts/cleanup_system.py --skills --memory
```

---

## 附录

### 相关文件

- 清理脚本：`backend/scripts/cleanup_system.py`
- 知识库维护：`backend/app/domain/knowledge/maintenance.py`
- 截图存储：`backend/app/core/vision/storage.py`
- Redis 配置：`backend/app/infrastructure/database/redis.py`
- Neo4j 配置：`backend/app/infrastructure/database/graph/driver.py`

### 版本信息

- 文档版本：1.0
- 最后更新：2026-03-02
- 兼容版本：EvoLoop v5+
