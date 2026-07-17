# Graph 层移除 — 回归测试验证计划

## 1. 修改范围概览

| 操作 | 模块 | 风险等级 |
|------|------|----------|
| **删除** | `infrastructure/database/graph/`（Neo4j 驱动 + 管理器） | 低 — 无消费者 |
| **删除** | `retrieval/graph_service.py` | 中 — 被 tools.py / engine.py 调用 |
| **删除** | `indexing/components/graph_syncer.py` | 高 — 索引管道的核心环节 |
| **删除** | `indexing/garbage_collector.py` | 低 — 仅维护流程使用 |
| **删除** | `atlas/adapters/graph_store.py` | 高 — Atlas 存储的全部数据 |
| **重写** | `retrieval/service.py` | 高 — 新增 6 个 SQL 方法 |
| **重写** | `retrieval/tools.py` | 高 — 搜索代码、查询图谱工具 |
| **重写** | `exploration/engine.py` | 中 — find_symbol / analyze_impact |
| **重写** | `indexing/service.py` | 高 — 移除 GraphSyncer 调用 |
| **重写** | `indexing/directory_summarizer.py` | 中 — SQL + JSON 文件替代图谱查询 |
| **重写** | `knowledge/ontology_builder.py` | 中 — SQL JOIN 替代 Cypher |
| **重写** | `knowledge/maintenance.py` | 中 — 移除图清理逻辑 |
| **重写** | `core/project/summarizer.py` | 低 — 仅移除 graph_db 参数 |
| **重写** | `atlas/engine.py` + `sql_store.py` | 高 — 存储后端从图切换为 SQL |
| **新增** | `models/atlas.py`（SQL ORM 模型） | 中 — Atlas 数据模型 |
| **修改** | `api/routes/projects.py` | 低 — 删除图清理分支 |
| **修改** | `infrastructure/config/embedding.py` | 低 — 删除 Neo4j 迁移 |

---

## 2. 测试用例清单

### P0 — 核心功能回归（阻断级）

| # | 测试名称 | 覆盖模块 | 说明 |
|---|----------|----------|------|
| R01 | 索引文件后 SQL 数据一致 | indexing/service, SQLPersister | 验证 `index_file` 后 code_entity/code_relation/code_chunk 表正确写入 |
| R02 | 索引仓库全流程 | indexing/manager, service | 完整索引流水线：提取 → 嵌入 → SQL 持久化 → 目录摘要 → 项目摘要 |
| R03 | 搜索代码库工具 | retrieval/tools, service | `search_codebase` 调用 find_symbol_definition / find_usages / search 正确路由 |
| R04 | 查询图谱自然语言工具 | retrieval/tools, service | `query_graph_natural_language` 调用 multi_entity_query 正确返回 |
| R05 | 符号查找 | exploration/engine, service | `find_symbol` 通过 SQL 找到定义并回退到 FileSearcher |
| R06 | 影响分析 | exploration/engine, service | `analyze_impact` 通过 SQL 找到引用关系 |
| R07 | 删除项目清理 | api/projects, maintenance | 删除项目后 SQL 表和向量数据一并清除 |
| R08 | Atlas 保存应用模型 | atlas/sql_store | `save_app_model` 正确写入 atlas_apps/states/transitions 表 |
| R09 | Atlas 查询应用摘要 | atlas/engine, sql_store | `query_app_atlas` 正确返回状态图 |
| R10 | Atlas 清除数据 | atlas/engine, sql_store | `clear_all_data` 清空所有 Atlas 表 |

### P1 — 重要功能回归

| # | 测试名称 | 覆盖模块 | 说明 |
|---|----------|----------|------|
| R11 | ontology 构建 | knowledge/ontology_builder | SQL JOIN 生成 directory_dependencies.json 正确 |
| R12 | wipe_knowledge_base | knowledge/maintenance | SQL TRUNCATE + 向量清空 |
| R13 | 目录摘要生成 | indexing/directory_summarizer | SQL 查询后 JSON 文件写入正确 |
| R14 | 文件移动/重命名 | indexing/service | remove + reindex 流程正确 |
| R15 | 文件删除 | indexing/service | SQL 清理 + 向量删除 |
| R16 | Atlas 状态细节查询 | atlas/sql_store | `get_state_detail` 返回正确元素数据 |
| R17 | Atlas 转换摘要查询 | atlas/sql_store | `get_transitions_summary` 返回正确转换列表 |
| R18 | 多层实体查询 AND 条件 | retrieval/service | `multi_entity_query` 多条件过滤正确 |
| R19 | 多层实体查询 OR 条件 | retrieval/service | `multi_entity_query` OR 条件过滤正确 |
| R20 | 调用层级递归查询 | retrieval/service | `get_call_hierarchy` CTE 递归正确 |

