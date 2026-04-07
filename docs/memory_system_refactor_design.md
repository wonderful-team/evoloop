# EvoLoop Memory System 重构设计方案

## 1. 执行摘要

### 1.1 当前架构问题

| 组件 | 嵌入式模式 | 完整模式 |
|------|-----------|---------|
| ShortTerm | ✅ SqlShortTermMemory | ✅ SqlShortTermMemory |
| LongTerm | ❌ NoOp (空操作) | ✅ Neo4jLongTermMemory |
| Preferences | ❌ NoOp (空操作) | ✅ Neo4jPreferenceStore |
| Graph | ❌ NoOp (空操作) | ✅ Neo4jGraphNavigator |
| Brain | ✅ FileSystem (活跃) | ✅ FileSystem (活跃) |

**核心问题：**
1. **重复架构**：Memory 和 Brain 两个独立系统
2. **功能割裂**：嵌入式模式下长期记忆完全失效
3. **概念负担**：开发者需理解两套 API
4. **NoOp 泛滥**：75% 的 Memory 接口在嵌入式模式下无实际功能

### 1.2 重构目标

借鉴 Claude Code 记忆系统的设计，实现：
- **统一架构**：单一 MemoryManager 门面
- **功能完整**：嵌入式模式下长期记忆可用（基于文件）
- **四类型分类**：user/feedback/project/reference
- **自动提取**：对话结束后自动分析保存
- **智能检索**：LLM 选择相关记忆

---

## 2. 目标架构设计

### 2.1 整体架构

```
MemoryManager (统一门面)
├── ShortTermManager (原 SqlShortTermMemory)
│   └── SQLite/PostgreSQL 存储对话历史
│
├── LongTermManager (新，替代 Brain + NoOp)
│   ├── MemoryTypeSystem (借鉴 Claude Code)
│   │   ├── user: 用户画像（私有）
│   │   ├── feedback: 反馈指导（可团队共享）
│   │   ├── project: 项目上下文（团队）
│   │   └── reference: 外部引用（团队）
│   │
│   ├── StorageBackends (多后端支持)
│   │   ├── FileBackend (嵌入式): ~/.evoloop/memory/
│   │   │   ├── MEMORY.md (索引)
│   │   │   ├── private/ (user, feedback)
│   │   │   └── team/ (project, reference)
│   │   └── Neo4jBackend (完整模式): 图数据
│   │
│   ├── AutoExtraction (借鉴 extractMemories)
│   │   └── 对话结束后自动提取记忆
│   │
│   └── Retrieval (借鉴 findRelevantMemories)
│       ├── 索引扫描
│       ├── LLM 相关性选择
│       └── 上下文注入
│
└── ConsolidationService (原 MemoryConsolidator)
    ├── 定时整理工作记忆到长期记忆
    └── 摘要生成
```

### 2.2 核心设计决策

#### 2.2.1 数据格式统一

```yaml
# 文件后端: Markdown + YAML Frontmatter
# 路径: ~/.evoloop/memory/private/user-profile.md
---
id: "mem_001"
type: "user"  # user | feedback | project | reference
privacy: "private"  # private | team
created_at: "2026-04-02T10:00:00Z"
updated_at: "2026-04-02T10:00:00Z"
version: 1
tags: ["preferences", "coding-style"]
source: "extracted"  # extracted | manual | imported
confidence: 0.95  # 提取置信度
---

# 内容部分（Markdown 格式）
用户偏好 Python 代码风格：
- 使用双引号而非单引号
- 遵循 PEP 8 规范
- 优先使用类型注解
```

#### 2.2.2 类型系统（借鉴 Claude Code）

| 类型 | 隐私级别 | 用途 | 示例 |
|------|---------|------|------|
| `user` | private | 用户画像、偏好 | 编码风格、常用框架 |
| `feedback` | private/team | 反馈指导 | "不要修改测试文件" |
| `project` | team | 项目上下文 | 架构决策、技术栈 |
| `reference` | team | 外部引用 | 文档链接、最佳实践 |

---

## 3. 详细接口设计

### 3.1 核心数据模型

