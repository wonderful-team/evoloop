"""
EvoLoop Link - PC Client (Python)
用于电脑端Agent连接云端中转服务
"""
import os
import asyncio
import json
import uuid
import platform
import httpx
import websockets
from typing import Optional, Callable, Dict, Any
from datetime import datetime

from app.logging import logger


class EvoLoopLinkClient:
    """
    EvoLoop Link 云端同步客户端
    负责设备注册、WebSocket连接、指令接收、日志上报
    """

    def __init__(
        self,
        base_url: str = "https://mall.imagicbox.cn",
        ws_url: str = "wss://mall.imagicbox.cn/wss/",
        token: Optional[str] = None,
        device_name: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.ws_url = ws_url
        self.token = token
        self.device_name = device_name or f"{platform.node()}"
        self.device_key = self._get_or_create_device_key()
        self.device_id: Optional[int] = None
        self.client_id: Optional[str] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._command_handler: Optional[Callable[[Dict[str, Any]], None]] = None
        self._reconnect_delay = 5  # seconds

    def _get_or_create_device_key(self) -> str:
        """获取或创建设备唯一标识"""
        key_file = os.path.expanduser("~/.evoloop_device_key")
        if os.path.exists(key_file):
            with open(key_file, "r") as f:
                return f.read().strip()
        else:
            device_key = str(uuid.uuid4())
            with open(key_file, "w") as f:
                f.write(device_key)
            return device_key

    def set_command_handler(self, handler: Callable[[Dict[str, Any]], None]):
        """设置指令处理回调"""
        self._command_handler = handler

    async def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """发送 API 请求"""
        url = f"{self.base_url}{endpoint}"
        params = {"token": self.token}
        if data:
            params.update(data)

        async with httpx.AsyncClient(timeout=30) as client:
            if method.upper() == "GET":
                resp = await client.get(url, params=params)
            else:
                resp = await client.post(url, data=params)
            
            # Debug log
            if resp.status_code != 200:
                logger.error(f"[EvoLoop] API Error {resp.status_code}: {resp.text[:500]}")
            
            # Log successful response for debugging logs
            if "upload" in endpoint:
                logger.info(f"[EvoLoop] API Response ({endpoint}): {resp.text}")

            try:
                return resp.json()
            except json.JSONDecodeError:
                logger.error(f"[EvoLoop] Invalid JSON from {url}: {resp.text[:500]}")
                raise

    async def register_device(self) -> bool:
        """注册设备到云端"""
        try:
            result = await self._api_request(
                "POST",
                "/evolooplink/api/device/register",
                {
                    "device_key": self.device_key,
                    "device_name": self.device_name,
                    "device_type": "desktop",
                    "os_info": f"{platform.system()} {platform.release()}",
                },
            )
            if result.get("code") == 0:
                self.device_id = result["data"]["device_id"]
                logger.info(f"[EvoLoop] Device registered: {self.device_id}")
                return True
            else:
                logger.error(f"[EvoLoop] Register failed: {result.get('message')}")
                return False
        except Exception as e:
            logger.error(f"[EvoLoop] Register error: {e}")
            return False

    async def heartbeat(self):
        """发送心跳"""
        if not self.device_id:
            return
        try:
            await self._api_request(
                "POST",
                "/evolooplink/api/device/heartbeat",
                {"device_id": self.device_id},
            )
        except Exception as e:
            logger.warning(f"[EvoLoop] Heartbeat error: {e}")

    async def bind_client_id(self, client_id: str) -> bool:
        """绑定 WebSocket client_id"""
        if not self.device_id:
            return False
        try:
            result = await self._api_request(
                "POST",
                "/evolooplink/api/device/bind",
                {"device_id": self.device_id, "client_id": client_id},
            )
            if result.get("code") == 0:
                self.client_id = client_id
                logger.info(f"[EvoLoop] Client bound: {client_id}")
                return True
            else:
                logger.error(f"[EvoLoop] Bind failed: {result.get('message')}")
                return False
        except Exception as e:
            logger.error(f"[EvoLoop] Bind error: {e}")
            return False

    async def upload_log(
        self,
        thread_id: str,
        log_type: str,
        content: Any,
        command_id: Optional[int] = None,
    ):
        """上传执行日志"""
        if not self.device_id:
            return
        try:
            data = {
                "device_id": self.device_id,
                "thread_id": thread_id,
                "type": log_type,
                "content": json.dumps(content) if isinstance(content, dict) else str(content),
            }
            if command_id:
                data["command_id"] = command_id

            result = await self._api_request("POST", "/evolooplink/api/log/upload", data)
            if result.get("code") != 0:
                logger.warning(f"[EvoLoop] Log upload failed: {result.get('message')}")
        except Exception as e:
            logger.error(f"[EvoLoop] Log upload error: {e}")

    async def upload_logs_batch(self, logs: list):
        """批量上传日志"""
        if not self.device_id or not logs:
            return
        try:
            data = {
                "device_id": self.device_id,
                "logs": json.dumps(logs),
            }
            await self._api_request("POST", "/evolooplink/api/log/upload", data)
        except Exception as e:
            logger.error(f"[EvoLoop] Batch log upload error: {e}")

    async def update_command_status(
        self,
        command_id: int,
        status: int,
        result: Optional[str] = None,
    ):
        """更新指令状态"""
        try:
            data = {"command_id": command_id, "status": status}
            if result:
                data["result"] = result
            await self._api_request("POST", "/evolooplink/api/command/updateStatus", data)
        except Exception as e:
            logger.error(f"[EvoLoop] Update command status error: {e}")

    async def _handle_ws_message(self, message: str):
        """处理 WebSocket 消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "init":
                # 收到 init 消息，获取 client_id 并绑定
                client_id = data.get("data", {}).get("client_id")
                if client_id:
                    await self.bind_client_id(client_id)

            elif msg_type == "new_command":
                # 收到新指令
                command_data = data.get("data", {})
                logger.info(f"[EvoLoop] Received command: {command_data.get('command_id')}")
                if self._command_handler:
                    # 异步执行指令处理
                    asyncio.create_task(self._execute_command(command_data))

        except json.JSONDecodeError:
            logger.warning(f"[EvoLoop] Invalid WS message: {message[:100]}")
        except Exception as e:
            logger.error(f"[EvoLoop] WS message handling error: {e}")

    async def _execute_command(self, command_data: Dict[str, Any]):
        """执行指令并上报日志"""
        command_id = command_data.get("command_id")
        thread_id = command_data.get("thread_id", "")
        content = command_data.get("content", {})

        # 更新状态为执行中
        await self.update_command_status(command_id, 2)  # STATUS_RUNNING

        try:
            # 调用用户设置的处理函数
            if self._command_handler:
                if asyncio.iscoroutinefunction(self._command_handler):
                     await self._command_handler(command_data)
                else:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._command_handler, command_data
                    )

            # 更新状态为完成
            await self.update_command_status(command_id, 3)  # STATUS_COMPLETED

        except Exception as e:
            logger.error(f"[EvoLoop] Command execution error: {e}")
            await self.update_command_status(command_id, 4, str(e))  # STATUS_FAILED

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self._running:
            await self.heartbeat()
            await asyncio.sleep(30)  # 每30秒心跳

    async def connect(self):
        """建立 WebSocket 连接"""
        while self._running:
            try:
                logger.info(f"[EvoLoop] Connecting to {self.ws_url}...")
                async with websockets.connect(self.ws_url) as ws:
                    self.ws = ws
                    logger.info("[EvoLoop] WebSocket connected")

                    async for message in ws:
                        await self._handle_ws_message(message)

            except websockets.ConnectionClosed as e:
                logger.warning(f"[EvoLoop] WebSocket closed: {e}")
            except Exception as e:
                logger.error(f"[EvoLoop] WebSocket error: {e}")

            if self._running:
                logger.info(f"[EvoLoop] Reconnecting in {self._reconnect_delay}s...")
                await asyncio.sleep(self._reconnect_delay)

    async def start(self):
        """启动客户端"""
        if not self.token:
            logger.error("[EvoLoop] Token not set!")
            return

        self._running = True

        # 注册设备
        if not await self.register_device():
            logger.error("[EvoLoop] Device registration failed, aborting")
            return

        # 启动心跳和 WebSocket 连接
        await asyncio.gather(
            self._heartbeat_loop(),
            self.connect(),
        )

    def stop(self):
        """停止客户端"""
        self._running = False
        if self.ws:
            asyncio.create_task(self.ws.close())


# 全局客户端实例
evoloop_client: Optional[EvoLoopLinkClient] = None


def get_evoloop_client() -> Optional[EvoLoopLinkClient]:
    """获取全局客户端实例"""
    return evoloop_client


def init_evoloop_client(token: str, device_name: Optional[str] = None) -> EvoLoopLinkClient:
    """初始化全局客户端"""
    global evoloop_client
    evoloop_client = EvoLoopLinkClient(token=token, device_name=device_name)
    return evoloop_client


def set_evoloop_client(client: EvoLoopLinkClient):
    """设置全局客户端实例"""
    global evoloop_client
    evoloop_client = client
