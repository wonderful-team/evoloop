"""真实端到端测试（Real E2E）的专属夹具。

本模块覆盖：真实工具副作用、真实语音客户端、真实 LLM 闭环、真实移动端/网关链路。
所有夹具都假设 tests/e2e/conftest.py 中的 `http_client`、`service_url` 等通用夹具可用。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import (
    E2E_PASSWORD,
    E2E_SKIP_LOGIN,
    E2E_USERNAME,
    wait_until,
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def real_markers() -> dict[str, str]:
    """在真实 E2E 用例之间共享的标记集合（用于避免与其他并发测试冲突）。"""
    return {}


@pytest.fixture
async def temp_project(
    http_client: httpx.AsyncClient,
    workspace_root: Path,
) -> AsyncIterator[dict[str, Any]]:
    """创建一个临时项目目录，并尝试导入为后端项目；失败后回退到 project_id=0。

    返回：{"project_id": int, "path": Path, "imported": bool}
    """
    marker = f"e2e-real-{uuid.uuid4().hex[:8]}"
    project_dir = workspace_root / marker
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".gitkeep").write_text("", encoding="utf-8")

    imported = False
    project_id = 0
    try:
        resp = await http_client.post(
            "/api/v1/projects/import-by-path",
            json={"path": str(project_dir), "name": marker},
        )
        if resp.status_code == 200:
            data = resp.json()
            # 优先使用真正的 project_id（cloud 分配的 PID），repo_id 是仓储行 id，
            # 二者 id 空间不同，喂给 /chat 的 project_id 必须用前者，否则 dispatch
            # 无法解析项目路径并拒绝回退（文件工具会落到 WORKSPACE_ROOT）。
            project_id = data.get("project_id") or data.get("repo_id") or 0
            imported = True
            logger.info("临时项目导入成功: %s -> %s", marker, project_id)
        else:
            logger.warning(
                "临时项目导入失败(status=%s): %s，将使用 project_id=0 继续测试",
                resp.status_code,
                resp.text[:200],
            )
    except Exception as exc:
        logger.warning("临时项目导入异常: %s", exc)

    try:
        yield {"project_id": project_id, "path": project_dir, "imported": imported}
    finally:
        # 尽量清理目录，但不要因清理失败影响测试断言结果
        try:
            if shutil.which("rm"):
                await asyncio.to_thread(shutil.rmtree, project_dir, ignore_errors=True)
            else:
                await asyncio.to_thread(project_dir.rmdir)
        except Exception as exc:
            logger.warning("清理临时项目目录失败: %s", exc)


@pytest.fixture(scope="session", autouse=True)
async def real_service_link_ready(service_url: str) -> None:
    """登录后端并等待 EvoCloud Gateway 链路握手完成。

    真实移动端/网关测试依赖本机已注册 device_key 且 WS 已连接；
    首次启动后链路需要几秒完成注册，因此在 session 级别统一等待。
    """
    if E2E_SKIP_LOGIN:
        return

    async with httpx.AsyncClient(base_url=service_url, timeout=15.0) as client:
        resp = await client.post(
            "/api/v1/login/access-token",
            data={"username": E2E_USERNAME, "password": E2E_PASSWORD},
        )
        if resp.status_code != 200:
            pytest.skip(f"登录失败，跳过真实 E2E: {resp.status_code} {resp.text[:200]}")
        token = resp.json().get("access_token")
        if not token:
            pytest.skip("登录未返回 token，跳过真实 E2E")
        client.headers["Authorization"] = f"Bearer {token}"

        async def _link_ready() -> bool:
            try:
                resp = await client.get("/api/v1/utils/evoloop-status")
                if resp.status_code != 200:
                    return False
                data = resp.json()
                return bool(data.get("connected") and data.get("device_key"))
            except Exception as exc:
                logger.debug("等待 EvoCloud 链路时异常: %s", exc)
                return False

        try:
            await wait_until(
                _link_ready,
                timeout=60.0,
                interval=0.5,
                desc="EvoCloud Gateway 链路连接",
            )
            logger.info("EvoCloud Gateway 链路已就绪")
        except TimeoutError:
            pytest.skip("EvoCloud Gateway 未在 60s 内连接，跳过真实移动端/网关测试")