```python
# app/core/memory_v2/models.py
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """四类型记忆分类（借鉴 Claude Code）"""
    USER = "user"           # 用户画像（私有）
    FEEDBACK = "feedback"   # 反馈指导（可团队共享）
    PROJECT = "project"     # 项目上下文（团队）
    REFERENCE = "reference" # 外部引用（团队）


class PrivacyLevel(str, Enum):
    """隐私级别"""
    PRIVATE = "private"  # 仅用户可见
    TEAM = "team"        # 团队成员可见


class MemorySource(str, Enum):
    """记忆来源"""
    EXTRACTED = "extracted"  # LLM 自动提取
    MANUAL = "manual"        # 用户手动添加
    IMPORTED = "imported"    # 外部导入
    CONSOLIDATED = "consolidated"  # 整理生成


class MemoryEntry(BaseModel):
    """统一的记忆条目模型"""
    id: str = Field(default_factory=generate_memory_id)
    type: MemoryType
    privacy: PrivacyLevel
    
    # 内容
    title: str
    content: str
    
    # 元数据
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    version: int = 1
    tags: list[str] = Field(default_factory=list)
    
    # 来源信息
    source: MemorySource = MemorySource.EXTRACTED
    confidence: float = 1.0  # 提取置信度
    source_thread_id: str | None = None
    source_message_id: str | None = None
    
    # 作用域
    user_id: str | None = None
    project_id: int | None = None
    
    # 扩展数据
    extra: dict[str, Any] = Field(default_factory=dict)
```

### 3.2 新的 MemoryManager 门面

```python
# app/core/memory_v2/manager.py
class MemoryManager:
    """
    统一的记忆管理门面（v2 重构版）
    设计原则：
    1. 向后兼容：保持 v1 接口，内部转发到 v2
    2. 功能完整：嵌入式模式下长期记忆可用
    3. 统一存储：单一后端处理所有长期记忆
    """
    
    def __init__(self):
        # 短期记忆：始终使用 SQL
        self.short_term = ShortTermManager()
        
        # 长期记忆：根据模式选择后端
        if settings.EMBEDDED_MODE:
            backend = FileBackend(settings.MEMORY_ROOT)
        else:
            backend = Neo4jBackend()
        
        self.long_term = LongTermManager(backend)
        self.consolidation = ConsolidationService(self.long_term)
    
    # ========== 短期记忆接口 ==========
    async def add_message(self, thread_id: str, message: BaseMessage) -> None:
        await self.short_term.add_message(thread_id, message)
    
    async def get_context(self, thread_id: str, limit: int = 50) -> list[BaseMessage]:
        return await self.short_term.get_context(thread_id, limit)
    
    # ========== 长期记忆接口（v2 新增） ==========
    async def store_memory(self, entry: MemoryEntry) -> str:
        return await self.long_term.store(entry)
    
    async def find_relevant_memories(
        self,
        query: str,
        context: dict[str, Any],
        max_tokens: int = 2000,
        types: list[MemoryType] | None = None,
    ) -> str:
        """
        查找相关记忆（借鉴 Claude Code 的 findRelevantMemories）
        流程：
        1. 扫描索引文件获取候选记忆
        2. 使用 LLM 选择最相关的记忆
        3. 控制注入上下文的长度
        """
        return await self.long_term.retrieve_relevant(
            query=query, context=context, max_tokens=max_tokens, types=types
        )
    
    async def extract_memories(self, thread_id: str, conversation_summary: str) -> list[MemoryEntry]:
        """从对话中提取记忆（借鉴 Claude Code 的 extractMemories）"""
        return await self.long_term.extract_from_conversation(thread_id, conversation_summary)
    
    # ========== 向后兼容接口（v1） ==========
    async def store_concept(self, concept: Concept) -> None:
        entry = MemoryEntry(
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title=concept.name,
            content=concept.description,
            tags=["concept"] + (concept.related_files or []),
        )
        await self.long_term.store(entry)
    
    async def search_concepts(self, query: str, project_id: int | None = None) -> list[SearchResult]:
        results = await self.long_term.search(query=query, types=[MemoryType.PROJECT], limit=10)
        return [SearchResult(name=r.memory.title, description=r.memory.content, score=r.score) for r in results]
```

### 3.3 文件后端实现

