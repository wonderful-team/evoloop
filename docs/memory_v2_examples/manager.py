"""MemoryManager 实现示例 - 统一的记忆管理门面"""
import logging
from typing import Any
from langchain_core.messages import BaseMessage

# 假设这些从其他模块导入
from models import MemoryEntry, MemoryType, PrivacyLevel, MemorySource, SearchResult as V2SearchResult
from file_backend import FileBackend

logger = logging.getLogger(__name__)


# v1 兼容接口
class Concept:
    def __init__(self, name: str, description: str, project_id: int, related_files: list[str] | None = None):
        self.name = name
        self.description = description
        self.project_id = project_id
        self.related_files = related_files or []


class Episode:
    def __init__(self, goal: str, result: str, plan_summary: str, error_msg: str | None, project_id: int, source_message_id: str | None = None):
        self.goal = goal
        self.result = result
        self.plan_summary = plan_summary
        self.error_msg = error_msg
        self.project_id = project_id
        self.source_message_id = source_message_id


class SearchResult:
    def __init__(self, name: str, description: str, score: float, files: list[str] | None = None):
        self.name = name
        self.description = description
        self.score = score
        self.files = files or []


class ShortTermManager:
    """短期记忆管理器（包装现有的 SqlShortTermMemory）"""
    
    def __init__(self):
        # 实际实现中：from app.core.memory.backends.sql_short_term import SqlShortTermMemory
        # self._impl = SqlShortTermMemory()
        pass
    
    async def initialize(self) -> None:
        logger.info("ShortTermManager initialized")
    
    async def add_message(self, thread_id: str, message: BaseMessage) -> None:
        """添加消息到短期记忆"""
        logger.debug(f"Added message to thread {thread_id}")
    
    async def get_context(self, thread_id: str, limit: int = 50) -> list[BaseMessage]:
        """获取对话上下文"""
        return []
    
    async def search_messages(self, query: str, thread_id: str | None = None, limit: int = 10) -> list[BaseMessage]:
        """搜索消息"""
        return []


class LongTermManager:
    """长期记忆管理器（v2 核心）"""
    
    def __init__(self, backend):
        self.backend = backend
    
    async def initialize(self) -> None:
        await self.backend.initialize()
        logger.info("LongTermManager initialized")
    
    async def store(self, entry: MemoryEntry) -> str:
        """存储记忆条目"""
        return await self.backend.store(entry)
    
    async def search(
        self,
        query: str,
        types: list[MemoryType] | None = None,
        limit: int = 10
    ) -> list[V2SearchResult]:
        """搜索记忆"""
        return await self.backend.search(query, types, limit)
    
    async def retrieve_relevant(
        self,
        query: str,
        context: dict[str, Any],
        max_tokens: int = 2000,
        types: list[MemoryType] | None = None,
    ) -> str:
        """
        检索相关记忆（借鉴 Claude Code）
        
        流程：
        1. 获取候选记忆
        2. 使用 LLM 选择最相关的
        3. 控制总 token 数
        """
        # 1. 获取候选
        candidates = await self.search(query, types, limit=20)
        
        if not candidates:
            return ""
        
        # 2. 使用 LLM 选择相关记忆（简化实现）
        # 实际实现中应该调用 LLM 进行相关性判断
        selected = candidates[:5]  # 简化：直接取前5个
        
        # 3. 格式化输出
        return self._format_memories(selected, max_tokens)
    
    async def extract_from_conversation(
        self,
        thread_id: str,
        summary: str,
    ) -> list[MemoryEntry]:
        """
        从对话中提取记忆
        
        实际实现中应该：
        1. 获取现有记忆摘要（避免重复）
        2. 使用 LLM 分析对话
        3. 生成新的记忆条目
        4. 存储到长期记忆
        """
        logger.info(f"Extracting memories from thread {thread_id}")
        # 简化实现：返回空列表
        return []
    
    def _format_memories(self, results: list[V2SearchResult], max_tokens: int) -> str:
        """格式化记忆为上下文字符串"""
        sections = []
        current_tokens = 0
        
        for r in results:
            entry = r.memory
            text = f"## {entry.title}\n{entry.content}\n\n"
            # 简化 token 计算（实际应该用 tiktoken）
            tokens = len(text) // 4
            
            if current_tokens + tokens > max_tokens:
                break
            
            sections.append(text)
            current_tokens += tokens
        
        if not sections:
            return ""
        
        return "# Relevant Memories\n\n" + "".join(sections)


