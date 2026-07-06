"""EvoCloud sync mixin: conversation sync, messages, upload."""

import hashlib
import logging
import os

import httpx

from app.constants import DEFAULT_PROJECT_ID

logger = logging.getLogger(__name__)


class SyncMixin:
    """Conversation sync and file upload API methods."""

    async def sync_conversation(
        self, device_key: str, conversation: dict, token: str | None = None
    ) -> dict:
        data = {"device_key": device_key, "conversation": conversation}
        return await self.request(
            "POST", "/evolooplink/api/sync/conversation", data=data, token=token
        )

    async def sync_delete_conversation(
        self, device_key: str, conversation_id: str, token: str | None = None
    ) -> dict:
        data = {"device_key": device_key, "conversation_id": conversation_id}
        return await self.request(
            "POST", "/evolooplink/api/conversation/delete", data=data, token=token
        )

    async def sync_messages(
        self,
        device_key: str,
        thread_id: str,
        messages: list[dict],
        token: str | None = None,
    ) -> dict:
        data = {
            "device_key": device_key,
            "thread_id": thread_id,
            "messages": messages,
        }
        return await self.request(
            "POST", "/evolooplink/api/sync/messages", data=data, token=token
        )

    async def sync_delete_messages(
        self,
        device_key: str,
        thread_id: str,
        message_ids: list[str],
        token: str | None = None,
    ) -> dict:
        data = {
            "device_key": device_key,
            "thread_id": thread_id,
            "message_ids": message_ids,
        }
        return await self.request(
            "POST", "/evolooplink/api/sync/deleteMessages", data=data, token=token
        )

    async def sync_rewind_messages(
        self,
        device_key: str,
        thread_id: str,
        target_sequence: int,
        include_target: bool,
        token: str | None = None,
    ) -> dict:
        data = {
            "device_key": device_key,
            "thread_id": thread_id,
            "target_sequence": target_sequence,
            "include_target": include_target,
        }
        return await self.request(
            "POST", "/evolooplink/api/sync/rewindMessages", data=data, token=token
        )

    async def sync_full_conversations(
        self, device_key: str, data: dict, token: str | None = None
    ) -> dict:
        payload = {"device_key": device_key, "data": data}
        return await self.request(
            "POST", "/evolooplink/api/sync/full", data=payload, token=token
        )

    async def check_sync_status(
        self, device_key: str, conversation_ids: list[str], token: str | None = None
    ) -> dict:
        return await self.request(
            "GET", "/evolooplink/api/sync/status",
            params={"device_key": device_key, "conversation_ids": conversation_ids},
            token=token,
        )

    async def get_conversations(
        self,
        project_id: int = DEFAULT_PROJECT_ID,
        page: int = 1,
        page_size: int = 20,
        token: str | None = None,
    ) -> dict:
        params = {"page": page, "page_size": page_size}
        if project_id > 0:
            params["project_id"] = project_id
        return await self.request(
            "GET", "/evolooplink/api/conversation/list", params=params, token=token
        )

    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        before_message_id: str | None = None,
        token: str | None = None,
    ) -> dict:
        params = {"conversation_id": conversation_id, "limit": limit}
        if before_message_id:
            params["before_message_id"] = before_message_id
        return await self.request(
            "GET", "/evolooplink/api/conversation/messages", params=params, token=token
        )

    async def upload_file(self, file_path: str, token: str | None = None) -> dict:
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        md5_val = hash_md5.hexdigest()

        try:
            url = f"{self._get_base_url(is_gateway=False)}/api/upload/chatfile"
            headers = {}
            active_token = token or await self.get_token()
            if active_token:
                headers["Authorization"] = f"Bearer {active_token}"

            async with httpx.AsyncClient() as client:
                with open(file_path, "rb") as f:
                    files = {"file": (filename, f)}
                    response = await client.post(
                        url, headers=headers, files=files, timeout=60.0
                    )
                    if response.status_code == 200:
                        res_json = response.json()
                        if res_json.get("code") == 0:
                            data = res_json.get("data") or {}
                            path = data.get("path") or ""
                            if path.startswith("/"):
                                path = path[1:]
                            download_url = f"{self.root_url}/{path}" if path else None
                            return {
                                "download_url": download_url,
                                "md5": md5_val,
                                "file_size": file_size,
                                "filename": filename,
                            }
            return {
                "download_url": f"{self.base_url}/api/v1/files/raw?path=uploads/{filename}",
                "md5": md5_val,
                "file_size": file_size,
                "filename": filename,
            }
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[EvoCloud] Upload failed: {e}, using local fallback")
            return {
                "download_url": f"{self.base_url}/api/v1/files/raw?path=uploads/{filename}",
                "md5": md5_val,
                "file_size": file_size,
                "filename": filename,
            }
