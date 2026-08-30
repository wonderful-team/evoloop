"""EvoCloud devices mixin: devices, heartbeat, logs, cancellation."""

from typing import Any

from app.core.schemas.canonical import (
    Endpoint,
    EndpointKind,
    MessageType,
    create_envelope,
)
from app.models.schemas.auth import EvoCloudProxyResponse


class DevicesMixin:
    """Device management and cancellation API methods."""

    async def get_devices(self, token: str | None = None) -> dict:
        return await self.request("GET", "/api/v1/devices", token=token)

    async def send_command_to_device(
        self,
        device_key: str,
        cmd_data: dict,
        token: str | None = None,
        envelope_type: str = MessageType.COMMAND_RELAY.value,
    ) -> dict:
        """Send a command to a device through the Gateway using canonical envelope v2.0."""
        body = dict(cmd_data)

        # Normalize legacy command_type/params into action/content if caller used them.
        if "action" not in body and "command_type" in body:
            body["action"] = body.pop("command_type")
        if "content" not in body and "params" in body:
            body["content"] = body.pop("params")
        if "action" not in body:
            body["action"] = "relay"

        envelope = create_envelope(
            type=envelope_type,
            body=body,
            source=Endpoint(kind=EndpointKind.BACKEND),
            target=Endpoint(kind=EndpointKind.MOBILE, device_key=device_key),
        ).model_dump()
        data = {"target_device_key": device_key, "envelope": envelope}
        return await self.request(
            "POST", "/api/v1/message/send", data=data, token=token
        )

    async def get_device_logs(
        self, device_key: str, limit=20, project_id=None, token: str | None = None
    ) -> dict:
        params = {"device_key": device_key, "limit": limit}
        if project_id is not None:
            params["project_id"] = project_id
        return await self.request(
            "GET", "/evolooplink/api/log/recent", params=params, token=token
        )

    async def search_device_logs(
        self,
        device_key: str,
        query: str,
        limit=20,
        project_id=None,
        token: str | None = None,
    ) -> dict:
        params = {"device_key": device_key, "query": query, "limit": limit}
        if project_id is not None:
            params["project_id"] = project_id
        return await self.request(
            "GET", "/evolooplink/api/log/search", params=params, token=token
        )

    async def bind_client_id(
        self, device_key: str, client_id: str, token: str | None = None
    ) -> dict:
        return await self.request(
            "POST",
            "/api/v1/devices/bind",
            data={"device_key": device_key, "client_id": client_id},
            token=token,
        )

    async def register_device(
        self, fingerprint: str, name: str, os_info: str, token: str | None = None
    ) -> dict:
        from app.core.environment.discovery import EnvironmentProbe

        return await self.request(
            "POST",
            "/evolooplink/api/device/register",
            data={
                "fingerprint": fingerprint,
                "device_name": name,
                "device_type": EnvironmentProbe.get_inferred_device_type(),
                "os_info": os_info,
            },
            token=token,
        )

    async def sync_device_info(
        self, device_key: str, info: dict[str, Any], token: str | None = None
    ) -> dict:
        payload = {"device_key": device_key, **info}
        return await self.request(
            "POST",
            "/evolooplink/api/device/updateInfo",
            data=payload,
            token=token,
        )

    async def send_heartbeat(self, device_key: str, token: str | None = None):
        await self.request(
            "POST", f"/api/v1/devices/{device_key}/heartbeat", token=token
        )

    # --- Cancellation ---

    async def get_cancellation_info(
        self, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "GET", "/membercancel/api/membercancel/info", token=token
            )
        )

    async def apply_cancellation(
        self, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "POST", "/membercancel/api/membercancel/apply", token=token
            )
        )

    async def cancel_cancellation_apply(
        self, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "POST", "/membercancel/api/membercancel/cancelApply", token=token
            )
        )
