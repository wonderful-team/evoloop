"""Integration tests for the /member API routes (app/api/routes/member.py)."""

from __future__ import annotations

from app.models.schemas.auth import EvoCloudProxyResponse


async def _fake_get_user_info(token=None):  # noqa: ARG001
    return EvoCloudProxyResponse(
        code=0,
        data={
            "member_id": 1,
            "username": "tester",
            "nickname": " Tester ",
            "mobile": "13800138000",
            "email": "test@example.com",
            "headimg": "https://img.url",
            "member_level": 2,
            "member_level_name": "Gold",
            "member_level_type": 1,
            "level_expire_time": 1700000000,
            "member_label": 0,
            "member_label_name": None,
            "member_code": "M001",
            "point": 500,
            "balance": 10.5,
            "balance_money": 10.5,
            "growth": 200,
            "status": 1,
            "password": 1,
            "is_edit_username": 0,
            "is_fenxiao": 0,
            "realname": None,
            "sex": 1,
            "birthday": None,
            "source_member": 0,
            "province_id": 0,
            "city_id": 0,
            "district_id": 0,
            "address": None,
            "full_address": None,
            "longitude": 0,
            "latitude": 0,
            "wx_openid": None,
            "wx_unionid": None,
        },
    )


async def _fake_get_user_info_fail(token=None):  # noqa: ARG001
    return EvoCloudProxyResponse(code=-1, message="Session expired")


async def _fake_change_password(old_password="", new_password="", token=None):  # noqa: ARG001
    return EvoCloudProxyResponse(code=0, success=True, message="Password changed")


async def _fake_update_user_info(data, token=None):  # noqa: ARG001
    from app.models import User
    return User(id=1, username="tester", nickname="updated")


async def _fake_get_cancellation_info():
    return EvoCloudProxyResponse(code=0, data={"can_cancel": True})


async def _fake_apply_cancellation():
    return EvoCloudProxyResponse(code=0, message="Applied")


async def _fake_cancel_cancellation_apply():
    return EvoCloudProxyResponse(code=0, message="Cancelled")


async def _fake_get_member_id(token):  # noqa: ARG001
    return 42


async def _fake_check_multiple_benefits(benefit_codes, member_id):  # noqa: ARG001
    return {"vip_access": True, "premium_support": False}


async def _fake_get_member_entitlements(member_id, force_refresh=False):  # noqa: ARG001
    return {"is_expired": False, "level_name": "Gold"}


async def _fake_invalidate_cache(member_id):  # noqa: ARG001
    return None


async def _fake_cache_get(key):  # noqa: ARG001
    return None


class TestReadUserMe:
    async def test_cache_miss_calls_mc(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.member.evocloud_manager.api.get_user_info", _fake_get_user_info)
        monkeypatch.setattr("app.api.routes.member.cache.get", _fake_cache_get)
        resp = await client.get("/member/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["username"] == "tester"
        assert data["is_active"] is True

    async def test_mc_failure_returns_401(self, client, monkeypatch):
        monkeypatch.setattr("app.api.routes.member.evocloud_manager.api.get_user_info", _fake_get_user_info_fail)
        monkeypatch.setattr("app.api.routes.member.cache.get", _fake_cache_get)
        resp = await client.get("/member/me")
        assert resp.status_code == 401

    async def test_cache_hit_returns_user(self, client, monkeypatch):
        import json

        cached = {
            "member_id": 1,
            "username": "cached_user",
            "nickname": "Cached",
            "status": 1,
        }

        async def _cache_get(_key):
            return json.dumps(cached)

        monkeypatch.setattr("app.api.routes.member.cache.get", _cache_get)
        resp = await client.get("/member/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "cached_user"


class TestChangePassword:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.member.evocloud_manager.api.change_password", _fake_change_password
        )
        resp = await client.put(
            "/member/password",
            json={"old_password": "old", "new_password": "newpassword"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestUpdateUserMe:
    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.member.evocloud_manager.api.update_user_info", _fake_update_user_info
        )
        resp = await client.put(
            "/member/me",
            json={"nickname": "new name"},
        )
        assert resp.status_code == 200
        assert resp.json()["nickname"] == "updated"
        assert resp.json()["id"] == 1


class TestCancellation:
    async def test_get_info(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.member.evocloud_manager.api.get_cancellation_info",
            _fake_get_cancellation_info,
        )
        resp = await client.get("/member/cancellation/info")
        assert resp.status_code == 200
        assert resp.json()["data"]["can_cancel"] is True

    async def test_apply(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.member.evocloud_manager.api.apply_cancellation",
            _fake_apply_cancellation,
        )
        resp = await client.post("/member/cancellation/apply")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_cancel(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.member.evocloud_manager.api.cancel_cancellation_apply",
            _fake_cancel_cancellation_apply,
        )
        resp = await client.post("/member/cancellation/cancel")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0


class TestBenefits:
    async def test_batch_check(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.member.identity_service.get_member_id", _fake_get_member_id
        )
        monkeypatch.setattr(
            "app.api.routes.member.benefit_service.check_multiple_benefits",
            _fake_check_multiple_benefits,
        )
        monkeypatch.setattr(
            "app.api.routes.member.benefit_service.get_member_entitlements",
            _fake_get_member_entitlements,
        )
        resp = await client.post(
            "/member/benefits/check-batch",
            json={"benefit_codes": ["vip_access", "premium_support"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["vip_access"] is True
        assert data["level_name"] == "Gold"

    async def test_get_benefits(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.member.identity_service.get_member_id", _fake_get_member_id
        )
        monkeypatch.setattr(
            "app.api.routes.member.benefit_service.get_member_entitlements",
            _fake_get_member_entitlements,
        )
        resp = await client.get("/member/benefits")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["level_name"] == "Gold"

    async def test_invalidate_cache(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.member.identity_service.get_member_id", _fake_get_member_id
        )
        monkeypatch.setattr(
            "app.api.routes.member.benefit_service.invalidate_cache",
            _fake_invalidate_cache,
        )
        resp = await client.post("/member/benefits/cache/invalidate")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
