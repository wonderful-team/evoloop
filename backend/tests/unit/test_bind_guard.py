"""HOST 绑定守卫回归（部署层 P0 修复）：

默认 fail-closed（loopback 之外拒绝启动）；生产 Web 部署经
ALLOW_REMOTE_BIND=1 显式豁免——语音路由仍受逐请求 loopback 守卫。
"""

import pytest

from app.main import assert_safe_bind


def test_loopback_hosts_pass():
    for host in ("127.0.0.1", "localhost", "::1"):
        assert_safe_bind(host)  # 不抛即通过


def test_remote_host_rejected_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_BIND", raising=False)
    with pytest.raises(RuntimeError, match="loopback binding"):
        assert_safe_bind("0.0.0.0")


@pytest.mark.parametrize("flag", ["1", "true", "yes", "TRUE"])
def test_remote_host_allowed_with_explicit_optin(monkeypatch, flag):
    monkeypatch.setenv("ALLOW_REMOTE_BIND", flag)
    assert_safe_bind("0.0.0.0")  # 豁免后不抛


@pytest.mark.parametrize("flag", ["0", "false", "", "random"])
def test_optin_flag_is_strict(monkeypatch, flag):
    monkeypatch.setenv("ALLOW_REMOTE_BIND", flag)
    with pytest.raises(RuntimeError):
        assert_safe_bind("192.168.1.10")