```python
# app/core/memory_v2/backends/file_backend.py
class FileBackend(ILongTermBackend):
    """
    基于文件的长期记忆后端（嵌入式模式）
    
    目录结构：
    ~/.evoloop/memory/
    ├── MEMORY.md          # 索引文件
    ├── private/           # 私有记忆
    │   ├── user-profile.md
    │   └── feedback/
    └── team/              # 团队共享记忆
        ├── project-{id}/
        └── reference/
    """
    
    def __init__(self, root_path: str):
        self.root = Path(root_path).expanduser()
        self.index_path = self.root / "MEMORY.md"
        self.private_dir = self.root / "private"
        self.team_dir = self.root / "team"
    
    async def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.private_dir.mkdir(exist_ok=True)
        self.team_dir.mkdir(exist_ok=True)
        if not self.index_path.exists():
            await self._create_index()
    
    async def store(self, entry: MemoryEntry) -> str:
        file_path = self._get_storage_path(entry)
        content = self._serialize_entry(entry)
        file_path.write_text(content, encoding="utf-8")
        await self._update_index(entry)
        return entry.id
    
    async def search(self, query: str, types: list[MemoryType] | None = None, limit: int = 10) -> list[SearchResult]:
        candidates = await self._get_candidates(types)
        results = []
        keywords = query.lower().split()
        
        for file_path in candidates:
            entry = await self._parse_entry(file_path)
            if not entry:
                continue
            score = self._calculate_relevance(entry, keywords)
            if score > 0:
                results.append(SearchResult(memory=entry, score=score))
        
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
    
    def _serialize_entry(self, entry: MemoryEntry) -> str:
        """序列化记忆条目为 Markdown + YAML Frontmatter"""
        frontmatter = {
            "id": entry.id,
            "type": entry.type.value,
            "privacy": entry.privacy.value,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
            "version": entry.version,
            "tags": entry.tags,
            "source": entry.source.value,
            "confidence": entry.confidence,
            "title": entry.title,
        }
        if entry.project_id:
            frontmatter["project_id"] = entry.project_id
        
        yaml_content = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        return f"---\n{yaml_content}---\n\n{entry.content}\n"
```

---

## 4. 文件存储格式规范

### 4.1 索引文件（MEMORY.md）

```markdown
# EvoLoop Memory Index

> 此文件由系统自动生成，请勿手动修改

## 统计
- 总记忆数: 42
- 上次更新: 2026-04-02T10:00:00Z

## 按类型索引

### User (3)
- [用户画像](private/user-profile.md)
- [编码偏好](private/coding-preferences.md)

### Feedback (15)
- [2026-04-02-feedback-001](private/feedback/2026-04-02-feedback-001.md)

### Project (20)
- [Project 1: Architecture](team/project-1/architecture.md)

### Reference (4)
- [Python Best Practices](team/reference/python-best-practices.md)

## 按标签索引

### coding-style
- [编码偏好](private/coding-preferences.md)

### architecture
- [Project 1: Architecture](team/project-1/architecture.md)
```

### 4.2 记忆文件示例

```markdown
---
id: "mem_user_001"
type: "user"
privacy: "private"
title: "用户编码偏好"
created_at: "2026-04-02T10:00:00Z"
updated_at: "2026-04-02T10:00:00Z"
version: 1
tags: ["preferences", "coding-style", "python"]
source: "extracted"
confidence: 0.95
---

## Python 编码风格偏好

用户偏好以下 Python 代码风格：

1. **引号使用**：优先使用双引号 `"` 而非单引号 `'`
2. **类型注解**：所有函数参数和返回值都应添加类型注解
3. **文档字符串**：使用 Google 风格的文档字符串
4. **行长度**：每行不超过 100 个字符

### 示例代码

```python
def process_data(input_data: list[dict]) -> list[dict]:
    \"\"\"处理输入数据并返回结果。
    
    Args:
        input_data: 输入数据列表
        
    Returns:
        处理后的数据列表
    \"\"\"
    return [item for item in input_data if item.get("active")]
```
```

---

## 5. 迁移路径

### 5.1 分阶段实施

```
Phase 1: 基础建设（1-2 周）
├── 创建 memory_v2 模块
├── 实现 FileBackend
├── 实现核心模型和接口
└── 编写单元测试

Phase 2: 功能实现（2-3 周）
├── 实现自动提取服务
├── 实现智能检索
├── 实现向后兼容层
└── 集成测试

Phase 3: 逐步迁移（1-2 周）
├── 新增代码使用 v2 接口
├── 监控和修复问题
├── 性能优化
└── 文档更新

