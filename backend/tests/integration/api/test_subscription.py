"""Integration tests for the /member/subscription and /member/quota API routes.

All subscription/quota endpoints proxy to ``evocloud_manager.api``.
The webhook endpoint verifies HMAC signatures and invalidates benefit caches.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
from types import SimpleNamespace

import pytest

# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------


async def _async_return(value):
    return value


# ---------------------------------------------------------------------------
# Subscription plan/status/order endpoints
# ---------------------------------------------------------------------------


class TestSubscriptionEndpoints:
    @pytest.fixture(autouse=True)
    def _mock_evocloud(self, monkeypatch):
        self._calls: list[tuple[str, tuple, dict]] = []

        def _record(method_name):
            async def _impl(*args, **kwargs):
                self._calls.append((method_name, args, kwargs))
                return {"ok": True, "method": method_name}

            return _impl

        api_mock = SimpleNamespace(
            get_subscription_plans=_record("get_subscription_plans"),
            calculate_upgrade_price=_record("calculate_upgrade_price"),
            get_subscription_status=_record("get_subscription_status"),
            get_subscription_detail=_record("get_subscription_detail"),
            create_subscription_order=_record("create_subscription_order"),
            cancel_subscription=_record("cancel_subscription"),
            check_subscription_order_status=_record("check_subscription_order_status"),
        )
        monkeypatch.setattr(
            "app.api.routes.subscription.evocloud_manager",
            SimpleNamespace(api=api_mock),
        )

    async def test_get_plans(self, client):
        resp = await client.get("/member/subscription/plans")
        assert resp.status_code == 200
        assert resp.json()["method"] == "get_subscription_plans"

    async def test_upgrade_preview(self, client):
        resp = await client.post(
            "/member/subscription/upgrade-preview?target_level_id=2"
        )
        assert resp.status_code == 200
        assert resp.json()["method"] == "calculate_upgrade_price"

    async def test_get_status(self, client):
        resp = await client.get("/member/subscription/status")
        assert resp.status_code == 200
        assert resp.json()["method"] == "get_subscription_status"

    async def test_get_detail(self, client):
        resp = await client.get("/member/subscription/detail")
        assert resp.status_code == 200
        assert resp.json()["method"] == "get_subscription_detail"

    async def test_create_order(self, client):
        resp = await client.post(
            "/member/subscription/order",
            json={"level_id": 3, "auto_renew": True, "pay_type": "alipay"},
        )
        assert resp.status_code == 200
        assert resp.json()["method"] == "create_subscription_order"

    async def test_cancel(self, client):
        resp = await client.post(
            "/member/subscription/cancel?cancel_type=expire&reason=test"
        )
        assert resp.status_code == 200
        assert resp.json()["method"] == "cancel_subscription"

    async def test_check_order_status(self, client):
        resp = await client.get(
            "/member/subscription/order/status?order_id=ord-123"
        )
        assert resp.status_code == 200
        assert resp.json()["method"] == "check_subscription_order_status"


# ---------------------------------------------------------------------------
# Quota endpoints
# ---------------------------------------------------------------------------


class TestQuotaEndpoints:
    @pytest.fixture(autouse=True)
    def _mock_evocloud(self, monkeypatch):
        self._calls: list[tuple[str, tuple, dict]] = []

        def _record(method_name):
            async def _impl(*args, **kwargs):
                self._calls.append((method_name, args, kwargs))
                return {"ok": True, "method": method_name}

            return _impl

        api_mock = SimpleNamespace(
            get_ai_quota=_record("get_ai_quota"),
            get_all_ai_quotas=_record("get_all_ai_quotas"),
            get_ai_quota_history=_record("get_ai_quota_history"),
        )
        monkeypatch.setattr(
            "app.api.routes.subscription.evocloud_manager",
            SimpleNamespace(api=api_mock),
        )

    async def test_get_ai_quota(self, client):
        resp = await client.get("/member/quota")
        assert resp.status_code == 200
        assert resp.json()["method"] == "get_ai_quota"

    async def test_get_all_quotas(self, client):
        resp = await client.get("/member/quota/all")
        assert resp.status_code == 200
        assert resp.json()["method"] == "get_all_ai_quotas"

    async def test_get_quota_history(self, client):
        resp = await client.get(
            "/member/quota/history?page=1&page_size=10"
        )
        assert resp.status_code == 200
        assert resp.json()["method"] == "get_ai_quota_history"


# ---------------------------------------------------------------------------
# Benefits webhook
# ---------------------------------------------------------------------------


class TestBenefitsWebhook:
    @pytest.fixture(autouse=True)
    def _mock_benefits(self, monkeypatch):
        self._invalidated_member: int | None = None
        self._published_events: list[tuple[int, str]] = []

        def _invalidate(member_id):
            self._invalidated_member = member_id

        async def _publish(member_id, event):
            self._published_events.append((member_id, event))

        monkeypatch.setattr(
            "app.api.routes.subscription.benefit_service",
            SimpleNamespace(invalidate_cache=_invalidate),
        )
        monkeypatch.setattr(
            "app.core.events.publishers.publish_subscription_changed",
            _publish,
        )
        monkeypatch.setattr(
            "app.api.routes.subscription.settings",
            SimpleNamespace(WEBHOOK_SECRET=""),
        )

    async def test_webhook_subscription_created(self, client):
        payload = {
            "member_id": 42,
            "event": "subscription_created",
            "timestamp": 1700000000,
            "signature": "does_not_matter",
        }
        resp = await client.post("/member/webhook/benefits-update", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert self._invalidated_member == 42
        assert (42, "subscription_created") in self._published_events

    async def test_webhook_subscription_cancelled(self, client):
        payload = {
            "member_id": 10,
            "event": "subscription_cancelled",
            "timestamp": 1700000000,
            "signature": "x",
        }
        resp = await client.post("/member/webhook/benefits-update", json=payload)
        assert resp.status_code == 200
        assert self._invalidated_member == 10

    async def test_webhook_unknown_event_no_invalidation(self, client):
        payload = {
            "member_id": 5,
            "event": "some_other_event",
            "timestamp": 1700000000,
            "signature": "x",
        }
        resp = await client.post("/member/webhook/benefits-update", json=payload)
        assert resp.status_code == 200
        assert self._invalidated_member is None

    async def test_webhook_bad_signature_rejected(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.subscription.settings",
            SimpleNamespace(WEBHOOK_SECRET="super_secret"),
        )
        payload = {
            "member_id": 1,
            "event": "subscription_created",
            "timestamp": 1700000000,
            "signature": "wrong_sig",
        }
        resp = await client.post("/member/webhook/benefits-update", json=payload)
        assert resp.status_code == 401

    async def test_webhook_valid_signature(self, client, monkeypatch):
        secret = "test_secret_key"
        monkeypatch.setattr(
            "app.api.routes.subscription.settings",
            SimpleNamespace(WEBHOOK_SECRET=secret),
        )
        member_id = 99
        event = "subscription_renewed"
        ts = 1700000000
        expected_sig = _hmac.new(
            secret.encode(),
            f"{member_id}:{event}:{ts}".encode(),
            hashlib.sha256,
        ).hexdigest()
        payload = {
            "member_id": member_id,
            "event": event,
            "timestamp": ts,
            "signature": expected_sig,
        }
        resp = await client.post("/member/webhook/benefits-update", json=payload)
        assert resp.status_code == 200
        assert self._invalidated_member == member_id