class MemoryManager:
    """
    统一的记忆管理门面（v2 重构版）
    
    设计原则：
    1. 向后兼容：保持 v1 接口，内部转发到 v2
    2. 功能完整：嵌入式模式下长期记忆可用
    3. 统一存储：单一后端处理所有长期记忆
    """
    
    def __init__(self, embedded_mode: bool = True):
        # 短期记忆：始终使用 SQL
        self.short_term = ShortTermManager()
        
        # 长期记忆：根据模式选择后端
        if embedded_mode:
            backend = FileBackend("~/.evoloop/memory")
        else:
            # 实际实现中可以使用 Neo4jBackend
            backend = FileBackend("~/.evoloop/memory")
        
        self.long_term = LongTermManager(backend)
    
    async def initialize(self) -> None:
        """初始化所有记忆组件"""
        await self.short_term.initialize()
        await self.long_term.initialize()
        logger.info("MemoryManager initialized")
    
    # ========== 短期记忆接口 ==========
    
    async def add_message(self, thread_id: str, message: BaseMessage) -> None:
        """添加消息到短期记忆"""
        await self.short_term.add_message(thread_id, message)
    
    async def get_context(self, thread_id: str, limit: int = 50) -> list[BaseMessage]:
        """获取对话上下文"""
        return await self.short_term.get_context(thread_id, limit)
    
    # ========== 长期记忆接口（v2 新增） ==========
    
    async def store_memory(self, entry: MemoryEntry) -> str:
        """存储记忆条目"""
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
        """
        return await self.long_term.retrieve_relevant(query, context, max_tokens, types)
    
    async def extract_memories(self, thread_id: str, conversation_summary: str) -> list[MemoryEntry]:
        """从对话中提取记忆"""
        return await self.long_term.extract_from_conversation(thread_id, conversation_summary)
    
    # ========== 向后兼容接口（v1） ==========
    
    async def store_concept(self, concept: Concept) -> None:
        """v1 兼容：存储概念"""
        entry = MemoryEntry(
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title=concept.name,
            content=concept.description,
            tags=["concept"] + (concept.related_files or []),
        )
        await self.long_term.store(entry)
    
    async def search_concepts(
        self,
        query: str,
        project_id: int | None = None,
        min_score: float = 0.7
    ) -> list[SearchResult]:
        """v1 兼容：搜索概念"""
        results = await self.long_term.search(
            query=query,
            types=[MemoryType.PROJECT],
            limit=10,
        )
        return [
            SearchResult(
                name=r.memory.title,
                description=r.memory.content,
                score=r.score,
                files=r.memory.tags,
            )
            for r in results
        ]
    
    async def record_episode(self, episode: Episode) -> str | None:
        """v1 兼容：记录执行片段"""
        entry = MemoryEntry(
            type=MemoryType.FEEDBACK,
            privacy=PrivacyLevel.PRIVATE,
            title=f"Episode: {episode.goal[:50]}...",
            content=f"Goal: {episode.goal}\nResult: {episode.result}",
            source_thread_id=episode.source_message_id,
            extra={
                "plan_summary": episode.plan_summary,
                "error_msg": episode.error_msg,
            }
        )
        return await self.long_term.store(entry)
    
    async def search_messages(self, query: str, thread_id: str | None = None, limit: int = 10):
        """v1 兼容：搜索消息"""
        return await self.short_term.search_messages(query, thread_id, limit)


# 全局实例（类似 v1）
memory_manager = MemoryManager(embedded_mode=True)


# 示例用法
if __name__ == "__main__":
    import asyncio
    
    async def main():
        # 初始化
        await memory_manager.initialize()
        
        # 使用 v2 接口存储记忆
        entry = MemoryEntry(
            type=MemoryType.USER,
            privacy=PrivacyLevel.PRIVATE,
            title="测试记忆",
            content="这是一个测试记忆条目",
            tags=["test"],
        )
        memory_id = await memory_manager.store_memory(entry)
        print(f"Stored with ID: {memory_id}")
        
        # 使用 v1 兼容接口
        concept = Concept(
            name="测试概念",
            description="这是一个测试概念",
            project_id=1,
        )
        await memory_manager.store_concept(concept)
        print("Concept stored via v1 API")
        
        # 搜索
        results = await memory_manager.search_concepts("测试", project_id=1)
        print(f"Found {len(results)} concepts")
    
    asyncio.run(main())
