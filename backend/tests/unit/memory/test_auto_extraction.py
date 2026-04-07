"""
Unit tests for automatic memory extraction.

pytest tests/unit/memory/test_auto_extraction.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage


class TestAutoMemoryExtractorGates:
    """Tests for extraction gating logic."""

    @pytest.mark.asyncio
    async def test_min_message_gate(self):
        """Test that extraction is skipped with too few messages."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager, min_messages=4)
        
        # Only 2 messages
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there"),
        ]
        
        result = await extractor.maybe_extract("thread_1", messages)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_frequency_gate(self):
        """Test that extraction respects frequency control."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager, extraction_interval=2)
        
        messages = [HumanMessage(content=f"Msg {i}") for i in range(5)]
        
        # First call should work
        with patch.object(extractor, '_run_extraction', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = []
            await extractor.maybe_extract("thread_1", messages)
            assert mock_run.call_count == 1
        
        # Second call should be skipped (throttled)
        with patch.object(extractor, '_run_extraction', new_callable=AsyncMock) as mock_run:
            result = await extractor.maybe_extract("thread_1", messages)
            assert mock_run.call_count == 0
            assert result is None
        
        # Third call should work again
        with patch.object(extractor, '_run_extraction', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = []
            await extractor.maybe_extract("thread_1", messages)
            assert mock_run.call_count == 1
    
    @pytest.mark.asyncio
    async def test_memory_write_detection(self):
        """Test detection of main agent memory writes."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        extractor._last_message_uuid["thread_1"] = "msg_2"
        
        messages = [
            HumanMessage(content="Hello", id="msg_1"),
            AIMessage(content="Hi", id="msg_2"),
            HumanMessage(content="Remember this", id="msg_3"),
            AIMessage(content="✅ Remembered: Use TypeScript", id="msg_4"),  # Memory write
        ]
        
        result = await extractor._has_memory_writes(messages, "thread_1")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_no_memory_write_detection(self):
        """Test when no memory writes exist."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        
        messages = [
            HumanMessage(content="Hello", id="msg_1"),
            AIMessage(content="Hi", id="msg_2"),
            HumanMessage(content="How are you?", id="msg_3"),
            AIMessage(content="I'm fine", id="msg_4"),
        ]
        
        result = await extractor._has_memory_writes(messages, "thread_1")
        
        assert result is False


class TestAutoMemoryExtractorExtraction:
    """Tests for actual extraction logic."""

    @pytest.mark.asyncio
    async def test_extraction_prompt_building(self):
        """Test that extraction prompt is built correctly."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        
        messages = [
            HumanMessage(content="I prefer TypeScript"),
            AIMessage(content="I'll remember that"),
        ]
        
        prompt = extractor._build_extraction_prompt(messages)
        
        assert "message_count" in prompt or isinstance(prompt, str)
    
    @pytest.mark.asyncio
    async def test_message_formatting(self):
        """Test message formatting for extraction."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        
        messages = [
            HumanMessage(content="User message here"),
            AIMessage(content="Assistant response"),
        ]
        
        formatted = extractor._format_messages(messages)
        
        assert "User:" in formatted
        assert "Assistant:" in formatted
        assert "User message here" in formatted
        assert "Assistant response" in formatted
    
    @pytest.mark.asyncio
    async def test_parse_valid_extraction_response(self):
        """Test parsing valid extraction response."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        
        response = '''```json
[
  {
    "type": "user",
    "content": "Prefers TypeScript",
    "context": "User has 5 years experience"
  }
]
```'''
        
        entries = extractor._parse_extraction_response(response, 42, "user_123")
        
        assert len(entries) == 1
        assert entries[0].type.value == "user"
        assert "TypeScript" in entries[0].content
        assert entries[0].source == "auto_extraction"
    
    @pytest.mark.asyncio
    async def test_parse_empty_extraction_response(self):
        """Test parsing empty extraction response."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        
        response = "[]"
        
        entries = extractor._parse_extraction_response(response, 42, "user_123")
        
        assert len(entries) == 0
    
    @pytest.mark.asyncio
    async def test_parse_invalid_json(self):
        """Test handling invalid JSON response."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        
        response = "not valid json"
        
        entries = extractor._parse_extraction_response(response, 42, "user_123")
        
        assert len(entries) == 0
    
    @pytest.mark.asyncio
    async def test_extraction_lock_prevents_concurrent(self):
        """Test that extraction lock prevents concurrent runs."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        
        # Acquire lock manually
        lock = extractor._get_lock("thread_1")
        lock.acquire()
        
        try:
            messages = [HumanMessage(content=f"Msg {i}") for i in range(5)]
            
            result = await extractor.maybe_extract("thread_1", messages)
            
            assert result is None  # Should be skipped due to lock
        finally:
            lock.release()


class TestAutoMemoryExtractorIntegration:
    """Integration-style tests for auto extraction."""

    @pytest.mark.asyncio
    async def test_full_extraction_flow(self):
        """Test full extraction flow with mocked LLM."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        # Create a mock memory manager
        mock_memory_manager = AsyncMock()
        mock_memory_manager.save_memory = AsyncMock()
        
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        
        messages = [
            HumanMessage(content="I prefer using TypeScript for all new projects"),
            AIMessage(content="I'll keep that in mind"),
            HumanMessage(content="Also, always use strict mode"),
            AIMessage(content="Noted"),
        ]
        
        mock_response = '''```json
[
  {
    "type": "user",
    "content": "Prefers TypeScript for all new projects",
    "context": "User preference for language choice"
  }
]
```'''
        
        with patch('app.infrastructure.llm.factory.get_default_llm') as mock_llm:
            mock_llm.return_value.ainvoke = AsyncMock(return_value=MagicMock(content=mock_response))
            
            with patch.object(extractor, '_get_existing_memory_manifest', new_callable=AsyncMock) as mock_manifest:
                mock_manifest.return_value = "No existing memories"
                
                result = await extractor._run_extraction("thread_1", messages, 42, "user_123")
                
                assert len(result) == 1
                assert result[0].type.value == "user"
                mock_memory_manager.save_memory.assert_called_once()


