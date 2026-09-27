"""Integration tests for the /account API routes (app/api/routes/account.py)."""

from __future__ import annotations


async def _fake_login(_username: str = "", _password: str = ""):
    return {"success": True, "token": "fake-token-123", "member_id": 42}


async def _fake_login_fail(_username: str = "", _password: str = ""):
    return {"success": False, "message": "Incorrect username or password"}


async def _fake_login_no_token(_username: str = "", _password: str = ""):
    return {"success": True, "member_id": 42}


async def _fake_send_mobile_code(mobile="", captcha_id="", captcha_code="", type="login"):  # noqa: ARG001
    return {"code": 0, "message": "ok", "data": {"key": "sms-key-abc"}}


async def _fake_send_mobile_code_fail(mobile="", captcha_id="", captcha_code="", type="login"):  # noqa: ARG001
    return {"code": -1, "message": "Failed to send"}


async def _fake_login_mobile(mobile="", key="", code=""):  # noqa: ARG001
    return {"success": True, "token": "mobile-token-xyz", "member_id": 7}


async def _fake_login_mobile_fail(mobile="", key="", code=""):  # noqa: ARG001
    return {"success": False, "message": "Login failed"}


async def _fake_login_mobile_no_token(mobile="", key="", code=""):  # noqa: ARG001
    return {"success": True, "member_id": 7}


async def _fake_identity_login(_token=None):
    return None


async def _fake_publish_logged_in(token, member_id):  # noqa: ARG001
    return None


async def _fake_publish_logged_out():
    return None


async def _fake_identity_logout():
    return None


class TestLoginAccessToken:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.account.evocloud_manager.api.login", _fake_login)
        monkeypatch.setattr("app.api.routes.account.identity_service.login_with_cloud_result", _fake_identity_login)
        monkeypatch.setattr("app.api.routes.account.publish_user_logged_in", _fake_publish_logged_in)
        resp = await client.post(
            "/login/access-token",
            data={"username": "user", "password": "pass"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "fake-token-123"
        assert data["token_type"] == "bearer"

    async def test_bad_credentials(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.account.evocloud_manager.api.login", _fake_login_fail)
        resp = await client.post(
            "/login/access-token",
            data={"username": "user", "password": "wrong"},
        )
        assert resp.status_code == 400

    async def test_missing_token_in_result(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.account.evocloud_manager.api.login", _fake_login_no_token)
        resp = await client.post(
            "/login/access-token",
            data={"username": "user", "password": "pass"},
        )
        assert resp.status_code == 500


class TestMobileLogin:
    async def test_request_code_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.account.evocloud_manager.api.send_mobile_code",
            _fake_send_mobile_code,
        )
        resp = await client.post(
            "/login/mobile/code",
            json={"mobile": "13800138000"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["key"] == "sms-key-abc"

    async def test_request_code_failure(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.account.evocloud_manager.api.send_mobile_code",
            _fake_send_mobile_code_fail,
        )
        resp = await client.post(
            "/login/mobile/code",
            json={"mobile": "13800138000"},
        )
        assert resp.status_code == 400

    async def test_login_mobile_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.account.evocloud_manager.api.login_mobile", _fake_login_mobile
        )
        monkeypatch.setattr("app.api.routes.account.identity_service.login_with_cloud_result", _fake_identity_login)
        monkeypatch.setattr("app.api.routes.account.publish_user_logged_in", _fake_publish_logged_in)
        resp = await client.post(
            "/login/mobile",
            json={"mobile": "13800138000", "code": "123456", "key": "k"},
        )
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "mobile-token-xyz"

    async def test_login_mobile_failure(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.account.evocloud_manager.api.login_mobile", _fake_login_mobile_fail
        )
        resp = await client.post(
            "/login/mobile",
            json={"mobile": "13800138000", "code": "000000", "key": "k"},
        )
        assert resp.status_code == 400

    async def test_login_mobile_no_token(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.account.evocloud_manager.api.login_mobile", _fake_login_mobile_no_token
        )
        resp = await client.post(
            "/login/mobile",
            json={"mobile": "13800138000", "code": "123456", "key": "k"},
        )
        assert resp.status_code == 500


class TestWeChat:
    async def test_get_config_enabled(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(code=0, message="ok")

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.get("/auth/wechat/config")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    async def test_get_config_exception_returns_disabled(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            raise ConnectionError("timeout")

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.get("/auth/wechat/config")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_generate_qr_success(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(
                code=0, data={"key": "qr-key", "expire_time": 300, "qrcode": "https://qr", "ticket": "t-123"}
            )

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.post("/auth/wechat/qrcode")
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "qr-key"
        assert data["qrcode_url"] == "https://qr"

    async def test_generate_qr_failure(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(code=-1, message="Service unavailable")

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.post("/auth/wechat/qrcode")
        assert resp.status_code == 503

    async def test_check_status_pending(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(code=0, data={})

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.get("/auth/wechat/status?key=k1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    async def test_check_status_confirmed(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(code=0, data={"token": "wx-tok"})

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.get("/auth/wechat/status?key=k1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"
        assert resp.json()["access_token"] == "wx-tok"

    async def test_check_status_expired(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(code=-1, message="expired")

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.get("/auth/wechat/status?key=k1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "expired"

    async def test_check_status_exception(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            raise RuntimeError("oops")

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.get("/auth/wechat/status?key=k1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    async def test_direct_login_success(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(
                code=0, data={"token": "direct-tok", "member_id": 99}
            )

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        monkeypatch.setattr("app.api.routes.account.identity_service.login_with_cloud_result", _fake_identity_login)
        monkeypatch.setattr("app.api.routes.account.publish_user_logged_in", _fake_publish_logged_in)
        resp = await client.post("/auth/wechat/login-direct?key=k1")
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "direct-tok"

    async def test_direct_login_no_code(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(code=-1, message="not scanned")

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.post("/auth/wechat/login-direct?key=k1")
        assert resp.status_code == 400

    async def test_direct_login_no_token_in_data(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(code=0, data={"member_id": 1})

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.post("/auth/wechat/login-direct?key=k1")
        assert resp.status_code == 400

    async def test_direct_login_no_member_id(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(code=0, data={"token": "tok"})

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.post("/auth/wechat/login-direct?key=k1")
        assert resp.status_code == 500

    async def test_callback_success(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            from app.models.schemas.auth import EvoCloudProxyResponse
            return EvoCloudProxyResponse(code=0, data="callback-ok")

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.post(
            "/auth/wechat/callback?signature=s&timestamp=1&nonce=n",
            content=b"<xml>test</xml>",
        )
        assert resp.status_code == 200

    async def test_callback_exception(self, client, monkeypatch):
        async def _mc_req(_method, _endpoint, **_kwargs):
            raise RuntimeError("fail")

        monkeypatch.setattr("app.api.routes.account._member_center_request", _mc_req)
        resp = await client.post(
            "/auth/wechat/callback?signature=s&timestamp=1&nonce=n",
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "OK"


class TestLogout:
    async def test_logout(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.account.identity_service.logout", _fake_identity_logout)
        monkeypatch.setattr("app.api.routes.account.publish_user_logged_out", _fake_publish_logged_out)
        resp = await client.post("/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["message"] == "Logged out successfully"
