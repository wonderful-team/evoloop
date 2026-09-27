"""MCP Features（tools / resources / prompts）单元测试。

覆盖：McpToolsFeature 工具转换与参数 schema 生成、McpResourcesFeature 资源列表与
读取（文本/二进制/base64）、McpPromptsFeature 提示词列表与渲染、命名格式化。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.mcp.features.base import (
    format_mcp_tool_name,
    parse_mcp_tool_name,
)
from app.core.mcp.features.prompts import McpPromptsFeature
from app.core.mcp.features.resources import McpResourcesFeature
from app.core.mcp.features.tools import McpToolsFeature


def _session():
    return AsyncMock()


class TestToolNameFormat:
    def test_format_and_parse(self) -> None:
        name = format_mcp_tool_name("GitHub Server", "Upsert Record")
        assert name.startswith("mcp__github_server__upsert_record")
        parsed = parse_mcp_tool_name(name)
        assert parsed == ("github_server", "upsert_record")

    def test_truncates_to_64(self) -> None:
        name = format_mcp_tool_name("a" * 50, "b" * 50)
        assert len(name) <= 64

    def test_parse_non_mcp_name_returns_none(self) -> None:
        assert parse_mcp_tool_name("some_native_tool") is None


class TestMcpToolsFeature:
    def _tool(self, name="tool_a", input_schema=None, description="desc"):
        return SimpleNamespace(
            name=name,
            description=description,
            inputSchema=input_schema or {"type": "object", "properties": {}},
        )

    async def test_initialize_loads_tools(self) -> None:
        session = _session()
        session.list_tools.return_value = SimpleNamespace(
            tools=[self._tool("a"), self._tool("b")]
        )
        feat = McpToolsFeature()
        await feat.initialize(session, "github")
        assert len(feat.get_tools()) == 2
        assert feat.get_tool_names() == ["mcp__github__a", "mcp__github__b"]

    async def test_initialize_failure_returns_empty(self) -> None:
        session = _session()
        session.list_tools.side_effect = RuntimeError("boom")
        feat = McpToolsFeature()
        await feat.initialize(session, "github")
        assert feat.get_tools() == []

    async def test_tool_call_delegates_to_session(self) -> None:
        session = _session()
        session.list_tools.return_value = SimpleNamespace(
            tools=[self._tool("upsert", {"type": "object", "properties": {}})]
        )
        session.call_tool = AsyncMock(return_value=SimpleNamespace(content=[]))
        feat = McpToolsFeature()
        await feat.initialize(session, "github")
        tool = feat.get_tools()[0]
        await tool.func(table="t")
        session.call_tool.assert_awaited_once_with("upsert", arguments={"table": "t"})

    async def test_args_schema_required_vs_optional(self) -> None:
        session = _session()
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "description": "the name"},
                "age": {"type": "integer", "description": "age"},
            },
        }
        session.list_tools.return_value = SimpleNamespace(tools=[self._tool("t", schema)])
        feat = McpToolsFeature()
        await feat.initialize(session, "github")
        tool = feat.get_tools()[0]
        model = tool.args_schema
        fields = model.model_fields
        assert "name" in fields
        assert fields["name"].is_required()
        assert "age" in fields
        assert fields["age"].is_required() is False

    async def test_args_schema_array_type_union(self) -> None:
        session = _session()
        schema = {
            "type": "object",
            "properties": {
                "opt": {"type": ["null", "string"], "description": "optional"},
            },
        }
        session.list_tools.return_value = SimpleNamespace(tools=[self._tool("t", schema)])
        feat = McpToolsFeature()
        await feat.initialize(session, "github")
        tool = feat.get_tools()[0]
        assert "opt" in tool.args_schema.model_fields

    async def test_capabilities(self) -> None:
        session = _session()
        session.list_tools.return_value = SimpleNamespace(
            tools=[self._tool("a")]
        )
        feat = McpToolsFeature()
        await feat.initialize(session, "github")
        caps = await feat.get_capabilities()
        assert caps.count == 1
        assert caps.tools[0]["name"] == "a"

    def test_reset(self) -> None:
        feat = McpToolsFeature()
        feat._native_tools = [MagicMock()]
        feat.reset()
        assert feat.get_tools() == []


class TestMcpResourcesFeature:
    def _resource(self, uri="file:///readme.md", name="readme", mime="text/markdown"):
        return SimpleNamespace(uri=uri, name=name, mimeType=mime, description="d")

    async def test_initialize_loads_resources(self) -> None:
        session = _session()
        session.list_resources.return_value = SimpleNamespace(
            resources=[self._resource()]
        )
        session.list_resource_templates.return_value = SimpleNamespace(
            resourceTemplates=[SimpleNamespace(uriTemplate="db://t/{id}", name="tpl")]
        )
        feat = McpResourcesFeature()
        await feat.initialize(session, "github")
        assert len(feat.get_resources()) == 1
        assert len(feat.get_resource_templates()) == 1

    async def test_initialize_without_templates(self) -> None:
        session = _session()
        session.list_resources.return_value = SimpleNamespace(resources=[])
        session.list_resource_templates.side_effect = RuntimeError("no tpl")
        feat = McpResourcesFeature()
        await feat.initialize(session, "github")
        assert feat.get_resource_templates() == []

    async def test_read_text_resource(self) -> None:
        session = _session()
        content = SimpleNamespace(text="hello", blob=None, mimeType="text/plain")
        session.read_resource.return_value = SimpleNamespace(contents=[content])
        feat = McpResourcesFeature()
        await feat.initialize(session, "github")
        result = await feat.read_resource("file:///a")
        assert result.content == "hello"
        assert result.is_binary is False
        assert result.mime_type == "text/plain"

    async def test_read_binary_resource(self) -> None:
        import base64

        # 合法 UTF-8 内容（但来自 blob）：应解码为文本
        blob = base64.b64encode("你好 world".encode())
        session = _session()
        content = SimpleNamespace(text=None, blob=blob, mimeType="application/octet-stream")
        session.read_resource.return_value = SimpleNamespace(contents=[content])
        feat = McpResourcesFeature()
        await feat.initialize(session, "github")
        result = await feat.read_resource("file:///bin")
        assert result.is_binary is False
        assert result.content == "你好 world"

    async def test_read_binary_undecodable(self) -> None:
        import base64

        session = _session()
        content = SimpleNamespace(text=None, blob=base64.b64encode(b"\x00\xff\xfe\x01\x02"), mimeType="application/octet-stream")
        session.read_resource.return_value = SimpleNamespace(contents=[content])
        feat = McpResourcesFeature()
        await feat.initialize(session, "github")
        result = await feat.read_resource("file:///bin")
        assert result.is_binary is True  # 无法解码 → 保留 base64

    async def test_read_resource_empty(self) -> None:
        session = _session()
        session.read_resource.return_value = SimpleNamespace(contents=[])
        feat = McpResourcesFeature()
        await feat.initialize(session, "github")
        result = await feat.read_resource("file:///empty")
        assert result.content == ""
        assert result.is_binary is False

    async def test_read_resource_failure_raises(self) -> None:
        session = _session()
        session.read_resource.side_effect = RuntimeError("boom")
        feat = McpResourcesFeature()
        await feat.initialize(session, "github")
        with pytest.raises(RuntimeError, match="boom"):
            await feat.read_resource("file:///a")

    def test_format_resources_list(self) -> None:
        session = _session()
        session.list_resources.return_value = SimpleNamespace(
            resources=[self._resource()]
        )
        session.list_resource_templates.return_value = SimpleNamespace(resourceTemplates=[])
        feat = McpResourcesFeature()
        import asyncio

        asyncio.run(feat.initialize(session, "github"))
        text = feat.format_resources_list()
        assert "file:///readme.md" in text
        assert "**Static Resources:**" in text


class TestMcpPromptsFeature:
    def _prompt(self, name="p1", args=None):
        return SimpleNamespace(name=name, description="d", arguments=args or [])

    async def test_initialize_and_list(self) -> None:
        session = _session()
        session.list_prompts.return_value = SimpleNamespace(prompts=[self._prompt()])
        feat = McpPromptsFeature()
        await feat.initialize(session, "github")
        assert len(feat.get_prompts()) == 1

    async def test_initialize_unsupported(self) -> None:
        session = _session()
        session.list_prompts.side_effect = RuntimeError("not supported")
        feat = McpPromptsFeature()
        await feat.initialize(session, "github")
        assert feat.get_prompts() == []

    async def test_get_prompt_text(self) -> None:
        session = _session()
        msg = SimpleNamespace(
            role="user",
            content=SimpleNamespace(type="text", text="hello"),
        )
        session.get_prompt.return_value = SimpleNamespace(
            name="p1", description="d", messages=[msg]
        )
        feat = McpPromptsFeature()
        await feat.initialize(session, "github")
        result = await feat.get_prompt("p1", {"x": "1"})
        assert result.messages[0].content == "hello"
        assert result.messages[0].content_type == "text"

    async def test_get_prompt_image(self) -> None:
        session = _session()
        msg = SimpleNamespace(
            role="assistant",
            content=SimpleNamespace(type="image", data="base64data", mimeType="image/png"),
        )
        session.get_prompt.return_value = SimpleNamespace(
            name="p1", description=None, messages=[msg]
        )
        feat = McpPromptsFeature()
        await feat.initialize(session, "github")
        result = await feat.get_prompt("p1")
        assert result.messages[0].content_type == "image"
        assert result.messages[0].mime_type == "image/png"

    async def test_get_prompt_resource(self) -> None:
        session = _session()
        resource = SimpleNamespace(text="file text", uri="file:///a")
        msg = SimpleNamespace(
            role="user",
            content=SimpleNamespace(type="resource", resource=resource),
        )
        session.get_prompt.return_value = SimpleNamespace(
            name="p1", description=None, messages=[msg]
        )
        feat = McpPromptsFeature()
        await feat.initialize(session, "github")
        result = await feat.get_prompt("p1")
        assert result.messages[0].content_type == "resource"
        assert result.messages[0].resource_uri == "file:///a"

    async def test_get_prompt_failure_raises(self) -> None:
        session = _session()
        session.get_prompt.side_effect = RuntimeError("boom")
        feat = McpPromptsFeature()
        await feat.initialize(session, "github")
        with pytest.raises(RuntimeError, match="boom"):
            await feat.get_prompt("p1")

    def test_format_prompts_list(self) -> None:
        session = _session()
        session.list_prompts.return_value = SimpleNamespace(
            prompts=[self._prompt("p1", [SimpleNamespace(name="a", required=True, description="desc")])]
        )
        feat = McpPromptsFeature()
        import asyncio

        asyncio.run(feat.initialize(session, "github"))
        text = feat.format_prompts_list()
        assert "p1" in text
        assert "`a`" in text

    def test_find_prompt(self) -> None:
        feat = McpPromptsFeature()
        feat._prompts = [self._prompt("p1")]
        assert feat.find_prompt("p1") is not None
        assert feat.find_prompt("missing") is None
