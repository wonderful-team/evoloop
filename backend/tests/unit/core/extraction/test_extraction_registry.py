"""Tests for the extraction framework (ExtractionPlugin / ExtractionRegistry)."""

import json
from unittest.mock import AsyncMock

import pytest

from app.core.extraction import ExtractionContext, ExtractionPlugin, ExtractionRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the singleton registry state between tests."""
    ExtractionRegistry._plugins.clear()
    ExtractionRegistry._handled_threads.clear()
    yield


# =============================================================================
# ExtractionPlugin
# =============================================================================


class TestExtractionPlugin:
    def test_minimal_plugin(self):
        p = ExtractionPlugin(name="test", description="A test plugin", output_schema={})
        assert p.name == "test"
        assert p.confidence_threshold == 0.7
        assert p.handler is None

    def test_full_plugin(self):
        async def handler(data, ctx):
            pass

        p = ExtractionPlugin(
            name="full",
            description="Full plugin",
            output_schema={"type": "object", "properties": {"x": {"type": "string"}}},
            confidence_threshold=0.5,
            handler=handler,
        )
        assert p.name == "full"
        assert p.confidence_threshold == 0.5
        assert p.handler is handler


# =============================================================================
# ExtractionRegistry — Registration
# =============================================================================


class TestRegistryRegistration:
    def test_register_and_get(self):
        p = ExtractionPlugin(name="alpha", description="First", output_schema={})
        ExtractionRegistry.register(p)
        assert ExtractionRegistry.get("alpha") is p

    def test_register_overwrite_warning(self, caplog):
        p1 = ExtractionPlugin(name="dup", description="First", output_schema={})
        p2 = ExtractionPlugin(name="dup", description="Second", output_schema={})
        ExtractionRegistry.register(p1)
        ExtractionRegistry.register(p2)
        assert "Overwriting existing plugin" in caplog.text
        assert ExtractionRegistry.get("dup") is p2

    def test_get_nonexistent(self):
        assert ExtractionRegistry.get("nope") is None

    def test_list_plugins(self):
        p1 = ExtractionPlugin(name="a", description="A", output_schema={})
        p2 = ExtractionPlugin(name="b", description="B", output_schema={})
        ExtractionRegistry.register(p1)
        ExtractionRegistry.register(p2)
        names = {p.name for p in ExtractionRegistry.list_plugins()}
        assert names == {"a", "b"}


# =============================================================================
# ExtractionRegistry — Thread tracking
# =============================================================================


class TestThreadTracking:
    def test_mark_and_check(self):
        assert ExtractionRegistry.is_thread_handled("t1") is False
        ExtractionRegistry.mark_thread_handled("t1")
        assert ExtractionRegistry.is_thread_handled("t1") is True

    def test_clear_on_overflow(self):
        # Fill to near limit
        for i in range(ExtractionRegistry._MAX_HANDLED):
            ExtractionRegistry.mark_thread_handled(f"t{i}")
        assert ExtractionRegistry.is_thread_handled("t0") is True
        # One more should clear the set
        ExtractionRegistry.mark_thread_handled("overflow")
        assert len(ExtractionRegistry._handled_threads) == 1
        assert ExtractionRegistry.is_thread_handled("overflow") is True


# =============================================================================
# ExtractionRegistry — build_prompt_section
# =============================================================================


class TestBuildPromptSection:
    def test_empty_when_no_plugins(self):
        assert ExtractionRegistry.build_prompt_section() == ""

    def test_includes_plugin_names(self):
        ExtractionRegistry.register(
            ExtractionPlugin(name="alpha", description="First plugin", output_schema={})
        )
        section = ExtractionRegistry.build_prompt_section()
        assert "alpha" in section
        assert "First plugin" in section
        assert "evoloop_extractions" in section

    def test_includes_schema(self):
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        ExtractionRegistry.register(
            ExtractionPlugin(name="nums", description="Numbers", output_schema=schema)
        )
        section = ExtractionRegistry.build_prompt_section()
        assert json.dumps(schema) in section
        assert "nums" in section

    def test_includes_multiple_plugins(self):
        ExtractionRegistry.register(
            ExtractionPlugin(name="a", description="Plugin A", output_schema={"a": 1})
        )
        ExtractionRegistry.register(
            ExtractionPlugin(name="b", description="Plugin B", output_schema={"b": 2})
        )
        section = ExtractionRegistry.build_prompt_section()
        assert "Plugin A" in section
        assert "Plugin B" in section


# =============================================================================
# ExtractionRegistry — parse_extractions
# =============================================================================


class TestParseExtractions:
    EXTRACTION_XML = """<evoloop_extractions>
  <extraction name="knowledge" confidence="0.85">
    {"title": "Arch", "content": "Use microservices", "category": "architecture"}
  </extraction>
  <extraction name="memory" confidence="0.92">
    {"type": "preference", "content": "User prefers dark mode"}
  </extraction>
