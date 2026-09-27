"""能力包契约测试（capability-packages-refactor.md §9）。

S1 引擎差量的锁定面：
1. 包格式：capability frontmatter 归一化、缺省降级、requires.tools 隔离；
2. 挂载联动：resolve_skill 返回 capability；react_skill 工具加载包时
   ensure_connected + 包名并入 ctx.metadata.loaded_packages（幂等）；
3. 可见性：(server, tool) 二元组过滤——预挂/加载包的工具可见、未声明
   的工具不可见、include 缺省 = server 全量、无包 = 全量兼容（零回归）；
4. 索引：包条目带 [capability package] 标记；渲染层标注已挂载包。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.learning.skills.validator import SkillValidator

MD = "---\nname: {name}\ndescription: {desc}\n{frontmatter}---\n\nbody\n"


def _make_skill(tmp_path: Path, frontmatter: str, name: str, desc: str = "d") -> Path:
    folder = tmp_path / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(MD.format(name=name, desc=desc, frontmatter=frontmatter))
    return folder


class TestPackageFormat:
    """契约 §9.1：capability 键归一化与降级。"""

    def test_full_package_frontmatter(self, tmp_path) -> None:
        folder = _make_skill(
            tmp_path,
            """capability:
  domain: mall_ops
  tools:
    - mcp_server: capability-matrix
      include: [list_orders, query_order]
    - mcp_server: mall-backend-ext
      include: []
  preload: true
  route_patterns: [order]
""",
            "mall-orders",
        )
        result = SkillValidator.validate_folder(folder)
        assert result.is_valid
        cap = SkillValidator._normalize_capability(result.metadata.get("capability"))
        assert cap["domain"] == "mall_ops"
        assert cap["tools"] == [
            {"mcp_server": "capability-matrix", "include": ["list_orders", "query_order"]},
            {"mcp_server": "mall-backend-ext", "include": []},
        ]
        assert cap["preload"] is True
        assert cap["route_patterns"] == ["order"]

    def test_malformed_tools_entries_dropped(self, tmp_path) -> None:
        folder = _make_skill(
            tmp_path,
            """capability:
  tools:
    - mcp_server: " "
    - "not-a-dict"
    - mcp_server: ok-server
