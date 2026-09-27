"""React system-prompt assembly unit tests — static + dynamic blocks, variants."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.context.manager import ContextManager, EvoContext
from app.core.context.schemas import ContextMetadata


def _ctx(**meta_kwargs) -> EvoContext:
    return EvoContext(
        working_directory="/work",
        project_id=9,
        metadata=ContextMetadata(**meta_kwargs),
    )


# ---------------------------------------------------------------------------
# _environment_block
# ---------------------------------------------------------------------------


def test_environment_block_includes_wd_platform_and_project():
    from app.core.engine.react.prompts import _environment_block

    block = _environment_block(_ctx(), SimpleNamespace())
    assert "工作目录: /work" in block
    assert any(line.startswith("平台: ") for line in block.splitlines())
    assert "项目 ID: 9" in block


def test_environment_block_without_project_and_with_plan():
    from app.core.engine.react.prompts import _environment_block

    plain = _environment_block(EvoContext(working_directory="/w"), SimpleNamespace())
    assert "项目 ID" not in plain

    state = SimpleNamespace(structured_plan="阶段计划")
    with_plan = _environment_block(_ctx(), state)
    assert "当前计划: 阶段计划" in with_plan


# ---------------------------------------------------------------------------
# _capability_index
# ---------------------------------------------------------------------------


def test_capability_index_renders_skills_macros():
    from app.core.engine.react.prompts import _capability_index

    ctx = _ctx(
        active_skills="站内搜索\n- 代码审查\n  文件主题",
        active_macros="- build.sh",
    )
    out = _capability_index(ctx)
    assert "<available_skills>" in out
    assert "- 站内搜索" in out
    assert "- 代码审查" in out
    assert "- 文件主题" in out
    assert "<available_macros>" in out
    assert "- build.sh" in out
    assert "<operation_map>" not in out


def test_capability_index_caps_skills_and_macros():
    from app.core.engine.react.prompts import MAX_MACROS, MAX_SKILLS, _capability_index

    many_skills = "\n".join(f"- skill {i}" for i in range(50))
    many_macros = "\n".join(f"- macro {i}" for i in range(30))
    ctx = _ctx(active_skills=many_skills, active_macros=many_macros)
    out = _capability_index(ctx)

    skill_block = out.split("<available_skills>")[1].split("</available_skills>")[0]
    macro_block = out.split("<available_macros>")[1].split("</available_macros>")[0]
    assert len(skill_block.strip().splitlines()) == MAX_SKILLS
    assert len(macro_block.strip().splitlines()) == MAX_MACROS


def test_capability_index_empty_fallback():
    from app.core.engine.react.prompts import _capability_index

    assert _capability_index(_ctx()) == "（当前无按需加载的能力索引）"


def test_capability_index_formats_structured_macros():
    """结构化宏索引（list_active_macro_index 返回 list[dict]）逐行渲染，
    不得把 Python repr（id/entity/risk_tier dict）注入 prompt。"""
    from app.core.engine.react.prompts import _capability_index

    ctx = _ctx(
        active_macros=[
            {
                "id": 3800,
                "name": "打开藏宝阁",
                "description": "打开 App\n导航列表页",
                "entity": "",
                "risk_tier": "act",
            },
            {
                "id": 3801,
                "name": "抓取列表",
                "description": "采集卡片",
                "entity": "",
                "risk_tier": "act",
            },
        ]
    )
    out = _capability_index(ctx)
    assert "- 打开藏宝阁: 打开 App 导航列表页" in out
    assert "- 抓取列表: 采集卡片" in out
    assert "risk_tier" not in out and "'id': 3800" not in out


def test_capability_index_legacy_macro_string_still_supported():
    from app.core.engine.react.prompts import _capability_index

    ctx = _ctx(active_macros="- build.sh: 构建脚本")
    out = _capability_index(ctx)
    assert "- build.sh: 构建脚本" in out


# ---------------------------------------------------------------------------
# _capability_index_async
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capability_index_async_appends_agents():
    from app.core.engine.react.prompts import _capability_index_async

    ctx = _ctx(active_skills="- 代码审查")
    with patch(
        "app.core.engine.react.prompts._available_agents_block",
        AsyncMock(return_value="agent-a\nagent-b"),
    ):
        out = await _capability_index_async(ctx)

    assert "agent-a" in out
    assert "<available_agents>" in out
    assert "代码审查" in out


@pytest.mark.asyncio
async def test_capability_index_async_truncates_long_agent_index():
    from app.core.engine.react.prompts import MAX_AGENTS, _capability_index_async

    ctx = _ctx(active_skills="- 代码审查")
    long_agents = "device " * 2000  # 12000 chars
    with patch(
        "app.core.engine.react.prompts._available_agents_block",
        AsyncMock(return_value=long_agents),
    ):
        out = await _capability_index_async(ctx)

    agents_block = (
        out.split("<available_agents>")[1].split("</available_agents>")[0].strip()
    )
    assert len(agents_block) <= MAX_AGENTS * 200


@pytest.mark.asyncio
async def test_capability_index_async_fallback_with_no_static_no_agents():
    from app.core.engine.react.prompts import _capability_index_async

    with patch(
        "app.core.engine.react.prompts._available_agents_block",
        AsyncMock(return_value=""),
    ):
        out = await _capability_index_async(_ctx())
    assert out == "（当前无按需加载的能力索引）"


# ---------------------------------------------------------------------------
# _available_agents_block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_available_agents_block_caches_within_ttl():
    from app.core.engine.react import prompts

    prompts._agents_cache = (0.0, None)
    with patch(
        "app.core.engine.tools.a2a.list_available_agents",
        AsyncMock(return_value="dev1\ndev2"),
    ) as fetch:
        first = await prompts._available_agents_block()
        second = await prompts._available_agents_block()

    assert first == "dev1\ndev2"
    assert second == "dev1\ndev2"
    assert fetch.await_count == 1


def test_available_agents_block_returns_cached_entry_directly():
    from app.core.engine.react import prompts

    prompts._agents_cache = (time.monotonic(), "cached-index")
    with patch("app.core.engine.tools.a2a.list_available_agents", AsyncMock()) as fetch:
        import asyncio

        text = asyncio.run(prompts._available_agents_block())
    assert text == "cached-index"
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_available_agents_block_fetch_failure_returns_empty():
    from app.core.engine.react import prompts

    prompts._agents_cache = (0.0, None)
    with patch(
        "app.core.engine.tools.a2a.list_available_agents",
        AsyncMock(side_effect=RuntimeError("gateway down")),
    ) as fetch:
        text = await prompts._available_agents_block()

    assert text == ""
    fetch.assert_awaited_once()


# ---------------------------------------------------------------------------
# _memory_block
# ---------------------------------------------------------------------------


def test_memory_block_hot_and_episodes():
    from app.core.engine.react.prompts import _memory_block

    block = _memory_block(
        _ctx(
            core_memory_raw="团队规范：使用中文",
            episodic_memory_raw="上周完成数据库迁移",
        )
    )
    assert "【热记忆】" in block
    assert "团队规范：" in block
    assert "【近期剧集】" in block
    assert "上周完成数据库迁移" in block


def test_memory_block_only_hot():
    from app.core.engine.react.prompts import _memory_block

    block = _memory_block(_ctx(core_memory_raw="hot"))
    assert "【热记忆】" in block
    assert "【近期剧集】" not in block


def test_memory_block_fallback():
    from app.core.engine.react.prompts import _memory_block

    block = _memory_block(_ctx())
    assert "（无热记忆" in block


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,expected_variant",
    [
        ("voice", "core/agent/main.voice.txt"),
        ("duty", "core/agent/main.duty.txt"),
        ("wecom_duty", "core/agent/main.duty.txt"),
        ("chat", None),
    ],
)
async def test_build_system_prompt_channel_variants(source, expected_variant):
    from app.core.engine.react.prompts import build_system_prompt

    def fake_render(path, placeholders=None):
        if path == "core/agent/main.txt":
            env = placeholders["environment_block"]
            cap = placeholders["capability_index"]
            mem = placeholders["memory_block"]
            return f"MAIN|env={env}|cap={cap}|mem={mem}"
        return f"VARIANT:{path}"

    exists = {
        "core/agent/main.voice.txt": True,
        "core/agent/main.duty.txt": True,
    }

    ctx = _ctx(source=source)
    with (
        patch("app.core.engine.react.prompts.render_prompt", side_effect=fake_render),
        patch(
            "app.core.engine.react.prompts.prompt_exists",
            side_effect=lambda p: exists.get(p, False),
        ),
    ):
        with ContextManager.use(ctx):
            main = await build_system_prompt(SimpleNamespace(), {})

    assert main.startswith("MAIN|")
    assert "（当前无按需加载的能力索引）" in main
    if expected_variant:
        assert f"VARIANT:{expected_variant}" in main
    else:
        assert "VARIANT:" not in main


@pytest.mark.asyncio
async def test_build_system_prompt_variant_requires_existing_template():
    from app.core.engine.react.prompts import build_system_prompt

    def fake_render(path, _placeholders=None):
        return f"RENDERED:{path}"

    ctx = _ctx(source="voice")
    with (
        patch("app.core.engine.react.prompts.render_prompt", side_effect=fake_render),
        patch("app.core.engine.react.prompts.prompt_exists", return_value=False),
    ):
        with ContextManager.use(ctx):
            main = await build_system_prompt(SimpleNamespace(), {})

    assert "RENDERED:core/agent/main.voice.txt" not in main
    assert main == "RENDERED:core/agent/main.txt"
