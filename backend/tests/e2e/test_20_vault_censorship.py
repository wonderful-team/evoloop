"""Vault 密钥脱敏回归测试（AGENTS.md 关键安全修复，此前无回归测试）。

链路：
  {{vault.<id>.<key>}} 占位符在 PRE_TOOL_USE 钩子被解密替换进工具输入，
  工具输出若包含密文，POST_TOOL_USE 钩子必须将其打码为 ******（含跨
  tool-call 的 EvoContext 回退）。
"""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx
import pytest

from tests.e2e.conftest import observe_agent_run

pytestmark = [pytest.mark.e2e, pytest.mark.real]


async def _all_message_text(http_client: httpx.AsyncClient, thread_id: str) -> str:
    """拼接消息历史全文（content + meta_data），用于检测密文泄漏。"""
    resp = await http_client.get(
        f"/api/v1/conversations/{thread_id}/messages",
        params={"include_tool_calls": "true"},
        timeout=30.0,
    )
    resp.raise_for_status()
    parts = [json.dumps(m, ensure_ascii=False) for m in resp.json().get("data", [])]
    return "\n".join(parts)


class TestVaultCensorship:
    @pytest.mark.timeout(240)
    async def test_vault_secret_censored_in_tool_output(
        self, http_client: httpx.AsyncClient, thread_id: str
    ) -> None:
        secret = f"e2e-vault-secret-{uuid.uuid4().hex[:8]}"
        identifier = f"e2e-sec-{uuid.uuid4().hex[:6]}"

        # 1. 创建 vault 凭据（payload 的 key 作为密文）
        create = await http_client.post(
            "/api/v1/vault/credentials",
            json={
                "identifier": identifier,
                "type": "api_key",
                "payload": {"key": secret},
                "project_id": 0,
                "description": "e2e censorship test",
            },
        )
        assert create.status_code == 200, create.text
        try:
            # 2. 让 Agent 原样运行包含占位符的命令（占位符在钩子层被解密注入）
            observer = asyncio.create_task(
                observe_agent_run(http_client, thread_id, timeout=200.0)
            )
            await asyncio.sleep(0)
            prompt = (
                f"请用 execute_command 工具原样运行命令 `echo {{{{vault.{identifier}.key}}}}`"
                "，命令一个字都不要改，然后报告输出。"
            )
            chat = await http_client.post(
                "/api/v1/chat",
                json={"thread_id": thread_id, "message": prompt, "project_id": 0},
            )
            assert chat.status_code == 200, chat.text
            assert chat.json()["status"] in ("queued", "done")

            result = await observer
            if result.run_end_status in ("failed", "cancelled", "quota_exhausted"):
                pytest.skip(
                    f"Agent 运行未成功完成（{result.run_end_status}），无法验证脱敏"
                )

            # 3. 核心断言：密文不得出现在任何消息历史（content/meta_data 均打码）。
            #    无论 LLM 是执行了命令（经占位符注入后输出被打码）还是出于安全
            #    考虑拒绝执行，密文都不允许泄漏。
            text = await _all_message_text(http_client, thread_id)
            assert secret not in text, (
                f"Vault 密文在消息历史中泄露！thread={thread_id} secret={secret[:12]}..."
            )

            # 4. 若命令确实被 execute_command 执行（出现了工具输出消息），则
            #    工具输出必须出现打码标记 ******。
            if '"role": "tool"' in text:
                assert "******" in text, (
                    "execute_command 已执行但工具输出未见打码标记 ******"
                )
        finally:
            await http_client.delete(
                f"/api/v1/vault/credentials/{identifier}", params={"project_id": 0}
            )
