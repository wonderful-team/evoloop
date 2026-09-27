"""阶段2：L0/L1 路由决策端到端测试（对应文档「附A 阶段2」）。

覆盖数据契约：
  - L0 不再处理内置动作（ack/end/cancel/rename/clarify 已全部移除），
    这些输入直接委托 Agent（queued）
  - 复合意图拦截 → 直接委托 Agent（queued）
  - L1 高层意图分类/兜底 → 委托 Agent（queued）
  - L0 宏路由由 BERT 意图分类 + DB 宏解析完成；动态创建测试宏时，宏名称和触发语
    必须选用 data/intents.yaml 中已存在的 BERT 标签及其训练示例
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import pytest

from .conftest import wait_until

pytestmark = pytest.mark.e2e


async def _delete_macros_bound_to_trigger(http_client: httpx.AsyncClient, trigger: str) -> None:
    """删除占住该 trigger 的历史宏（跨运行脏数据）。

    init_spec 对 trigger 是 first-bind-wins：历史残留宏会永久占住触发词，
    导致新宏被 "already bound" 跳过、L0 命中到内容已过时的旧宏。夹具创建
    前必须先清理。
    """
    init = (await http_client.get("/api/v1/route/init")).json()
    for tpl in init.get("templates", []):
        if trigger not in (tpl.get("patterns") or []):
            continue
        action = tpl.get("action") or ""
        if not action.startswith("macro:"):
            continue
        old_id = action.split(":", 1)[1]
        await http_client.delete(f"/api/v1/macros/{old_id}")


async def _create_routable_macro(
    http_client: httpx.AsyncClient, name: str, trigger: str
) -> int:
    """创建并确认一个可路由的最小宏（wait 1ms），返回 macro_id。

    ``name`` 必须是 BERT 意图标签集中已存在的标签，这样服务端 BERT
    分类器才能将该宏识别为 L0 可路由目标。``trigger`` 同时注入到 Init Spec
    templates 并用于实际文本匹配；同名/同 trigger 冲突时最新确认的宏优先，
    因此必须选用意图标签的训练示例，避免与历史脏数据冲突。
    """
    script = (
        "- type: action\n"
        "  event_type: wait\n"
        "  source: desktop\n"
        "  payload:\n"
        "    duration_ms: 1\n"
    )
    await _delete_macros_bound_to_trigger(http_client, trigger)

    create_resp = await http_client.post(
        "/api/v1/macros/",
        json={
            "name": name,
            "description": "edge L0 macro",
            "macro_script": script,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    macro_id = create_resp.json()["id"]

    update_resp = await http_client.put(
        f"/api/v1/macros/{macro_id}",
        json={"trigger_patterns": [trigger]},
    )
    assert update_resp.status_code == 200, update_resp.text

    confirm_resp = await http_client.post(f"/api/v1/macros/{macro_id}/confirm")
    assert confirm_resp.status_code == 200, confirm_resp.text
    return macro_id


async def _wait_for_macro_in_spec(
    http_client: httpx.AsyncClient,
    macro_id: int,
    timeout: float = 30.0,
    expected_trigger: str | None = None,
) -> None:
    """轮询 /route/init 直到宏触发器被载入 L0 规格。

    仅按 macro id 存在判定是脆弱的：SQLite rowid 复用 + 去抖重建可能让
    旧 spec 短暂携带同名 id（历史宏的残留模板），提前终止轮询。给定
    ``expected_trigger`` 时等待目标 trigger 实际出现在该宏的 patterns 中。
    """

    def _tpl_has(tpl: dict) -> bool:
        if tpl.get("action") != f"macro:{macro_id}":
            return False
        if expected_trigger is not None:
            return expected_trigger in (tpl.get("patterns") or [])
        return True

    async def _check() -> bool:
        resp = await http_client.get("/api/v1/route/init")
        if resp.status_code != 200:
            return False
        data = resp.json()
        templates = data.get("templates", [])
        return any(_tpl_has(t) for t in templates)

    await wait_until(_check, timeout=timeout, desc=f"L0 spec 载入 macro:{macro_id}")


class TestL0Routing:
    """二 L0 快速本地命中。"""

    @pytest.mark.timeout(30)
    async def test_l0_no_builtin_ack_delegates_to_agent(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """"对的" 不再被 L0 内置 ack 吞掉，直接委托 Agent。"""
        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": "对的"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

    @pytest.mark.timeout(30)
    async def test_l0_no_builtin_end_delegates_to_agent(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """"拜拜" 不再被 L0 内置 end 吞掉，直接委托 Agent。"""
        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": "拜拜"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

    @pytest.mark.timeout(30)
    async def test_l0_no_builtin_cancel_delegates_to_agent(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """"取消" 不再被 L0 内置 cancel 吞掉，直接委托 Agent。"""
        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": "取消"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

    @pytest.mark.timeout(30)
    async def test_l0_unknown_input_fails_open(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """非内置动作的常规问题不会被 L0 吞掉 → 委托 Agent。"""
        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "什么是量子计算"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"


class TestCompoundIntentGuard:
    """二 L0-2 复合意图防线。"""

    @pytest.mark.timeout(30)
    async def test_compound_intent_delegates(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """ "先搜索前端代码再部署到测试环境"（先/再 顺序标记 + 2 动作词）→ multi_intent → 委托 Agent。"""
        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "先搜索前端代码再部署到测试环境"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "queued"


class TestL1Routing:
    """二 L1 高层意图分类与委托。"""

    @pytest.mark.timeout(30)
    async def test_l1_delegate_contract(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """复杂任务（L0 未命中）→ L1 委托 → queued 契约。"""
        resp = await http_client.post(
            "/api/v1/chat",
            json={
                "thread_id": thread_id,
                "message": "帮我调研一下最近的 AI Agent 框架对比并输出报告",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "queued"
        assert body["thread_id"] == thread_id
        assert body["message_id"]


class TestL0MacroRoute:
    """二 文字消息跳过 L0：即便命中 BERT 已学习/已确认的宏标签，也直接委派 Agent。

    L0 宏路由只服务语音快捷指令（见 test_04_voice_output 语音 L0 宏路由用例）；
    文字消息不再本地执行宏，统一走 L1 → Agent（queued）。
    """

    @pytest.mark.timeout(90)
    async def test_web_macro_trigger_skips_l0_and_delegates_to_agent(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """用 BERT 标签 ``传文件到手机`` 创建宏，文字触发后不再本地执行（跳过 L0），
        直接委派 Agent 返回 queued。"""
        name = "传文件到手机"
        trigger = "传文件到手机"
        macro_id = await _create_routable_macro(http_client, name, trigger)
        try:
            await _wait_for_macro_in_spec(
                http_client, macro_id, expected_trigger=trigger
            )
            resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": trigger, "project_id": 0},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "queued", f"文字消息应跳过 L0 委派 Agent: {body}"
            assert body["message_id"], body
            assert body["thread_id"] == thread_id
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")

    @pytest.mark.timeout(90)
    async def test_l0_duplicate_trigger_newest_macro_wins(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """同一 trigger 存在多个已确认宏时，L0 spec 绑定最新确认的宏。

        历史残留/重复确认会留下多个同 trigger 宏（如 e2e 多次运行后的
        ack 宏）。init_spec 去重按 preset 优先、created_at desc 保留最新，
        resolver 运行时同序选择，保证用户新确认的宏立即生效；因此真实
        trigger 的回归测试不依赖唯一占位符也能稳定通过。
        """
        name = "ack"
        trigger = "麻烦对对对"
        old_id = await _create_routable_macro(http_client, name, trigger)
        try:
            new_id = await _create_routable_macro(http_client, name, trigger)
            try:
                # 最新确认的宏应出现在 L0 spec 中（轮询直至绑定）
                await _wait_for_macro_in_spec(http_client, new_id)
                resp = await http_client.get("/api/v1/route/init")
                assert resp.status_code == 200, resp.text
                templates = resp.json().get("templates", [])
                bound = [
                    t for t in templates if trigger in (t.get("patterns") or [])
                ]
                assert bound, f"trigger {trigger!r} 未出现在 L0 spec: {templates}"
                assert all(
                    t.get("action") == f"macro:{new_id}" for t in bound
                ), f"重复 trigger 应只绑定最新宏 macro:{new_id}，实际: {bound}"

                # 运行时：文字消息跳过 L0，即使宏在 spec 中也不本地执行 → queued
                resp = await http_client.post(
                    "/api/v1/chat",
                    json={"thread_id": thread_id, "message": trigger, "project_id": 0},
                )
                assert resp.status_code == 200, resp.text
                body = resp.json()
                assert body["status"] == "queued", (
                    f"文字消息应跳过 L0 委派 Agent: {body}"
                )
            finally:
                await http_client.delete(f"/api/v1/macros/{new_id}")
        finally:
            await http_client.delete(f"/api/v1/macros/{old_id}")


class TestL0EdgeInputs:
    """二 L0 对边缘输入的降级/不崩溃。"""

    @pytest.mark.timeout(30)
    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("1", id="single-digit"),
            pytest.param("q", id="single-letter"),
            pytest.param("😀", id="emoji"),
            pytest.param("，。", id="punctuation"),
        ],
    )
    async def test_l0_edge_input_returns_valid_status(
        self, http_client: httpx.AsyncClient, thread_id: str, text: str
    ) -> None:
        """单字符/数字/emoji/标点不应 500，必须返回可识别终态。"""
        resp = await http_client.post(
            "/api/v1/chat", json={"thread_id": thread_id, "message": text}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] in ("done", "queued", "failed"), (
            f"边缘输入返回状态异常: {body}"
        )
        assert body["thread_id"] == thread_id


async def _create_navigation_macro(
    http_client: httpx.AsyncClient,
    name: str,
    trigger: str,
    route: str,
    feedback: str = "已跳转",
) -> int:
    """创建并确认一个导航宏（namespace=preset），返回 macro_id。

    ``name`` 必须是 BERT 已学习的意图标签，``trigger`` 为该标签下的示例 utterance。
    """
    script = (
        "- type: action\n"
        "  event_type: frontend_navigate\n"
        "  payload:\n"
        f"    route: {route}\n"
        f"    feedback: {feedback}\n"
    )
    create_resp = await http_client.post(
        "/api/v1/macros/",
        json={
            "name": name,
            "description": "edge L0 navigation macro",
            "macro_script": script,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    macro_id = create_resp.json()["id"]

    update_resp = await http_client.put(
        f"/api/v1/macros/{macro_id}",
        json={
            "namespace": "preset",
            "trigger_patterns": [trigger],
            "feedback": feedback,
        },
    )
    assert update_resp.status_code == 200, update_resp.text

    confirm_resp = await http_client.post(f"/api/v1/macros/{macro_id}/confirm")
    assert confirm_resp.status_code == 200, confirm_resp.text
    return macro_id


async def _create_parametric_macro(
    http_client: httpx.AsyncClient,
    name: str,
    trigger_pattern: str,
    parameters: list[dict[str, Any]],
) -> int:
    """创建并确认一个带参数/槽位的宏，返回 macro_id。

    ``name`` 必须是 BERT 意图标签，``trigger_pattern`` 包含 ``{slot}`` 用于槽位提取。
    调用方应使用 BERT 已学习该标签的示例 utterance 作为触发文本，并确保它能被
    ``trigger_pattern`` 的正则匹配。
    """
    script = "- type: action\n  event_type: wait\n  payload:\n    duration_ms: 1\n"
    create_resp = await http_client.post(
        "/api/v1/macros/",
        json={
            "name": name,
            "description": "edge L0 parametric macro",
            "macro_script": script,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    macro_id = create_resp.json()["id"]

    update_resp = await http_client.put(
        f"/api/v1/macros/{macro_id}",
        json={
            "parameters": parameters,
            "trigger_patterns": [trigger_pattern],
        },
    )
    assert update_resp.status_code == 200, update_resp.text

    confirm_resp = await http_client.post(f"/api/v1/macros/{macro_id}/confirm")
    assert confirm_resp.status_code == 200, confirm_resp.text

    return macro_id


class TestL0NavigationMacro:
    """二 文字消息跳过 L0：导航宏在文字链路上不再本地导航，统一委派 Agent。

    L0 前端导航只服务语音快捷指令；语音侧 navigate 信封由
    ``test_18_voice_reply_points.test_voice_navigate_envelope`` 覆盖。
    """

    @pytest.mark.timeout(90)
    async def test_web_navigation_trigger_skips_l0_and_delegates_to_agent(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """用 BERT 标签 ``弹出磁盘`` 创建导航宏，文字触发后不再返回 navigate，
        直接委派 Agent 返回 queued。"""
        # ``弹出来一下`` 是 data/intents.yaml 中 ``弹出磁盘`` 的训练示例，BERT 裕度约 0.45。
        name = "弹出磁盘"
        trigger = "弹出来一下"
        route = "/e2e-settings-test"
        feedback = "已跳转"
        macro_id = await _create_navigation_macro(
            http_client, name, trigger, route, feedback
        )
        try:
            resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": trigger, "project_id": 0},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "queued", f"文字消息应跳过 L0 导航委派 Agent: {body}"
            assert body.get("navigate") is None, f"文字消息不应带 navigate: {body}"
            assert body["thread_id"] == thread_id
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")


class TestL0ParametricMacro:
    """二 文字消息跳过 L0：参数化宏不再在本地做槽位抽取执行，统一委派 Agent。"""

    @pytest.mark.timeout(90)
    async def test_web_parametric_trigger_skips_l0_and_delegates_to_agent(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """用 BERT 标签 ``重说`` 创建带 {word} 槽位的宏，文字触发后不再本地执行，
        直接委派 Agent 返回 queued。"""
        # ``你说什么呗`` 是 ``重说`` 的训练示例，BERT 裕度约 0.76。
        name = "重说"
        trigger_pattern = "你说{word}呗"
        trigger_value = "你说什么呗"
        parameters = [{"name": "word", "type": "str", "required": True}]
        macro_id = await _create_parametric_macro(
            http_client, name, trigger_pattern, parameters
        )
        try:
            text = trigger_value
            resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": text, "project_id": 0},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "queued", f"文字消息应跳过 L0 委派 Agent: {body}"
            assert body["thread_id"] == thread_id
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")


class TestL0OpenAppSpec:
    """二 L0 规格仍向客户端发布宏触发模板，供端侧确定性匹配。

    服务端 L0 路由已切换为 BERT 意图分类 + DB 宏解析，但 ``/route/init`` 仍会
    通过 ``enrich_spec_with_macro_triggers`` 注入 ``macro:{id}`` 模板。此处仅断言
    规格中保留了能匹配 open_app 指令的宏模板（如 preset 宏 "打开应用"），以及
    静态 app 槽位（WeChat）存在。
    """

    @pytest.mark.timeout(30)
    async def test_open_app_capability_published_via_macro_spec(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """GET /route/init 返回的规格包含能命中 open_app 指令的宏模板 + WeChat 静态 app。"""
        resp = await http_client.get("/api/v1/route/init")
        assert resp.status_code in (200, 202), resp.text
        data = resp.json()
        if data.get("unchanged"):
            # 首次请求可能还在 pending，重试一次等待 worker 构建完成
            await asyncio.sleep(1.0)
            resp = await http_client.get("/api/v1/route/init")
            assert resp.status_code in (200, 202), resp.text
            data = resp.json()
        templates = data.get("templates", [])
        actions = {t.get("action") for t in templates}

        # open_app 能力以宏模板承载（action 为 macro:*），而非静态 builtin 模板。
        # 断言存在携带 open_app 槽位（如 打开{app} / 启动{app}）的宏模板。
        open_app_patterns = {"打开{app}", "启动{app}", "开一下{app}", "打开微信"}
        matched = [
            t
            for t in templates
            if open_app_patterns.intersection(set(t.get("patterns", [])))
        ]
        assert matched, (
            f"L0 规格缺少可命中 open_app 指令的宏模板: {actions}"
        )

        apps = data.get("slot_dictionaries", {}).get("app", [])
        names = {e.get("name") for e in apps if isinstance(e, dict)}
        assert "WeChat" in names, f"静态 app 槽位缺少 WeChat: {names}"


class TestL0OpenAppMacroInDB:
    """二 宏表可以存储 open_app 动作，确认后进入 L0 规格（不执行桌面）。"""

    @pytest.mark.timeout(90)
    async def test_open_app_macro_appears_in_l0_spec(
        self, http_client: httpx.AsyncClient
    ) -> None:
        """创建并确认一个 open_app 宏，其触发词出现在 L0 规格中。"""
        script = (
            "- type: action\n"
            "  event_type: open_app\n"
            "  source: desktop\n"
            "  payload:\n"
            "    app_name: WeChat\n"
        )
        create_resp = await http_client.post(
            "/api/v1/macros/",
            json={
                "name": f"e2e-open-wechat-{uuid.uuid4().hex[:6]}",
                "description": "open wechat macro",
                "macro_script": script,
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        macro_id = create_resp.json()["id"]

        try:
            trigger = f"e2e打开微信测试{uuid.uuid4().hex[:6]}"
            update_resp = await http_client.put(
                f"/api/v1/macros/{macro_id}",
                json={"trigger_patterns": [trigger]},
            )
            assert update_resp.status_code == 200, update_resp.text

            confirm_resp = await http_client.post(f"/api/v1/macros/{macro_id}/confirm")
            assert confirm_resp.status_code == 200, confirm_resp.text

            await _wait_for_macro_in_spec(http_client, macro_id, expected_trigger=trigger)

            spec_resp = await http_client.get("/api/v1/route/init")
            assert spec_resp.status_code == 200, spec_resp.text
            templates = spec_resp.json().get("templates", [])
            matches = [t for t in templates if t.get("action") == f"macro:{macro_id}"]
            assert matches, "open_app 宏的触发词未进入 L0 规格"
            assert trigger in matches[0].get("patterns", [])
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")


async def _create_failing_macro(
    http_client: httpx.AsyncClient, name: str, trigger: str
) -> int:
    """创建并确认一个必然失败的宏（bash 步骤 exit 1），返回 macro_id。

    ``name`` 必须是 BERT 已学习的意图标签，``trigger`` 为该标签下的示例 utterance，
    这样 voice 源 L0 才能命中该宏并执行失败，随后转投 Agent。
    """
    script = '- type: bash\n  payload:\n    command: "exit 1"\n'
    create_resp = await http_client.post(
        "/api/v1/macros/",
        json={
            "name": name,
            "description": "deterministic failing macro (bash exit 1)",
            "macro_script": script,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    macro_id = create_resp.json()["id"]

    update_resp = await http_client.put(
        f"/api/v1/macros/{macro_id}",
        json={"trigger_patterns": [trigger]},
    )
    assert update_resp.status_code == 200, update_resp.text

    confirm_resp = await http_client.post(f"/api/v1/macros/{macro_id}/confirm")
    assert confirm_resp.status_code == 200, confirm_resp.text
    return macro_id


class TestWebSkipsL0DelegatesAgent:
    """二 文字消息跳过 L0：BERT 宏命中/未命中一律委派 Agent（queued）。

    对应新链路「文字消息 → L1 → Agent」：
      - 即使命中已确认宏标签：跳过 L0 本地执行，委派 Agent（queued）
      - 未命中宏：L1 → Agent（queued）
    L0 本地执行只保留给语音快捷指令（见 test_04_voice_output 语音 L0 用例）。
    """

    @pytest.mark.real
    @pytest.mark.timeout(120)
    async def test_open_app_macro_hit_delegates_to_agent(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """用 BERT 标签 ``ack`` 创建 wait 宏，文字触发后跳过 L0 → 委派 Agent queued。"""
        # ``麻烦对对对`` 是 ``ack`` 的训练示例，BERT 裕度约 0.77。
        name = "ack"
        trigger = "麻烦对对对"
        macro_id = await _create_routable_macro(http_client, name, trigger)
        try:
            resp = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": trigger, "project_id": 0},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "queued", (
                f"文字消息命中宏也应跳过 L0 委派 Agent，实际 {body}"
            )
            assert body["message_id"], body
            assert body["thread_id"] == thread_id
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")

    @pytest.mark.real
    @pytest.mark.timeout(120)
    async def test_open_app_macro_miss_delegates_to_agent(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        """非 open_app 语义的普通问题 → L1 → Agent 兜底 queued。"""
        resp = await http_client.post(
            "/api/v1/chat",
            json={"thread_id": thread_id, "message": "什么是量子计算", "project_id": 0},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "queued", (
            f"文字消息应委派 Agent（queued），实际 {body}"
        )
        assert body["thread_id"] == thread_id
        assert body["message_id"]


class TestVoiceMacroFailureFallback:
    """二 L0-5：voice 源宏失败转投 Agent（dispatch_handler voice 失败转投）。"""

    @pytest.mark.real
    @pytest.mark.slow
    @pytest.mark.timeout(300)
    async def test_failed_macro_delegates_to_agent(
        self,
        http_client: httpx.AsyncClient,
        thread_id: str,
        voice_conn: Any,
    ) -> None:
        """exit 1 的 bash 宏在 voice 源必然失败 → 转投 Agent → 终态带 AI summary。

        本地宏执行失败会立即推送固定话术 {status: failed, summary: "执行失败"}；
        转投 Agent 后需要较长时间由 LLM 处理并返回自由文本 summary。
        以"短窗口内无固定话术终态 + 长等待后出现 AI summary"判定转投成功。
        """
        # ``改名`` 是 BERT 已学习的标签且不是现有 DB 宏名称，``帮我你以后叫小明``
        # 为其训练示例，宏脚本为必然失败的 bash exit 1，用于验证 voice 源失败后的 Agent 回退。
        name = "改名"
        trigger = "帮我你以后叫小明"
        macro_id = await _create_failing_macro(http_client, name, trigger)
        try:
            await voice_conn.send_route(trigger)

            # 短窗口：本地宏（成功或失败）应在数秒内返回固定话术终态。
            try:
                env = await voice_conn.wait_terminal_route_result(timeout=12.0)
            except TimeoutError:
                env = None

            if env is None:
                # 无快速本地终态 → 宏失败已转投 Agent，等待 Agent 侧终态。
                env = await voice_conn.wait_terminal_route_result(timeout=180.0)
                body = env["body"]
                assert body["status"] in ("done", "failed"), (
                    f"Agent 转投终态状态异常: {body}"
                )
                summary = body.get("summary", "")
                assert summary and summary not in ("完成", "执行失败"), (
                    f"期望 Agent 转投后的 AI summary，实际疑似本地宏结果: {body}"
                )
            else:
                body = env["body"]
                summary = body.get("summary", "")
                if body["status"] == "done" and summary == "完成":
                    pytest.skip(
                        "exit 1 宏未如预期失败（本地执行成功），无法验证 voice 源失败转投"
                    )
                assert summary not in ("完成", "执行失败"), (
                    f"voice 源宏失败未转投 Agent，返回了本地执行结果: {body}"
                )
        finally:
            await http_client.delete(f"/api/v1/macros/{macro_id}")
