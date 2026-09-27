"""Integration tests for the /auth_proxy API routes (app/api/routes/auth_proxy.py)."""

from __future__ import annotations

from app.models.schemas.auth import EvoCloudProxyResponse, LoginResult


async def _fake_captcha_config():
    return EvoCloudProxyResponse(code=0, data={"enabled": True})


async def _fake_captcha(captcha_id):  # noqa: ARG001
    return EvoCloudProxyResponse(code=0, data={"image": "base64data"})


async def _fake_register_config():
    return EvoCloudProxyResponse(code=0, data={"mobile_required": True})


async def _fake_register_agreement(type="SERVICE"):  # noqa: ARG001
    return EvoCloudProxyResponse(code=0, data={"content": "terms text"})


async def _fake_send_mobile_code(mobile="", captcha_id="", captcha_code="", type="login"):  # noqa: ARG001
    return EvoCloudProxyResponse(code=0, data={"key": "sms-key"})


async def _fake_register_mobile(data):  # noqa: ARG001
    return EvoCloudProxyResponse(code=0, message="registered")


async def _fake_register_username(data):  # noqa: ARG001
    return EvoCloudProxyResponse(code=0, message="registered")


async def _fake_login_mobile(mobile="", key="", code=""):  # noqa: ARG001
    return LoginResult(success=True, token="proxy-tok", member_id=5)


async def _fake_check_mobile(mobile):  # noqa: ARG001
    return EvoCloudProxyResponse(code=0, data={"exists": True})


async def _fake_reset_password(mobile, code, key, password):  # noqa: ARG001
    return EvoCloudProxyResponse(code=0, message="password reset")


class TestCaptchaEndpoints:
    async def test_get_captcha_config(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.auth_proxy.evocloud_manager.api.get_captcha_config",
            _fake_captcha_config,
        )
        resp = await client.post("/auth/captcha/config")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_get_captcha(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.auth_proxy.evocloud_manager.api.get_captcha",
            _fake_captcha,
        )
        resp = await client.get("/auth/captcha/captcha-123")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["image"] == "base64data"


class TestRegisterEndpoints:
    async def test_get_register_config(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.auth_proxy.evocloud_manager.api.get_register_config",
            _fake_register_config,
        )
        resp = await client.get("/auth/register/config")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_get_register_agreement(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.auth_proxy.evocloud_manager.api.get_register_agreement",
            _fake_register_agreement,
        )
        resp = await client.get("/auth/register/agreement?type=SERVICE")
        assert resp.status_code == 200
        assert resp.json()["data"]["content"] == "terms text"

    async def test_register_mobile(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.auth_proxy.evocloud_manager.api.register_mobile",
            _fake_register_mobile,
        )
        resp = await client.post(
            "/auth/register/mobile",
            json={"mobile": "13800138000", "key": "k", "code": "123456"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_register_username(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.auth_proxy.evocloud_manager.api.register_username",
            _fake_register_username,
        )
        resp = await client.post(
            "/auth/register/username",
            json={"username": "testuser", "password": "secret123"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0


class TestLoginMobileProxy:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.auth_proxy.evocloud_manager.api.login_mobile",
            _fake_login_mobile,
        )
        resp = await client.post(
            "/auth/login/mobile",
            json={"mobile": "13800138000", "code": "123456", "key": "k"},
        )
        assert resp.status_code == 200
        assert resp.json()["token"] == "proxy-tok"
        assert resp.json()["success"] is True


class TestSmsAndCheck:
    async def test_send_sms(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.auth_proxy.evocloud_manager.api.send_mobile_code",
            _fake_send_mobile_code,
        )
        resp = await client.post(
            "/auth/sms/send",
            json={"mobile": "13800138000"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_check_mobile(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.auth_proxy.evocloud_manager.api.check_mobile_exist",
            _fake_check_mobile,
        )
        resp = await client.post(
            "/auth/mobile/check",
            json={"mobile": "13800138000"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["exists"] is True


class TestResetPassword:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.auth_proxy.evocloud_manager.api.reset_password_by_mobile",
            _fake_reset_password,
        )
        resp = await client.post(
            "/auth/password/reset/mobile",
            json={"mobile": "13800138000", "key": "k", "code": "123456", "password": "newpass123"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
