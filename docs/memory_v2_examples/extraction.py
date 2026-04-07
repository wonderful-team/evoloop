"""MemoryExtractionService 实现示例 - 自动提取记忆"""
import json
import logging
from typing import Any
from langchain_core.messages import BaseMessage, SystemMessage

from models import MemoryEntry, MemoryType, PrivacyLevel, MemorySource

logger = logging.getLogger(__name__)


class MemoryExtractionService:
    """记忆自动提取服务（借鉴 Claude Code 的 extractMemories）"""
    
    def __init__(self, long_term_manager):
        self.long_term = long_term_manager
    
    async def extract_from_conversation(
        self,
        thread_id: str,
        messages: list[BaseMessage],
        existing_memories: list[MemoryEntry] | None = None,
    ) -> list[MemoryEntry]:
        """从对话中提取新记忆"""
        if existing_memories is None:
            existing_memories = []
        
        # 1. 构建对话摘要
        conversation_text = self._format_conversation(messages)
        existing_summary = self._summarize_existing(existing_memories)
        
        # 2. 使用 LLM 提取记忆
        prompt = self._build_extraction_prompt(conversation_text, existing_summary)
        logger.info(f"Extracting memories from thread {thread_id}")
        
        # 模拟返回
        extracted = self._simulate_extraction(conversation_text)
        
        # 3. 转换为 MemoryEntry 并存储
        new_entries = []
        for item in extracted:
            entry = MemoryEntry(
                type=MemoryType(item["type"]),
                privacy=PrivacyLevel(item.get("privacy", "private")),
                title=item["title"],
                content=item["content"],
                source=MemorySource.EXTRACTED,
                confidence=item.get("confidence", 0.8),
                source_thread_id=thread_id,
                tags=item.get("tags", []),
            )
            
            entry_id = await self.long_term.store(entry)
            entry.id = entry_id
            new_entries.append(entry)
            logger.info(f"Extracted memory: {entry.title} ({entry.type.value})")
        
        return new_entries
    
    def _format_conversation(self, messages: list[BaseMessage]) -> str:
        """将消息列表格式化为对话文本"""
        lines = []
        for msg in messages:
            role = getattr(msg, 'type', 'unknown')
            content = str(msg.content) if msg.content else ""
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)
    
    def _summarize_existing(self, memories: list[MemoryEntry]) -> str:
        """生成现有记忆的摘要"""
        if not memories:
            return "无现有记忆"
        lines = [f"- [{m.type.value}] {m.title}" for m in memories[:10]]
        return "\n".join(lines)
    
    def _build_extraction_prompt(self, conversation: str, existing_summary: str) -> str:
        """构建提取提示词"""
        return f"""分析以下对话，提取需要长期记忆的重要信息。

## 现有记忆摘要
{existing_summary}

## 对话内容
{conversation}

## 提取规则

1. **记忆类型**：user(用户偏好)、feedback(反馈)、project(项目)、reference(引用)
2. **隐私级别**：private(私有)、team(团队)
3. **提取原则**：避免重复、优先显式偏好、忽略临时信息
4. **置信度**：0.9-1.0(明确)、0.7-0.9(推断)、0.5-0.7(推测)

## 输出格式

返回 JSON 数组，每个元素包含：type, privacy, title, content, confidence, tags
"""
    
    def _simulate_extraction(self, conversation: str) -> list[dict]:
        """模拟记忆提取（用于演示）"""
        extracted = []
        
        if "python" in conversation.lower():
            extracted.append({
                "type": "user",
                "privacy": "private",
                "title": "Python 使用偏好",
                "content": "用户在讨论中使用 Python，可能对 Python 开发有偏好",
                "confidence": 0.7,
                "tags": ["python", "preferences"],
            })
        
        return extracted


if __name__ == "__main__":
    import asyncio
    from langchain_core.messages import HumanMessage, AIMessage
    
    async def main():
        class MockLongTermManager:
            async def store(self, entry: MemoryEntry) -> str:
                return entry.id or "mem_test_001"
        
        service = MemoryExtractionService(MockLongTermManager())
        
        messages = [
            HumanMessage(content="你好，请帮我写一个 Python 脚本处理数据"),
            AIMessage(content="当然可以！您需要处理什么格式的数据？"),
        ]
        
        new_memories = await service.extract_from_conversation("thread_001", messages)
        print(f"Extracted {len(new_memories)} memories")
        for m in new_memories:
            print(f"  - {m.title}")
    
    asyncio.run(main())
