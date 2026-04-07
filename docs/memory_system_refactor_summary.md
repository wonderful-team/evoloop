# EvoLoop Memory System 重构方案 - 执行摘要

## 概述

本文档是基于 EvoLoop 和 Claude Code 记忆系统分析设计的完整重构方案。

## 核心问题

### 当前架构问题

| 组件 | 嵌入式模式 | 问题 |
|------|-----------|------|
| LongTerm | ❌ NoOp (空操作) | 长期记忆完全失效 |
| Preferences | ❌ NoOp (空操作) | 用户偏好无法保存 |
| Graph | ❌ NoOp (空操作) | 图导航不可用 |
| Brain | ✅ FileSystem | 与 Memory 系统重复 |

**75% 的 Memory 接口在嵌入式模式下是空操作！**

## 重构方案

### 目标架构

```
MemoryManager (统一门面)
├── ShortTermManager (原 SqlShortTermMemory)
│   └── SQLite/PostgreSQL 存储对话历史
│
├── LongTermManager (新，替代 Brain + NoOp)
│   ├── MemoryTypeSystem (四类型分类)
│   │   ├── user: 用户画像（私有）
│   │   ├── feedback: 反馈指导（可团队共享）
│   │   ├── project: 项目上下文（团队）
│   │   └── reference: 外部引用（团队）
│   │
│   ├── StorageBackends (多后端支持)
│   │   ├── FileBackend (嵌入式): ~/.evoloop/memory/
│   │   └── Neo4jBackend (完整模式): 图数据
│   │
│   ├── AutoExtraction (对话结束后自动提取)
│   └── Retrieval (LLM 相关性选择)
│
└── ConsolidationService (定时整理)
```

### 关键改进

1. **统一架构**：消除 Memory 和 Brain 的重复
2. **功能完整**：嵌入式模式下长期记忆基于文件存储，完全可用
3. **四类型分类**：借鉴 Claude Code 的设计
4. **自动提取**：对话结束后自动分析保存
5. **智能检索**：LLM 辅助选择相关记忆

## 文件存储格式

```yaml
# ~/.evoloop/memory/private/user-profile.md
---
id: "mem_user_001"
type: "user"
privacy: "private"
title: "用户编码偏好"
created_at: "2026-04-01T15:30:00Z"
version: 1
tags: ["preferences", "python"]
source: "extracted"
confidence: 0.95
---

## Python 编码风格偏好

用户偏好以下 Python 代码风格：
1. 使用双引号而非单引号
2. 遵循 PEP 8 规范
3. 优先使用类型注解
```

## 目录结构

```
~/.evoloop/memory/
├── MEMORY.md              # 索引文件
├── private/               # 私有记忆
│   ├── user-profile.md
│   ├── feedback/
│   │   └── 2026-04-02-*.md
│   └── preferences.md
└── team/                  # 团队共享记忆
    ├── project-{id}/
    │   ├── architecture.md
    │   └── decisions.md
    └── reference/
        ├── libraries.md
        └── best-practices.md
```

## 实施计划

### Phase 1: 基础建设（1-2 周）
- 创建 memory_v2 模块
- 实现 FileBackend
- 实现核心模型和接口
- 编写单元测试

### Phase 2: 功能实现（2-3 周）
- 实现自动提取服务
- 实现智能检索
- 实现向后兼容层
- 集成测试

### Phase 3: 逐步迁移（1-2 周）
- 新增代码使用 v2 接口
- 监控和修复问题
- 性能优化
- 文档更新

### Phase 4: 最终切换（1 周）
- 切换默认实现到 v2
- 保留 v1 作为兼容层
- 清理废弃代码
- 发布说明

**总时间估算：5-8 周**

## 向后兼容

```python
# 通过配置切换
if settings.USE_MEMORY_V2:
    from app.core.memory_v2.manager import MemoryManager
else:
    from app.core.memory.manager import MemoryManager

# v1 接口保持不变
await memory_manager.store_concept(concept)  # 内部转发到 v2
await memory_manager.search_concepts(query)  # 内部转发到 v2
```

## 优先级

| 功能 | 优先级 | 预估时间 |
|------|--------|----------|
| FileBackend | P0 | 3 天 |
| MemoryEntry 模型 | P0 | 1 天 |
| 向后兼容层 | P0 | 2 天 |
| 自动提取 | P1 | 5 天 |
| 智能检索 | P1 | 5 天 |
| 索引系统 | P1 | 3 天 |
| 数据迁移工具 | P2 | 2 天 |

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 向后兼容问题 | 中 | 高 | 保持 v1 接口，逐步切换 |
| 性能下降 | 低 | 中 | 实现缓存层，异步索引更新 |
| 数据丢失 | 低 | 高 | 迁移前备份，提供回滚方案 |

## 文件清单

### 设计方案
- `memory_system_refactor_design.md` - 完整设计方案
- `memory_system_refactor_summary.md` - 本摘要

### 示例代码
- `memory_v2_examples/models.py` - 数据模型
- `memory_v2_examples/file_backend.py` - 文件后端实现
- `memory_v2_examples/manager.py` - MemoryManager 实现
- `memory_v2_examples/extraction.py` - 自动提取服务
- `memory_v2_examples/migration.py` - 迁移脚本
- `memory_v2_examples/config.py` - 配置示例

### 示例记忆文件
- `memory_v2_examples/sample_memory_files/MEMORY.md` - 索引文件
- `memory_v2_examples/sample_memory_files/private/user-profile.md` - 用户偏好示例
- `memory_v2_examples/sample_memory_files/private/feedback/*.md` - 反馈示例
- `memory_v2_examples/sample_memory_files/team/project-1/*.md` - 项目记忆示例
- `memory_v2_examples/sample_memory_files/team/reference/*.md` - 引用示例

## 下一步行动

1. [ ] 创建 feature branch: `feature/memory-v2`
2. [ ] 实现基础模型和 FileBackend
3. [ ] 编写单元测试
4. [ ] 实现向后兼容层
5. [ ] 内部测试和 review
6. [ ] 逐步迁移现有代码

## 参考

- Claude Code 记忆系统设计
- EvoLoop 现有架构分析
- Python 最佳实践