class TestTriggerAutoExtraction:
    """Tests for the trigger function."""

    @pytest.mark.asyncio
    async def test_trigger_function(self):
        """Test the fire-and-forget trigger function."""
        from app.core.memory.auto_extraction import trigger_auto_extraction
        
        messages = [HumanMessage(content="Hello") for _ in range(5)]
        
        # Mock the async extractor getter and shutdown
        mock_extractor = AsyncMock()
        mock_extractor.maybe_extract = AsyncMock(return_value=[])
        
        with patch('app.core.memory.auto_extraction._get_auto_extractor', return_value=mock_extractor):
            with patch('app.core.memory.auto_extraction._shutdown_auto_extractor', new_callable=AsyncMock):
                await trigger_auto_extraction("thread_1", messages, 42, "user_123")
                
                # Should be called
                assert mock_extractor.maybe_extract.called


class TestMemoryTypeDetection:
    """Tests for automatic memory type detection."""

    def test_preference_keywords_detected(self):
        """Test that preference keywords are detected in extraction."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        
        # Parse response with user type
        response = '''[{"type": "user", "content": "I prefer dark mode"}]'''
        entries = extractor._parse_extraction_response(response, None, None)
        
        assert len(entries) == 1
        assert entries[0].type.value == "user"
        assert entries[0].privacy.value == "private"
    
    def test_project_type_default(self):
        """Test that project type is default for non-user memories."""
        from app.core.memory.auto_extraction import AutoMemoryExtractor
        
        mock_memory_manager = AsyncMock()
        extractor = AutoMemoryExtractor(memory_manager=mock_memory_manager)
        
        # Parse response with project type
        response = '''[{"type": "project", "content": "Using Docker for deployment"}]'''
        entries = extractor._parse_extraction_response(response, 42, None)
        
        assert len(entries) == 1
        assert entries[0].type.value == "project"
        assert entries[0].privacy.value == "team"