Phase 4: 最终切换（1 周）
├── 切换默认实现到 v2
├── 保留 v1 作为兼容层
├── 清理废弃代码
└── 发布说明
```

### 5.2 向后兼容策略

```python
# app/core/memory/__init__.py
# 保持原有导出不变，内部使用 v2 实现

# 检测是否启用 v2
USE_MEMORY_V2 = settings.USE_MEMORY_V2

if USE_MEMORY_V2:
    from app.core.memory_v2.manager import MemoryManager
    from app.core.memory_v2.models import MemoryEntry, MemoryType
else:
    from app.core.memory.manager import MemoryManager

# 全局实例
memory_manager = MemoryManager()
```

### 5.3 数据迁移

```python
# 从 Brain 迁移到 Memory v2
async def migrate_brain_to_v2():
    """将 Brain 文件系统迁移到 Memory v2"""
    fs = BrainFileSystem(settings.BRAIN_MEMORY_ROOT)
    
    # 迁移 journal.md
    journal_content = fs.read_file("knowledge/journal.md")
    entries = parse_journal_entries(journal_content)
    
    for entry in entries:
        memory_entry = MemoryEntry(
            type=MemoryType.FEEDBACK,
            privacy=PrivacyLevel.PRIVATE,
            title=entry.title,
            content=entry.content,
            source=MemorySource.CONSOLIDATED,
        )
        await memory_manager.store_memory(memory_entry)
```

---

## 6. 实施优先级和时间估算

### 6.1 优先级矩阵

| 功能 | 影响 | 复杂度 | 优先级 | 预估时间 |
|------|------|--------|--------|----------|
| FileBackend | 高 | 中 | P0 | 3 天 |
| MemoryEntry 模型 | 高 | 低 | P0 | 1 天 |
| 向后兼容层 | 高 | 中 | P0 | 2 天 |
| 自动提取 | 中 | 高 | P1 | 5 天 |
| 智能检索 | 中 | 高 | P1 | 5 天 |
| 索引系统 | 中 | 中 | P1 | 3 天 |
| Neo4jBackend | 低 | 中 | P2 | 3 天 |
| 数据迁移工具 | 中 | 低 | P2 | 2 天 |

### 6.2 总时间估算

| 阶段 | 时间 | 产出 |
|------|------|------|
| Phase 1 | 1-2 周 | 基础功能可用 |
| Phase 2 | 2-3 周 | 完整功能实现 |
| Phase 3 | 1-2 周 | 逐步迁移完成 |
| Phase 4 | 1 周 | 正式发布 |
| **总计** | **5-8 周** | 完整重构 |

---

## 7. 风险与缓解

### 7.1 主要风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 向后兼容问题 | 中 | 高 | 保持 v1 接口，逐步切换 |
| 性能下降 | 低 | 中 | 实现缓存层，异步索引更新 |
| 数据丢失 | 低 | 高 | 迁移前备份，提供回滚方案 |
| 用户学习成本 | 中 | 低 | 保持 API 不变，内部重构 |

### 7.2 回滚方案

```python
# 通过配置快速回滚到 v1
if settings.MEMORY_SYSTEM_VERSION == "v1":
    from app.core.memory.manager import MemoryManager
elif settings.MEMORY_SYSTEM_VERSION == "v2":
    from app.core.memory_v2.manager import MemoryManager
```

---

## 8. 总结

### 8.1 核心改进

1. **统一架构**：消除 Memory 和 Brain 的重复
2. **功能完整**：嵌入式模式下长期记忆可用
3. **类型系统**：借鉴 Claude Code 的四类型分类
4. **智能提取**：自动分析对话提取记忆
5. **智能检索**：LLM 辅助选择相关记忆

### 8.2 关键成功因素

1. **向后兼容**：确保现有代码平滑过渡
2. **分阶段实施**：降低风险，快速迭代
3. **充分测试**：单元测试 + 集成测试 + 性能测试
4. **文档完整**：开发者文档 + 用户指南

### 8.3 下一步行动

1. [ ] 创建 feature branch：`feature/memory-v2`
2. [ ] 实现基础模型和 FileBackend
3. [ ] 编写单元测试
4. [ ] 实现向后兼容层
5. [ ] 内部测试和 review
6. [ ] 逐步迁移现有代码
