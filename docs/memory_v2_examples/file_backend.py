"""FileBackend 实现示例 - 基于文件的长期记忆后端"""
import yaml
import logging
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod
from models import MemoryEntry, MemoryType, PrivacyLevel, MemorySource, SearchResult

logger = logging.getLogger(__name__)


class ILongTermBackend(ABC):
    """长期记忆后端接口"""
    
    @abstractmethod
    async def initialize(self) -> None:
        pass
    
    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        pass
    
    @abstractmethod
    async def search(self, query: str, types: list[MemoryType] | None = None, limit: int = 10) -> list[SearchResult]:
        pass


class FileBackend(ILongTermBackend):
    """基于文件的长期记忆后端"""
    
    def __init__(self, root_path: str = "~/.evoloop/memory"):
        self.root = Path(root_path).expanduser()
        self.index_path = self.root / "MEMORY.md"
        self.private_dir = self.root / "private"
        self.team_dir = self.root / "team"
    
    async def initialize(self) -> None:
        """初始化目录结构"""
        self.root.mkdir(parents=True, exist_ok=True)
        self.private_dir.mkdir(exist_ok=True)
        self.team_dir.mkdir(exist_ok=True)
        (self.private_dir / "feedback").mkdir(exist_ok=True)
        (self.team_dir / "reference").mkdir(exist_ok=True)
        
        if not self.index_path.exists():
            await self._create_index()
        
        logger.info(f"FileBackend initialized at {self.root}")
    
    async def store(self, entry: MemoryEntry) -> str:
        """存储记忆条目"""
        file_path = self._get_storage_path(entry)
        content = self._serialize_entry(entry)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        await self._update_index(entry)
        logger.debug(f"Stored memory {entry.id} to {file_path}")
        return entry.id
    
    async def search(self, query: str, types: list[MemoryType] | None = None, limit: int = 10) -> list[SearchResult]:
        """搜索记忆"""
        keywords = query.lower().split()
        results = []
        candidates = list(self._get_all_memory_files())
        
        for file_path in candidates:
            entry = await self._parse_entry(file_path)
            if not entry:
                continue
            if types and entry.type not in types:
                continue
            score = self._calculate_relevance(entry, keywords)
            if score > 0:
                results.append(SearchResult(memory=entry, score=score))
        
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
    
    def _get_storage_path(self, entry: MemoryEntry) -> Path:
        """确定记忆条目的存储路径"""
        base_dir = self.private_dir if entry.privacy == PrivacyLevel.PRIVATE else self.team_dir
        
        if entry.type == MemoryType.USER:
            return base_dir / "user-profile.md"
        elif entry.type == MemoryType.FEEDBACK:
            feedback_dir = base_dir / "feedback"
            date_str = entry.created_at.strftime("%Y-%m-%d")
            return feedback_dir / f"{date_str}-{entry.id}.md"
        elif entry.type == MemoryType.PROJECT:
            if entry.project_id:
                project_dir = base_dir / f"project-{entry.project_id}"
                return project_dir / f"{self._slugify(entry.title)}.md"
            return base_dir / f"{self._slugify(entry.title)}.md"
        else:  # REFERENCE
            ref_dir = base_dir / "reference"
            return ref_dir / f"{self._slugify(entry.title)}.md"
    
    def _serialize_entry(self, entry: MemoryEntry) -> str:
        """序列化记忆条目为 Markdown + YAML Frontmatter"""
        frontmatter = {
            "id": entry.id,
            "type": entry.type.value,
            "privacy": entry.privacy.value,
            "title": entry.title,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
            "version": entry.version,
            "tags": entry.tags,
            "source": entry.source.value,
            "confidence": entry.confidence,
        }
        
        if entry.project_id:
            frontmatter["project_id"] = entry.project_id
        if entry.user_id:
            frontmatter["user_id"] = entry.user_id
        if entry.source_thread_id:
            frontmatter["source_thread_id"] = entry.source_thread_id
        
        yaml_content = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return f"---\n{yaml_content}---\n\n{entry.content}\n"
    
    async def _parse_entry(self, file_path: Path) -> MemoryEntry | None:
        """解析 Markdown 文件为记忆条目"""
        try:
            content = file_path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None
            
            parts = content.split("---", 2)
            if len(parts) < 3:
                return None
            
            frontmatter = yaml.safe_load(parts[1])
            body = parts[2].strip()
            
            return MemoryEntry(
                id=frontmatter["id"],
                type=MemoryType(frontmatter["type"]),
                privacy=PrivacyLevel(frontmatter["privacy"]),
                title=frontmatter["title"],
                content=body,
                created_at=datetime.fromisoformat(frontmatter["created_at"]),
                updated_at=datetime.fromisoformat(frontmatter["updated_at"]),
                version=frontmatter.get("version", 1),
                tags=frontmatter.get("tags", []),
                source=MemorySource(frontmatter.get("source", "manual")),
                confidence=frontmatter.get("confidence", 1.0),
                project_id=frontmatter.get("project_id"),
                user_id=frontmatter.get("user_id"),
                source_thread_id=frontmatter.get("source_thread_id"),
            )
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None
    
    def _get_all_memory_files(self):
        """获取所有记忆文件路径"""
        for dir_path in [self.private_dir, self.team_dir]:
            if dir_path.exists():
                yield from dir_path.rglob("*.md")
    
    def _calculate_relevance(self, entry: MemoryEntry, keywords: list[str]) -> float:
        """计算记忆条目与关键词的相关性分数"""
        if not keywords:
            return 0.0
        
        text = f"{entry.title} {entry.content} {' '.join(entry.tags)}".lower()
        matches = sum(1 for kw in keywords if kw in text)
        return matches / len(keywords)
    
    def _slugify(self, text: str) -> str:
        """将文本转换为文件名安全的 slug"""
        return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")
    
    async def _create_index(self) -> None:
        """创建初始索引文件"""
        index_content = """# EvoLoop Memory Index

> 此文件由系统自动生成，请勿手动修改

## 统计
- 总记忆数: 0
- 上次更新: {}

## 索引

### User
_No entries_

### Feedback
_No entries_

### Project
_No entries_

### Reference
_No entries_
""".format(datetime.utcnow().isoformat())
        
        self.index_path.write_text(index_content, encoding="utf-8")
    
    async def _update_index(self, entry: MemoryEntry) -> None:
        """更新索引文件（简化实现）"""
        # 实际实现中应该：
        # 1. 读取现有索引
        # 2. 添加或更新条目
        # 3. 更新统计信息
        # 4. 写回文件
        pass


# 示例用法
if __name__ == "__main__":
    import asyncio
    
    async def main():
        backend = FileBackend("~/.evoloop/memory-test")
        await backend.initialize()
        
        # 创建测试记忆
        entry = MemoryEntry(
            type=MemoryType.USER,
            privacy=PrivacyLevel.PRIVATE,
            title="Python 编码偏好",
            content="用户偏好使用双引号和类型注解",
            tags=["python", "preferences"],
            source=MemorySource.MANUAL,
            confidence=1.0,
        )
        
        memory_id = await backend.store(entry)
        print(f"Stored memory with ID: {memory_id}")
        
        # 搜索
        results = await backend.search("python 编码", limit=5)
        print(f"Found {len(results)} results")
        for r in results:
            print(f"  - {r.memory.title} (score: {r.score:.2f})")
    
    asyncio.run(main())
