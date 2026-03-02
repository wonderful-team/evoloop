# EvoLoop 系统清理脚本

> **📖 完整文档**: 查看 [系统清理工具使用指南](../../docs/system_cleanup_guide.md) 获取更详细的说明。

## 概述

这是一个全面的系统清理工具，用于清理 EvoLoop 后端的各种存储组件，包括 Redis 缓存、Neo4j 图数据库、PostgreSQL 数据表和文件系统存储。

## 功能特性

### 支持的存储组件

| 组件 | 描述 | 位置 |
|------|------|------|
| **Redis** | 缓存和上下文数据 | `redis://localhost:6379/0` |
| **Neo4j Index** | 文件索引（代码库索引） | `bolt://localhost:7687` |
| **Neo4j Memory** | 记忆数据（概念、历史） | `bolt://localhost:7687` |
| **PostgreSQL** | 关系数据库 | `postgresql://localhost:5432/evoloop` |
| **Screenshots** | 截图存储 | `~/.evoloop/artifacts/screenshots/` |
| **Recordings** | 屏幕录制 | `~/.evoloop/artifacts/recordings/` |
| **Knowledge Base** | 知识库文件 | `~/.evoloop/library/` |
| **Skills** | 技能文件 | `~/.evoloop/skills/` |
| **Brain Memory** | 记忆文件 | `~/.evoloop/memory/` |

## 使用方法

### 基本用法

```bash
# 查看帮助
python scripts/cleanup_system.py --help

# 预览所有可清理的数据（干运行模式）
python scripts/cleanup_system.py --dry-run --all

# 清理所有数据（⚠️ 危险！）
python scripts/cleanup_system.py --all

# 带确认提示的清理
python scripts/cleanup_system.py --all --confirm
```

### 文件索引 vs 记忆的区分

| 类型 | 参数 | 存储位置 | 数据内容 |
|------|------|----------|----------|
| **文件索引** | `--neo4j` / `--index` | Neo4j: `File`, `Directory`, `CodeEntity`, `CodeChunk`<br>PG: `code_chunks`, `code_relations`, `source_files` | 代码库索引数据 |
| **记忆** | `--memory` | Neo4j: `Concept`, `Episode`, `Preference`, `User` | 长期记忆（概念、执行历史、偏好） |
| **知识库** | `--knowledge` | 文件: `~/.evoloop/library/` | Markdown文件、技能定义 |

**注意**：知识概念的语义数据（Concept 节点）存储在 Neo4j 中，使用 `--memory` 清理；而 `--knowledge` 只清理文件系统中的知识库文件。

### 选择性清理

```bash
# 仅清理 Redis
python scripts/cleanup_system.py --redis

# 仅清理技能数据
python scripts/cleanup_system.py --skills

# 仅清理记忆（概念、执行历史、用户偏好）
python scripts/cleanup_system.py --memory

# 清理文件索引但保留 Atlas 应用数据
python scripts/cleanup_system.py --neo4j --keep-apps

# 清理 Redis + 文件索引 + 技能
python scripts/cleanup_system.py --redis --neo4j --skills

# 清理文件索引和向量存储
python scripts/cleanup_system.py --index

# 清理消息和会话
python scripts/cleanup_system.py --messages
```

### 过期数据清理

```bash
# 仅清理过期的截图（按保留策略）
python scripts/cleanup_system.py --expired-only --screenshots

# 仅清理过期的录制
python scripts/cleanup_system.py --expired-only --recordings

# 清理所有过期文件
python scripts/cleanup_system.py --expired-only --screenshots --recordings
```

### 高级选项

```bash
# 清理 Neo4j 但保留 Atlas 应用数据
python scripts/cleanup_system.py --neo4j --keep-apps

# 干运行模式查看将要删除的内容
python scripts/cleanup_system.py --dry-run --redis --skills --index
```

## 存储架构详解

### 1. Redis 缓存

**键模式：**
- `evo:context:{thread_id}` - 线程执行上下文
- `evo:intent_cache:{hash}` - 意图匹配缓存（300秒TTL）
- `system:dynamic_apps:{platform}` - 动态应用分类
- `system:processed_apps:{platform}` - 已处理应用追踪
- `system:app_categorization:{platform}` - 应用推理数据

**清理命令：**
```bash
python scripts/cleanup_system.py --redis
```

### 2. Neo4j 图数据库

#### 2.1 文件索引 (--neo4j)

**节点类型（代码库索引）：**
- `File` - 文件引用
- `Directory` - 目录结构
- `CodeEntity` - 代码符号/实体
- `CodeChunk` - 向量化代码块
- `App` - 应用 Atlas 数据（可选保留）
- `State` - UI 状态快照（可选保留）

**关系类型：**
- `(Directory)-[:CONTAINS]->(Directory/File)`
- `(Directory)-[:DEPENDS_ON]->(Directory)`
- `(File)-[:HAS_ENTITY]->(CodeEntity)`

**清理命令：**
```bash
# 清理文件索引
python scripts/cleanup_system.py --neo4j

# 清理但保留 Atlas 应用数据
python scripts/cleanup_system.py --neo4j --keep-apps
```

#### 2.2 记忆 (--memory)

**节点类型（长期记忆）：**
- `Concept` - 知识概念（语义记忆）
- `Episode` - 执行历史（情景记忆）
- `Preference` - 用户偏好
- `User` - 用户实体