""",
            "bad-pkg",
        )
        metadata, _ = SkillValidator._parse_skill_md(folder / "SKILL.md")
        cap = SkillValidator._normalize_capability(metadata.get("capability"))
        # 非法 entry 被丢弃；仅保留合法 server 且无 include → 全 server 语义
        assert cap == {"tools": [{"mcp_server": "ok-server"}]}

    def test_plain_skill_degrades_to_none(self, tmp_path) -> None:
        folder = _make_skill(tmp_path, "", "plain-skill")
        metadata, _ = SkillValidator._parse_skill_md(folder / "SKILL.md")
        assert SkillValidator._normalize_capability(metadata.get("capability")) is None
        # requires.tools 不受污染：仍走原生工具依赖路径
        folder2 = _make_skill(
            tmp_path,
            "requires:\n  tools: [bash, read]\n",
            "plain-requires",
        )
        metadata2, _ = SkillValidator._parse_skill_md(folder2 / "SKILL.md")
        assert SkillValidator._normalize_capability(metadata2.get("capability")) is None


class TestPackageVisibility:
    """契约 §9.3/9.4：(server, tool) 二元组可见性。"""

    def _mcp_tool(self, name: str):
        t = MagicMock()
        t.name = name
        return t

    @pytest.mark.asyncio
    async def test_loaded_package_scopes_surface(self, monkeypatch) -> None:
        """加载 mall-orders 后：core 订单工具 + ext oms 工具可见；商品/社媒不可见。"""
        from app.core.context.schemas import ContextMetadata
        from app.core.tools.manager import tool_manager

        ctx = MagicMock()
        ctx.metadata = ContextMetadata(loaded_packages=["mall-orders"])
        monkeypatch.setattr(
            "app.core.context.ContextManager.current", staticmethod(lambda: ctx)
        )
        monkeypatch.setattr(
            type(tool_manager),
            "_resolve_domain_profile",
            staticmethod(lambda: None),
        )

        async def fake_get_capability(name: str):
            if name != "mall-orders":
                return None
            return {
                "tools": [
                    {"mcp_server": "capability-matrix", "include": ["list_orders", "query_order"]},
                    {"mcp_server": "mall-backend-ext", "include": ["oms_ship_order"]},
                ]
            }

        monkeypatch.setattr(
            "app.core.learning.skills.discovery.skill_discovery.get_capability",
            fake_get_capability,
        )

        all_mcp = [
            self._mcp_tool("mcp__capability-matrix__list_orders"),
            self._mcp_tool("mcp__capability-matrix__list_goods"),  # 同 server 未声明
            self._mcp_tool("mcp__mall-backend-ext__oms_ship_order"),
            self._mcp_tool("mcp__mall-backend-ext__channel_publish_now"),
            self._mcp_tool("mcp__other-server__free_tool"),  # 未涉及 server
        ]

        # ToolManager.get_agent_tools 内部通过模块顶层 import 引用，这里打补丁
        fake_manager = MagicMock()
        fake_manager.aget_all_tools = AsyncMock(return_value=all_mcp)
        monkeypatch.setattr(
            "app.core.mcp.mcp_client_manager", fake_manager
        )

        monkeypatch.setattr(
            "app.core.tools.registry.get_agent_tools", lambda agent: []
        )
        monkeypatch.setattr(
            "app.infrastructure.config.service.SystemConfigService",
            MagicMock(get_value=staticmethod(lambda k: None)),
        )

        from app.core.engine.state import AgentState

        tools = await tool_manager.get_agent_tools("react", state=AgentState())
        names = {t.name for t in tools}

        assert "mcp__capability-matrix__list_orders" in names
        assert "mcp__mall-backend-ext__oms_ship_order" in names
        # 跨 server 归属 + 连接/可见性分离核心断言
        assert "mcp__capability-matrix__list_goods" not in names
        assert "mcp__mall-backend-ext__channel_publish_now" not in names
        assert "mcp__other-server__free_tool" not in names

    @pytest.mark.asyncio
    async def test_no_packages_full_surface(self, monkeypatch) -> None:
        """零回归锁：无 loaded_packages → 全量注入（现状行为）。"""
        from app.core.context.schemas import ContextMetadata
        from app.core.tools.manager import tool_manager

        ctx = MagicMock()
        ctx.metadata = ContextMetadata()
        monkeypatch.setattr(
            "app.core.context.ContextManager.current", staticmethod(lambda: ctx)
        )
        monkeypatch.setattr(
            type(tool_manager), "_resolve_domain_profile", staticmethod(lambda: None)
        )

        all_mcp = [
            self._mcp_tool("mcp__a__t1"),
            self._mcp_tool("mcp__b__t2"),
        ]
        fake_manager = MagicMock()
        fake_manager.aget_all_tools = AsyncMock(return_value=all_mcp)
        monkeypatch.setattr("app.core.mcp.mcp_client_manager", fake_manager)
        monkeypatch.setattr("app.core.tools.registry.get_agent_tools", lambda agent: [])

        from app.core.engine.state import AgentState

        tools = await tool_manager.get_agent_tools("react", state=AgentState())
        names = {t.name for t in tools}
        assert names == {"mcp__a__t1", "mcp__b__t2"}

    @pytest.mark.asyncio
    async def test_include_empty_means_full_server(self, monkeypatch) -> None:
        """include 空 = server 全量（ext 兜底语义）。"""
        from app.core.context.schemas import ContextMetadata
        from app.core.tools.manager import tool_manager

        ctx = MagicMock()
        ctx.metadata = ContextMetadata(loaded_packages=["ext-all"])
        monkeypatch.setattr(
            "app.core.context.ContextManager.current", staticmethod(lambda: ctx)
        )
        monkeypatch.setattr(
            type(tool_manager), "_resolve_domain_profile", staticmethod(lambda: None)
        )
        monkeypatch.setattr(
            "app.core.learning.skills.discovery.skill_discovery.get_capability",
            AsyncMock(
                return_value={"tools": [{"mcp_server": "mall-backend-ext"}]}
            ),
        )

        all_mcp = [
            self._mcp_tool("mcp__mall-backend-ext__oms_a"),
            self._mcp_tool("mcp__mall-backend-ext__oms_b"),
            self._mcp_tool("mcp__mall-backend-ext__channel_x"),
        ]
        fake_manager = MagicMock()
        fake_manager.aget_all_tools = AsyncMock(return_value=all_mcp)
        monkeypatch.setattr("app.core.mcp.mcp_client_manager", fake_manager)
        monkeypatch.setattr("app.core.tools.registry.get_agent_tools", lambda agent: [])

        from app.core.engine.state import AgentState

        tools = await tool_manager.get_agent_tools("react", state=AgentState())
        assert {t.name for t in tools} == {t.name for t in all_mcp}


class TestPackageIndex:
    """契约：索引条目标记与渲染标注。"""

    def test_capability_package_flagged_in_index_description(self) -> None:
        skill = MagicMock()
        skill.description = "订单查询"
        skill.capability = {"domain": "mall_ops", "tools": []}
        plain = MagicMock()
        plain.description = "普通技能"
        plain.capability = None

        assert "[capability package]" in skill_discovery_index(skill)
        assert "[capability package]" not in skill_discovery_index(plain)


def skill_discovery_index(skill) -> str:
    from app.core.learning.skills.discovery import SkillDiscovery

    return SkillDiscovery._index_description(skill)