### P2 — 边界/异常

| # | 测试名称 | 覆盖模块 | 说明 |
|---|----------|----------|------|
| R21 | 符号查找未找到 | retrieval/service / engine | 返回空结果，回退 FileSearcher |
| R22 | 空仓库索引 | indexing/service | 无文件时索引不报错 |
| R23 | Atlas 空应用列表 | atlas/sql_store | 无数据时 list_apps 返回空列表 |
| R24 | 重复索引（幂等性） | indexing/service | 两次索引同一文件数据一致 |
| R25 | 搜索空关键词 | retrieval/tools | 空/None 参数不崩溃 |
| R26 | 嵌入配置切换 | config/embedding | 切换模型后不再触发 Neo4j 迁移 |

---

## 3. 详细测试方案

### R01: 索引文件后 SQL 数据一致

**前置条件**:
- PostgreSQL 数据库已初始化
- 向量存储可用
- 项目目录存在且包含一个有效代码文件（如 `test.py`）

**步骤**:
1. 调用 `IndexingService.index_file(file_path, repo_id, session)`
2. 从 `code_entities` 查询实体记录
3. 从 `code_relations` 查询关系记录
4. 从 `code_chunks` 查询块记录

**预期结果**:
- `code_entities` 表中存在对应的函数/类/变量实体
- `code_relations` 表中存在对应的调用/继承/包含关系
- `code_chunks` 表中存在至少一个代码块
- 所有记录的 `repository_id` 与输入的 repo_id 一致

**Mock 策略**: 使用真实 PostgreSQL（测试数据库）+ 真实向量存储

---

### R02: 索引仓库全流程

**前置条件**: 同上，项目目录包含多层目录和多个代码文件

**步骤**:
1. 调用 `IndexingManager.trigger_full_index_repo(repo_id, project_root)`
2. 等待流水线完成
3. 验证 SQL 表数据完整
4. 验证 `.evoloop/directory_summaries/` 下生成了摘要 JSON
5. 验证 `.evoloop/project.json` 文件存在

**预期结果**:
- 流水线不抛出异常
- SQL 数据完整
- 摘要 JSON 包含目录结构描述
- 项目摘要包含 LLM 生成的描述文本
- GraphSyncer 相关代码未被调用（可 mock 检测）

---

### R03: 搜索代码库工具

**前置条件**: SQL 中有预置的实体数据（`search_codebase` 的调用包含了符号查找）

**步骤**:
1. 使用已知符号名调用 `search_codebase(query="test_function", search_type="hybrid")`
2. 使用未知符号名调用
3. 使用类名调用（请求关系）

**预期结果**:
- 找到符号定义时返回实体详情和代码片段
- 未找到时返回空结果（无崩溃）
- 包含关系数据时正确返回关联的调用者/被调用者

---

### R04: 查询图谱自然语言工具

**前置条件**: SQL 中有跨文件的多实体和关系

**步骤**:
1. 调用 `query_graph_natural_language("find all functions called by main")`
2. 调用 `query_graph_natural_language("find classes that inherit from BaseModel")`

**预期结果**:
- `multi_entity_query` 被正确调用
- 返回匹配的实体列表，包含文件位置和关系
- 不再调用 Neo4j/Cypher

---

### R05: 符号查找（engine.py）

**前置条件**: SQL 中有函数 `calculate_total` 的定义

**步骤**:
1. 调用 `engine.find_symbol("calculate_total")`
2. 当 SQL 找到定义时返回符号位置
3. 当 SQL 未找到时触发 FileSearcher 回退

**预期结果**:
- SQL 找到时返回 `(file_path, line_number)` + 代码上下文
- SQL 未找到时通过 FileSearcher 在文件系统中搜索
- 不再调用 graph_service

---

### R06: 影响分析

**前置条件**: `code_relations` 中有对 `calculate_total` 的调用记录

**步骤**:
1. 调用 `engine.analyze_impact("calculate_total")`

**预期结果**:
- 返回调用 `calculate_total` 的调用者列表（文件名 + 行号 + 代码行）
- 使用 `RetrievalService.find_usages()` 通过 `CodeRelation.target_entity_id` 查询

---

### R07: 删除项目清理

**前置条件**: 已索引的项目，SQL 和向量存储中均有数据

**步骤**:
1. 调用 `delete_project(project_id)`
2. 查询 SQL 表（code_entities/relations/chunks）中该项目的数据
3. 查询向量存储中该项目的数据

**预期结果**:
- 该项目所有 SQL 记录被删除
- 该项目所有向量数据被删除
- 其他项目数据不受影响
- 不再调用 graph 清理代码

---