</evoloop_extractions>"""

    def test_parse_valid(self):
        items = ExtractionRegistry.parse_extractions(self.EXTRACTION_XML)
        assert len(items) == 2

        assert items[0]["name"] == "knowledge"
        assert items[0]["confidence"] == 0.85
        assert items[0]["data"]["title"] == "Arch"

        assert items[1]["name"] == "memory"
        assert items[1]["confidence"] == 0.92
        assert items[1]["data"]["type"] == "preference"

    def test_parse_empty_output(self):
        items = ExtractionRegistry.parse_extractions(
            "<evoloop_session_audit>...</evoloop_session_audit>"
        )
        assert items == []

    def test_parse_empty_block(self):
        items = ExtractionRegistry.parse_extractions(
            "<evoloop_extractions>\n</evoloop_extractions>"
        )
        assert items == []

    def test_parse_no_block_at_all(self):
        items = ExtractionRegistry.parse_extractions("Just some text without XML block")
        assert items == []

    def test_parse_malformed_json_skips_item(self, caplog):
        xml = """<evoloop_extractions>
  <extraction name="bad" confidence="0.5">
    {invalid json}
  </extraction>
  <extraction name="good" confidence="0.9">
    {"ok": true}
  </extraction>
</evoloop_extractions>"""
        items = ExtractionRegistry.parse_extractions(xml)
        assert len(items) == 1
        assert items[0]["name"] == "good"
        assert "Failed to parse JSON" in caplog.text

    def test_parse_bad_confidence_returns_zero(self):
        xml = """<evoloop_extractions>
  <extraction name="x" confidence="abc">
    {"key": "val"}
  </extraction>
</evoloop_extractions>"""
        items = ExtractionRegistry.parse_extractions(xml)
        assert len(items) == 1
        assert items[0]["confidence"] == 0.0

    def test_parse_only_extraction_block(self):
        xml = """Some preamble text here.
<evoloop_extractions>
  <extraction name="test" confidence="0.8">
    {"msg": "hello"}
  </extraction>
</evoloop_extractions>
Some trailing text."""
        items = ExtractionRegistry.parse_extractions(xml)
        assert len(items) == 1
        assert items[0]["name"] == "test"

    def test_parse_single_item(self):
        xml = """<evoloop_extractions>
  <extraction name="single" confidence="0.75">
    {"value": 42}
  </extraction>
</evoloop_extractions>"""
        items = ExtractionRegistry.parse_extractions(xml)
        assert len(items) == 1
        assert items[0]["data"]["value"] == 42


# =============================================================================
# ExtractionRegistry — dispatch
# =============================================================================


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_happy_path(self):
        handler = AsyncMock()
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="test",
                description="Test",
                output_schema={},
                confidence_threshold=0.5,
                handler=handler,
            )
        )
        ctx = ExtractionContext(thread_id="t1", project_id=1)
        items = [{"name": "test", "confidence": 0.8, "data": {"key": "val"}}]
        count = await ExtractionRegistry.dispatch(items, ctx)
        assert count == 1
        handler.assert_awaited_once_with({"key": "val"}, ctx)

    @pytest.mark.asyncio
    async def test_dispatch_below_threshold(self):
        handler = AsyncMock()
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="test",
                description="Test",
                output_schema={},
                confidence_threshold=0.9,
                handler=handler,
            )
        )
        ctx = ExtractionContext(thread_id="t1")
        items = [{"name": "test", "confidence": 0.5, "data": {"x": 1}}]
        count = await ExtractionRegistry.dispatch(items, ctx)
        assert count == 0
        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_no_handler(self):
        ExtractionRegistry.register(
            ExtractionPlugin(name="noop", description="No handler", output_schema={})
        )
        ctx = ExtractionContext(thread_id="t1")
        items = [{"name": "noop", "confidence": 0.9, "data": {}}]
        count = await ExtractionRegistry.dispatch(items, ctx)
        assert count == 0

    @pytest.mark.asyncio
    async def test_dispatch_unregistered_plugin(self):
        ctx = ExtractionContext(thread_id="t1")
        items = [{"name": "unknown", "confidence": 0.9, "data": {}}]
        count = await ExtractionRegistry.dispatch(items, ctx)
        assert count == 0

    @pytest.mark.asyncio
    async def test_dispatch_handler_error_continues(self):
        good_handler = AsyncMock()
        bad_handler = AsyncMock(side_effect=ValueError("oops"))

        ExtractionRegistry.register(
            ExtractionPlugin(
                name="bad",
                description="Bad",
                output_schema={},
                handler=bad_handler,
            )
        )
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="good",
                description="Good",
                output_schema={},
                handler=good_handler,
            )
        )

        ctx = ExtractionContext(thread_id="t1")
        items = [
            {"name": "bad", "confidence": 0.9, "data": {}},
            {"name": "good", "confidence": 0.9, "data": {}},
        ]
        count = await ExtractionRegistry.dispatch(items, ctx)
        assert count == 1
        good_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_marks_thread(self):
        handler = AsyncMock()
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="test",
                description="Test",
                output_schema={},
                handler=handler,
            )
        )
        ctx = ExtractionContext(thread_id="mark-me")
        items = [{"name": "test", "confidence": 0.9, "data": {}}]
        await ExtractionRegistry.dispatch(items, ctx)
        assert ExtractionRegistry.is_thread_handled("mark-me") is True


# =============================================================================
# ExtractionRegistry — parse_and_dispatch_from_messages
# =============================================================================


class TestParseAndDispatchFromMessages:
    @pytest.mark.asyncio
    async def test_integration(self):
        handler = AsyncMock()
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="test",
                description="Test",
                output_schema={},
                handler=handler,
            )
        )
        from langchain_core.messages import AIMessage

        messages = [
            AIMessage(content="Earlier message"),
            AIMessage(
                content="""<evoloop_session_audit>...</evoloop_session_audit>
