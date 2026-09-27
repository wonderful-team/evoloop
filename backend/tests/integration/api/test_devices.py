"""Integration tests for the /devices API routes (app/api/routes/devices.py)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


async def _fake_get_devices(token=None):  # noqa: ARG001
    return {
        "code": 0,
        "data": {"devices": [{"id": "dev-1", "serial": "SN001", "model": "Pixel"}]},
    }


async def _fake_get_devices_empty(token=None):  # noqa: ARG001
    return {"code": 0, "data": {"devices": []}}


async def _fake_get_devices_fail(token=None):  # noqa: ARG001
    return {"code": -1, "message": "error"}


async def _fake_send_command(device_key, body, token=None, envelope_type="command.relay"):  # noqa: ARG001
    return {"code": 0, "data": {"sent": True}}


async def _fake_send_command_fail(device_key, body, token=None, envelope_type="command.relay"):  # noqa: ARG001
    return {"code": 404, "message": "device not found"}


async def _fake_send_command_server_error(device_key, body, token=None, envelope_type="command.relay"):  # noqa: ARG001
    return {"code": 500, "message": "internal error"}


async def _fake_get_device_logs(device_key, limit, project_id):  # noqa: ARG001
    return {"code": 0, "data": [{"msg": "log line 1"}]}


async def _fake_get_device_logs_fail(device_key, limit, project_id):  # noqa: ARG001
    return {"code": -1, "message": "logs unavailable"}


async def _fake_search_device_logs(device_key, query, limit, project_id):  # noqa: ARG001
    return {"code": 0, "data": [{"msg": "found log"}]}


async def _fake_search_device_logs_fail(device_key, query, limit, project_id):  # noqa: ARG001
    return {"code": -1, "message": "search failed"}


async def _fake_bind_client_id(device_key, client_id, token=None):  # noqa: ARG001
    return {"bound": True}


async def _fake_check_benefit(benefit_code, token):  # noqa: ARG001
    return True


class TestGetDevices:
    async def test_with_cloud_devices(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.get_devices", _fake_get_devices
        )
        monkeypatch.setattr(
            "app.core.environment.get_awakened_state", lambda: None
        )
        resp = await client.get("/devices/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["connection_type"] == "cloud"
        assert data[0]["status"] == "online"

    async def test_empty_devices(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.get_devices",
            _fake_get_devices_empty,
        )
        monkeypatch.setattr(
            "app.core.environment.get_awakened_state", lambda: None
        )
        resp = await client.get("/devices/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_cloud_fail_returns_empty(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.get_devices",
            _fake_get_devices_fail,
        )
        monkeypatch.setattr(
            "app.core.environment.get_awakened_state", lambda: None
        )
        resp = await client.get("/devices/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_local_adb_devices(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.get_devices",
            _fake_get_devices_empty,
        )
        local_dev = SimpleNamespace(
            device_id="adb-1", model="OnePlus", os_version="13",
            is_reachable=True, battery_percent=85,
        )
        monkeypatch.setattr(
            "app.core.environment.get_awakened_state",
            lambda: SimpleNamespace(android_devices=[local_dev]),
        )
        resp = await client.get("/devices/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["connection_type"] == "adb"
        assert data[0]["battery_percent"] == 85


class TestSendCommand:
    @pytest.mark.parametrize(
        "fake,path,status",
        [
            (_fake_send_command, "/devices/dev-1/command", 200),
            (_fake_send_command_fail, "/devices/dev-missing/command", 404),
            (_fake_send_command_server_error, "/devices/dev-1/command", 500),
        ],
    )
    async def test_command_flow(self, client, monkeypatch, fake, path, status):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.send_command_to_device",
            fake,
        )
        monkeypatch.setattr(
            "app.api.deps.check_benefit", _fake_check_benefit
        )
        resp = await client.post(
            path,
            json={"command_type": "relay", "params": {}},
        )
        assert resp.status_code == status

    async def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.send_command_to_device",
            _fake_send_command,
        )
        monkeypatch.setattr("app.api.deps.check_benefit", _fake_check_benefit)
        resp = await client.post(
            "/devices/dev-1/command",
            json={"command_type": "relay", "params": {"action": "start"}},
        )
        assert resp.status_code == 200
        assert resp.json()["sent"] is True

    async def test_device_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.send_command_to_device",
            _fake_send_command_fail,
        )
        monkeypatch.setattr("app.api.deps.check_benefit", _fake_check_benefit)
        resp = await client.post(
            "/devices/dev-missing/command",
            json={"command_type": "relay", "params": {}},
        )
        assert resp.status_code == 404

    async def test_server_error(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.send_command_to_device",
            _fake_send_command_server_error,
        )
        monkeypatch.setattr("app.api.deps.check_benefit", _fake_check_benefit)
        resp = await client.post(
            "/devices/dev-1/command",
            json={"command_type": "relay", "params": {}},
        )
        assert resp.status_code == 500


class TestDeviceLogs:
    async def test_get_logs(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.get_device_logs",
            _fake_get_device_logs,
        )
        resp = await client.get("/devices/dev-1/logs?limit=10")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_get_logs_fail(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.get_device_logs",
            _fake_get_device_logs_fail,
        )
        resp = await client.get("/devices/dev-1/logs")
        assert resp.status_code == 500

    async def test_search_logs(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.search_device_logs",
            _fake_search_device_logs,
        )
        resp = await client.get("/devices/dev-1/logs/search?query=error&limit=5")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_search_logs_fail(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.search_device_logs",
            _fake_search_device_logs_fail,
        )
        resp = await client.get("/devices/dev-1/logs/search?query=x")
        assert resp.status_code == 500


class TestBindDevice:
    async def test_bind_client(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager.api.bind_client_id",
            _fake_bind_client_id,
        )
        resp = await client.post(
            "/devices/dev-1/bind",
            json={"client_id": "mobile-abc"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


class TestBindCurrentDevice:
    async def test_success(self, client, monkeypatch):
        async def _bind(_cid):
            return None

        fake_manager = SimpleNamespace(
            link=SimpleNamespace(
                device_key="current-dev",
                bind_client_id=_bind,
            ),
        )
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager", fake_manager
        )
        resp = await client.post(
            "/devices/bind",
            json={"client_id": "mobile-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    async def test_no_device_registered(self, client, monkeypatch):
        fake_manager = SimpleNamespace(link=SimpleNamespace(device_key=None))
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager", fake_manager
        )
        resp = await client.post(
            "/devices/bind",
            json={"client_id": "mobile-123"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"


class TestDebugStatus:
    async def test_returns_status(self, client, monkeypatch):
        fake_link = SimpleNamespace(
            device_key="dev-1",
            device_name="MyPhone",
            is_connected=lambda: True,
        )
        async def _get_token():
            return "tok-1234567890"

        fake_manager = SimpleNamespace(
            get_token=_get_token,
            link=fake_link,
            api=SimpleNamespace(base_url="https://api.example.com"),
        )
        monkeypatch.setattr(
            "app.api.routes.devices.evocloud_manager", fake_manager
        )
        resp = await client.get("/devices/debug/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_logged_in"] is True
        assert data["token_prefix"] == "tok-123456..."
        assert data["device_id"] == "dev-1"
        assert data["is_connected"] is True
