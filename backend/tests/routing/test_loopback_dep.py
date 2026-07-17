import pytest
from fastapi import HTTPException

from app.core.routing import deps


def test_is_loopback_host():
    assert deps.is_loopback_host("127.0.0.1")
    assert deps.is_loopback_host("::1")
    assert deps.is_loopback_host("localhost")
    assert deps.is_loopback_host("::ffff:127.0.0.1")
    assert not deps.is_loopback_host("8.8.8.8")
    assert not deps.is_loopback_host("192.168.1.10")
    assert not deps.is_loopback_host(None)
    assert not deps.is_loopback_host("")


@pytest.mark.asyncio
async def test_require_loopback_rejects_remote():
    class _Client:
        host = "8.8.8.8"

    class _Req:
        client = _Client()

    with pytest.raises(HTTPException) as exc:
        await deps.require_loopback(_Req())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_loopback_allows_local():
    class _Client:
        host = "127.0.0.1"

    class _Req:
        client = _Client()

    await deps.require_loopback(_Req())  # no raise
