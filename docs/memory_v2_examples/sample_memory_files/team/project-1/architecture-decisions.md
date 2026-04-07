---
id: mem_proj_001
type: project
privacy: team
title: EvoLoop 架构决策
created_at: '2026-03-28T09:15:00Z'
updated_at: '2026-04-02T14:00:00Z'
version: 2
tags:
- architecture
- design-decisions
- evoloop
source: manual
confidence: 1.0
project_id: 1
---

## EvoLoop 核心架构决策

### 1. 分层架构

```
API Layer (FastAPI)
    ↓
Engine Layer (LangGraph)
    ↓
Core Services (Memory, Tools, Learning)
    ↓
Infrastructure (Database, Queue, LLM)
```

### 2. 关键决策

#### 2.1 使用 LangGraph 作为编排引擎

**决策**：采用 LangGraph 而非自研状态机

**原因**：
- 支持复杂的循环和条件分支
- 内置持久化和断点恢复
- 与 LangChain 生态集成

**替代方案**：自研 DAG 引擎（已否决，维护成本高）

#### 2.2 双模式架构（Embedded vs Full）

**决策**：支持嵌入式模式（SQLite）和完整模式（PostgreSQL + Neo4j）

**考虑因素**：
- 嵌入式模式适合桌面应用
- 完整模式适合企业部署
- 统一抽象层隐藏差异

#### 2.3 记忆系统重构

**决策**：从 Brain + Memory 双系统改为统一的 MemoryManager

**动机**：
- 消除概念负担
- 嵌入式模式下长期记忆可用
- 借鉴 Claude Code 的分类方法

### 3. 技术栈

| 层级 | 技术 |
|------|------|
| API | FastAPI, WebSocket |
| 工作流 | LangGraph, LangChain |
| 数据库 | PostgreSQL / SQLite, Neo4j (可选) |
| 消息队列 | Celery, Redis |
| LLM | OpenAI, Anthropic, 本地模型 |

### 4. 待决策事项

- [ ] 是否支持多 Agent 协作
- [ ] 向量数据库选型（Pinecone vs Milvus vs pgvector）
