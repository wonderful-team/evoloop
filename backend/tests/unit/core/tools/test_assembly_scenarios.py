"""渐进式工具装配场景验收（2026-09-18）。

用代表性原生工具名做静态面，验证三类会话形态下 ToolManager 的真实装配面：
A. 内嵌 mall 会话（host_declared 域信号）          → 域 profile 收窄面
B. 会话无域信号、已加载的包未声明 capability.domain（普通技能）
   → 全量（零回归兜底：没有域信号就不猜）。
   注：包声明了域的情形走自动识别（test_auto_identify_floor.py）——
   skill 激活即反哺 session_domain，下一轮按域面收窄 + 已用工具保底。
C. 桌面会话 + 项目级 fallback.native_tools（opt-in）→ 项目自定义保留面

B 是有意保留的零回归兜底：域信号缺失时宁可全量也不误裁——
消除 B 的唯一正道是给会话补域信号（host_declared / 分类器 / 包反哺），不是改兜底。
"""

from __future__ import annotations

import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.context.schemas import ContextMetadata
from app.core.engine.state import AgentState

# agent_main.yaml react 面的代表子集（含本验收关心的 mobile/desktop）
FULL_FACE = {
    "bash", "read", "glob", "grep", "edit", "write", "task",
    "webfetch", "websearch", "plan", "tasks", "skill", "question",
    "browser", "image", "video", "mobile", "desktop", "vault", "macro",
}
MALL_FACE = {"webfetch", "websearch", "plan", "skill", "question", "tasks"}


def _native_tool(name: str):
    t = MagicMock()
    t.name = name
    t.metadata = {}
    return t


def _setup(monkeypatch, tmp_path, metadata: ContextMetadata):
    from app.core.engine.capability_profiles import reload as reload_profiles
    from app.core.tools.manager import tool_manager

    reload_profiles(str(tmp_path))

    ctx = MagicMock()
    ctx.metadata = metadata
    ctx.working_directory = str(tmp_path)
    monkeypatch.setattr(
        "app.core.context.ContextManager.current", staticmethod(lambda: ctx)
    )
    import app.core.tools.registry as registry_mod

    monkeypatch.setattr(
        registry_mod, "get_agent_tools", lambda agent: [_native_tool(n) for n in FULL_FACE]
    )
    monkeypatch.setattr(
        "app.infrastructure.config.service.SystemConfigService",
        MagicMock(get_value=staticmethod(lambda k: "vision-model")),
    )
    return tool_manager


@pytest.mark.asyncio
async def test_scenario_a_embedded_mall_with_domain_signal(tmp_path, monkeypatch):
    """A：域信号存在（host_declared mall_ops）→ 装配 6 工具域面。

    会话工作区无 profile，经包归属项目回退命中 mall-backend 的 mall_ops profile。
    """
    home = tmp_path / "mall-backend"
    (home / ".evoloop").mkdir(parents=True)
    (home / ".evoloop" / "capability_profiles.yaml").write_text(
        "domains:\n  mall_ops:\n    native_tools: [webfetch, websearch, plan, skill, question, tasks]\n",
        encoding="utf-8",
    )
    session = tmp_path / "session-project"
    session.mkdir()

    tool_manager = _setup(
        monkeypatch,
        session,
        ContextMetadata(intent_hint=SimpleNamespace(domain="mall_ops")),
    )
    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_packages_for_domain",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    resource_path=str(home / ".evoloop" / "skills" / "mall-products")
                )
            ]
        ),
    )

    tools = await tool_manager.get_agent_tools("react", state=AgentState())
    names = {t.name for t in tools}
    assert names == MALL_FACE
    assert "mobile" not in names and "desktop" not in names and "bash" not in names


@pytest.mark.asyncio
async def test_scenario_b_desktop_session_without_domain_signal(tmp_path, monkeypatch):
    """B（现状边界）：无域信号 + 已加载 mall 包 → 全量装配（含 mobile/desktop）。

    这就是用户日志会话的形态：skill(mall-products) 加载成功，但包不反哺域
    信号（设计如此，防混合会话被误裁），profile 无从生效 → 零回归全量。
    """
    tool_manager = _setup(
        monkeypatch, tmp_path, ContextMetadata(loaded_packages=["mall-products"])
    )
    # 密封性：包 capability 查询不落 DB（与 test_capability_packages 同法）
    monkeypatch.setattr(
        "app.core.learning.skills.discovery.skill_discovery.get_capability",
        AsyncMock(return_value=None),
    )

    tools = await tool_manager.get_agent_tools("react", state=AgentState())
    names = {t.name for t in tools}
    assert names == FULL_FACE
    assert {"mobile", "desktop"} <= names


@pytest.mark.asyncio
async def test_scenario_c_desktop_session_with_project_fallback_policy(tmp_path, monkeypatch):
    """C：项目 opt-in fallback.native_tools → 无域信号也按项目白名单装配。"""
    (tmp_path / ".evoloop").mkdir()
    (tmp_path / ".evoloop" / "capability_profiles.yaml").write_text(
        textwrap.dedent(
            """\
            domains: {}
            fallback:
              native_tools: [bash, read, glob, grep, edit, write, task,
                             webfetch, websearch, plan, skill, question,
                             mobile, desktop, macro]
            """
        ),
        encoding="utf-8",
    )
    tool_manager = _setup(monkeypatch, tmp_path, ContextMetadata(loaded_packages=["mall-products"]))

    tools = await tool_manager.get_agent_tools("react", state=AgentState())
    names = {t.name for t in tools}
    # 全量 20 - {tasks, browser, image, video, vault} = 项目白名单 15
    assert names == FULL_FACE - {"tasks", "browser", "image", "video", "vault"}
    assert {"mobile", "desktop"} <= names  # 藏宝阁场景保留具身工具