<evoloop_extractions>
  <extraction name="test" confidence="0.9">
    {"result": "success"}
  </extraction>
</evoloop_extractions>"""
            ),
        ]
        ctx = ExtractionContext(thread_id="t1")
        count = await ExtractionRegistry.parse_and_dispatch_from_messages(messages, ctx)
        assert count == 1
        handler.assert_awaited_once_with({"result": "success"}, ctx)

    @pytest.mark.asyncio
    async def test_no_extractions_in_messages(self):
        handler = AsyncMock()
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="test",
                description="Test",
                output_schema={},
                handler=handler,
            )
        )
        from langchain_core.messages import AIMessage, HumanMessage

        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Just an audit, no extractions"),
        ]
        ctx = ExtractionContext(thread_id="t1")
        count = await ExtractionRegistry.parse_and_dispatch_from_messages(messages, ctx)
        assert count == 0
        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_non_ai_messages(self):
        handler = AsyncMock()
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="test",
                description="Test",
                output_schema={},
                handler=handler,
            )
        )
        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content="<evoloop_extractions>...")]
        ctx = ExtractionContext(thread_id="t1")
        count = await ExtractionRegistry.parse_and_dispatch_from_messages(messages, ctx)
        assert count == 0

    @pytest.mark.asyncio
    async def test_uses_last_matching_message(self):
        handler = AsyncMock()
        ExtractionRegistry.register(
            ExtractionPlugin(
                name="test",
                description="Test",
                output_schema={},
                handler=handler,
            )
        )
        from langchain_core.messages import AIMessage

        messages = [
            AIMessage(
                content="""<evoloop_extractions>
  <extraction name="test" confidence="0.9">
    {"from": "first"}
  </extraction>
</evoloop_extractions>"""
            ),
            AIMessage(
                content="""<evoloop_extractions>
  <extraction name="test" confidence="0.9">
    {"from": "second"}
  </extraction>
</evoloop_extractions>"""
            ),
        ]
        ctx = ExtractionContext(thread_id="t1")
        count = await ExtractionRegistry.parse_and_dispatch_from_messages(messages, ctx)
        assert count == 1
        # Should use the LAST message
        handler.assert_awaited_once()
        assert handler.await_args[0][0]["from"] == "second"


# =============================================================================
# ExtractionContext
# =============================================================================


class TestExtractionContext:
    def test_minimal_context(self):
        ctx = ExtractionContext(thread_id="t1")
        assert ctx.thread_id == "t1"
        assert ctx.project_id is None
        assert ctx.extra == {}

    def test_full_context(self):
        ctx = ExtractionContext(
            thread_id="t1",
            project_id=42,
            user_id="u1",
            run_id="r1",
            summary="Done",
            extra={"source": "test"},
        )
        assert ctx.project_id == 42
        assert ctx.extra["source"] == "test"