### R08–R10: Atlas SQL 存储

**前置条件**: PostgreSQL 已初始化 atlas 表

**步骤**:
- R08: `store.save_app_model(app_model)` → 插入 atlas_apps + atlas_states + atlas_transitions
- R09: `store.get_app_summary(app_name)` + `store.get_state_detail(package, state_name)` → 返回正确数据
- R10: `store.clear_all_data()` → 三个表均清空

**预期结果**:
- 支持 upsert（同一 app 多次保存更新而非重复）
- 外键关系正确（state.app_id → app.id, transition.from_state_id → state.id）
- 清空后 list_apps 为空

---

### R11: ontology 构建

**前置条件**: SQL 中有跨文件的关系数据

**步骤**:
1. 调用 `OntologyBuilder.build(repo_id)`
2. 读取输出的 `.evoloop/ontology/directory_dependencies.json`

**预期结果**:
- JSON 包含目录间依赖关系
- 依赖关系来自 `CodeRelation` 表 JOIN `CodeEntity` + `SourceFile`
- 每个条目包含 source 和 target 目录及关系数量

---

### R12: wipe_knowledge_base

**步骤**:
1. 调用 `wipe_knowledge_base()`
2. 查询 code_chunks/code_relations/code_entities/source_files/tools 表
3. 查询向量存储

**预期结果**:
- 所有 SQL 表被 TRUNCATE
- 向量存储被清空
- 不尝试连接 Neo4j

---

## 4. Mock / 测试基础设施建议

### 4.1 测试数据库

```python
# conftest.py 追加
@pytest.fixture
def db_session():
    """提供真实 PostgreSQL 测试 session，每次用例后回滚"""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()
```

### 4.2 预置数据夹具

```python
@pytest.fixture
def sample_entity(db_session):
    entity = CodeEntity(
        id=uuid4(),
        name="calculate_total",
        entity_type="function",
        file_path="/project/main.py",
        repository_id="repo_1",
        ...
    )
    db_session.add(entity)
    await db_session.commit()
    return entity
```

### 4.3 关键 Mock 点

| 需要 Mock 的模块 | 原因 | 替代方案 |
|------------------|------|----------|
| `get_vector_store()` | 向量存储依赖外部服务 | `unittest.mock.patch` 返回 MemoryStore |
| `llm_client` | 摘要/分类中调用 LLM | 返回预定义的 mock 响应 |
| `Settings` | 数据库连接配置 | 使用测试专用 `.env.test` |
| 文件系统操作 | 目录摘要写文件 | `tmp_path` fixture |
| Neo4j（残留） | 旧 conftest 仍 mock | 可安全保留，无功能影响 |

---

## 5. 测试执行顺序建议

```
Round 1: 单元测试（快速验证）
  R21 → R14 → R15 → R22 → R23 → R24 → R25 → R26

Round 2: 核心功能
  R01 → R02 → R08 → R09 → R10 → R20

Round 3: 业务功能
  R03 → R04 → R05 → R06 → R07 → R11 → R12 → R13

Round 4: Atlas 功能
  R16 → R17 → R18 → R19
```

---

## 6. 风险矩阵

| 区域 | 风险等级 | 影响 | 缓解措施 |
|------|----------|------|----------|
| 索引流水线中断 | **高** | 新增/修改代码无法索引 | R01, R02 必须通过 |
| 搜索/查询功能失效 | **高** | Agent 无法理解代码库 | R03, R04, R05, R06 必须通过 |
| Atlas 数据不可恢复 | **高** | UI 自动化不工作 | R08, R09, R10 必须通过 |
| 知识库清理不完整 | 中 | 脏数据累积 | R12 验证 |
| ontology 不准确 | 中 | 目录依赖丢失 | R11 验证 |
| 嵌入配置残留 Neo4j | 低 | 配置切换报错 | R26 验证 |
| 旧 conftest mock | 低 | 无功能影响 | 可选清理 |

---

## 7. 实施建议

1. **优先实现 R01–R10（P0）**：这些是阻断级回归点，有任何失败都意味着 graph 移除引入了 bug
2. **R01/R02 使用真实 PostgreSQL**：SQL 查询逻辑（特别是 CTE、JOIN）无法通过 mock 充分验证
3. **R08–R10 使用真实 PostgreSQL + SQLite 均可**：Atlas SQL 模型使用标准 SQLAlchemy ORM，SQLite 内存模式可加速测试
4. **R03/R04 需要 mock RetrievalService 和 hybrid_searcher**：关注工具路由逻辑而非底层搜索
5. **监控测试覆盖率**：目标是对所有重写方法实现 >80% 行覆盖率

---

*文档版本: 1.0*
*适用范围: Graph 层移除后的回归验证*