**关系类型：**
- `(Episode)-[:RELATED_TO]->(Concept)`
- `(User)-[:PREFERS]->(Preference)`
- `(Concept)-[:REFERENCES]->(File)`

**向量索引：**
- `concept_embeddings` - 概念嵌入（768维）
- `episode_embeddings` - 片段嵌入（768维）

**清理命令：**
```bash
python scripts/cleanup_system.py --memory
```

### 3. PostgreSQL 数据表

#### 技能相关表和文件
**数据库表：**
- `learned_skills` - 学习到的技能
- `trace_events` - 执行追踪事件
- `router_training_data` - 意图路由训练数据

**技能文件：**
- **位置**：`~/.evoloop/skills/`
- **来源**：内置技能从 `app/core/learning/skills/` 复制
- **结构**：每个技能是一个包含 `SKILL.md` 的文件夹

**清理命令：**
```bash
python scripts/cleanup_system.py --skills
```

#### 文件索引表
- `code_chunks` - 向量化代码块
- `code_relations` - 代码实体关系
- `code_entities` - 代码符号实体
- `source_files` - 源文件索引
- `repositories` - Git 仓库元数据
- `tools` - 工具嵌入

**清理命令：**
```bash
python scripts/cleanup_system.py --index
```

#### 会话相关表
- `messages` - 聊天消息
- `conversations` - 会话线程

**清理命令：**
```bash
python scripts/cleanup_system.py --messages
```

#### 任务队列表
- `jobs` - 后台任务队列

**清理命令：**
```bash
python scripts/cleanup_system.py --jobs
```

### 4. 截图存储

**目录结构：**
```
~/.evoloop/artifacts/screenshots/
├── temp/{date}/          # 临时截图（1天保留期）
├── atlas/{bundle_id}/{date}/  # Atlas 学习截图（90天）
├── debug/{date}/         # 调试截图（7天）
└── dataset/{date}/       # 数据集截图（365天）
```

**清理命令：**
```bash
# 清理所有截图
python scripts/cleanup_system.py --screenshots

# 仅清理过期截图
python scripts/cleanup_system.py --expired-only --screenshots
```

### 5. 屏幕录制

**目录结构：**
```
~/.evoloop/artifacts/recordings/
├── {date}/               # 录制视频文件
└── frames/{session_id}/  # 提取的视频帧
```

**保留策略：**
- 保留期：30天
- 总容量限制：10GB
- 单次最大时长：10分钟
- 单次最大大小：500MB

**清理命令：**
```bash
# 清理所有录制
python scripts/cleanup_system.py --recordings

# 仅清理过期录制
python scripts/cleanup_system.py --expired-only --recordings
```

### 6. 知识库

知识库数据存储在两个位置：

#### 6.1 语义知识（Neo4j）
- **位置**：Neo4j 图数据库的 `Concept` 节点
- **内容**：知识概念、概念之间的关联、概念引用文件的关联
- **清理**：使用 `--memory` 参数（Concept 属于记忆系统）

#### 6.2 文件知识库（文件系统）
- **位置**：`~/.evoloop/library/`
- **内容**：Markdown 文件、技能定义、文档等全局知识库文件
- **清理**：使用 `--knowledge` 参数

**完整清理知识库：**
```bash
# 清理文件知识库
python scripts/cleanup_system.py --knowledge

# 清理语义知识（Concept 节点）
python scripts/cleanup_system.py --memory

# 同时清理两者
python scripts/cleanup_system.py --knowledge --memory
```

### 7. Brain Memory

**位置：** `~/.evoloop/memory/`

**目录结构：**
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

**清理命令：**
```bash
python scripts/cleanup_system.py --brain
```

## 完整重置（核选项）

⚠️ **警告：这将删除所有数据，不可恢复！**

```bash
# 1. 预览将要删除的内容
python scripts/cleanup_system.py --dry-run --all

# 2. 执行完整清理
python scripts/cleanup_system.py --all

# 3. 输入 DELETE 确认
```

## 环境要求

- Python 3.11+
- Redis 连接（可选）
- Neo4j 连接（可选）
- PostgreSQL 连接（可选）

## 故障排除

### Redis 连接失败
```
⚠️  Redis not available: Cannot connect to Redis
```
**解决：** 确保 Redis 服务正在运行：`redis-server`

### Neo4j 连接失败
```
⚠️  Neo4j not available: Cannot connect to Neo4j
```
**解决：** 确保 Neo4j 服务正在运行：`neo4j start`

### PostgreSQL 连接失败
```
⚠️  PostgreSQL not available: Cannot connect to database
```
**解决：** 检查 `.env` 文件中的数据库连接配置

## 安全建议

1. **始终在干运行模式下预览**：`--dry-run`
2. **备份重要数据**后再执行清理
3. **使用 `--confirm`** 在删除前获得确认提示
4. **不要清理生产环境**除非完全了解后果

## 相关文件

- 清理脚本：`backend/scripts/cleanup_system.py`
- 知识库维护：`backend/app/domain/knowledge/maintenance.py`
- 截图存储：`backend/app/core/vision/storage.py`
- Redis 配置：`backend/app/infrastructure/database/redis.py`
- Neo4j 配置：`backend/app/infrastructure/database/graph/driver.py`
