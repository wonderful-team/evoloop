
import os
import json
import time
import hashlib
import hmac
import asyncio
import platform
import uuid
import httpx
import websockets
import logging
from typing import Optional, Dict, Any, Callable

from app.utils import json as json_utils
from app.utils import file as file_utils
from app.utils import http as http_utils
from app.utils.security import generate_hmac_signature
from app.utils.id import gen_uuid
from app.utils.async_utils import run_in_thread

from app.core.config import settings
from app.domain.system.service import SystemConfigService

logger = logging.getLogger(__name__)


class ImagicBoxClient:
    """
    Unified Client for ImagicBox (Member Center) & EvoLoop Link.
    
    Responsibilities:
    1. Business Logic (User, Projects, Tasks) - via REST API
    2. Device Connection (Registration, Heartbeat, Commands) - via WebSocket/REST
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ImagicBoxClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
            
        # --- Config ---
        self.base_url = str(settings.IMAGICBOX_API_URL).rstrip('/')
        self.ws_url = str(settings.IMAGICBOX_WS_URL)
        self.api_key = settings.IMAGICBOX_API_KEY
        self.api_secret = settings.IMAGICBOX_API_SECRET
        self.timeout = 30.0
        
        # --- Authentication ---
        self._user_token: Optional[str] = None
        self._member_id: Optional[int] = None
        
        # --- Device Link State ---
        db_device_name = SystemConfigService.get_value("IMAGICBOX_DEVICE_NAME") # Legacy key in DB? Or migrate?
        self.device_name = settings.IMAGICBOX_DEVICE_NAME or db_device_name or f"{platform.node()}"
        self.device_key = self._get_or_create_device_key()
        self.device_id: Optional[int] = None
        self.client_id: Optional[str] = None
        
        # --- Connection State ---
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_delay = 5
        self._client_session: Optional[httpx.AsyncClient] = None # Deprecated in favor of _clients
        self._clients: Dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
        
        # --- Handlers ---
        self._command_handler: Optional[Callable[[Dict[str, Any]], None]] = None
        self._event_handler: Optional[Callable[[str, Dict[str, Any]], None]] = None

        self._load_token()
        self._initialized = True
        logger.info(f"ImagicBoxClient Initialized (URL: {self.base_url})")

    async def get_client(self) -> httpx.AsyncClient:
        """Get httpx client bound to current event loop"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Should mostly be called within loop, but fallback if not?
            # Creating client without loop context will bind to whatever loop runs it next?
            # Httpx binds on first use.
            # But here we need a key.
            return http_utils.create_client(timeout=self.timeout)

        if loop in self._clients:
            client = self._clients[loop]
            if not client.is_closed:
                return client
        
        # Create new
        client = http_utils.create_client(timeout=self.timeout)
        self._clients[loop] = client
        return client

    async def close(self):
        # Close all active clients
        for client in self._clients.values():
            if not client.is_closed:
                await client.aclose()
        self._clients.clear()

    # --- Authentication Helper ---
    
    def _load_token(self):
        """Load token from local storage or environment"""
        try:
            # Check env/settings first
            if settings.IMAGICBOX_ACCESS_TOKEN:
                self._user_token = settings.IMAGICBOX_ACCESS_TOKEN
                return

            auth_file = os.path.join(os.getcwd(), ".evoloop", "auth.json")
            if os.path.exists(auth_file):
                content = file_utils.read_file(auth_file)
                data = json_utils.loads(content)
                self._user_token = data.get("token")
                self._member_id = data.get("member_id")
        except Exception as e:
            logger.warning(f"Failed to load auth token: {e}")

    def _save_token(self, token: str, member_id: int):
        try:
            self._user_token = token
            self._member_id = member_id
            
            auth_dir = os.path.join(os.getcwd(), ".evoloop")
            os.makedirs(auth_dir, exist_ok=True)
            
            with open(os.path.join(auth_dir, "auth.json"), "w") as f:
                json.dump({"token": token, "member_id": member_id}, f)
                
            # Sync to Redis for other processes/cache
            # We don't block on this sync save, but we should start async task or ignore
            # Since this is sync method called by login logic, we keep it simple.
            # But wait, login logic is now async in controller.
            # Ideally this should be async.
        except Exception as e:
            logger.error(f"Failed to save auth token: {e}")

    async def logout(self):
        self._user_token = None
        self._member_id = None
        try:
            auth_file = os.path.join(os.getcwd(), ".evoloop", "auth.json")
            if os.path.exists(auth_file):
                os.remove(auth_file)
        except:
            pass
        await self.stop_device_link()

    def get_status(self):
        return {
            "is_logged_in": bool(self._user_token),
            "member_id": self._member_id,
            "device_connected": self._running and (self.ws is not None),
            "device_id": self.device_id
        }

    # --- Core Request Wrapper (Async) ---

    def _generate_signature(self, method: str, uri: str, body: str, timestamp: int) -> str:
        string_to_sign = f"{method}\\n{uri}\\n{body}\\n{timestamp}"
        return generate_hmac_signature(self.api_secret, string_to_sign)

    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None, token: Optional[str] = None) -> Dict:
        """
        Unified Async Request Handler.
        Includes Token Injection & Signature.
        """
        client = await self.get_client()
        active_token = token or self._user_token
        
        url = f"{self.base_url}{endpoint}"
        timestamp = int(time.time())
        body_str = json_utils.dumps(data) if data else ""
        
        headers = {
            'Content-Type': 'application/json',
            'X-Timestamp': str(timestamp)
        }
        
        if self.api_key and self.api_secret:
            headers['X-API-Key'] = self.api_key
            headers['X-Signature'] = self._generate_signature(method, endpoint, body_str, timestamp)
            
        # Params preparation
        if params is None:
            params = {}
        if active_token:
            params['token'] = active_token

        try:
            logger.debug(f"Req: {method} {endpoint}")
            resp = await client.request(method, url, params=params, json=data, headers=headers)
            
            # Simple error handling
            if resp.status_code >= 400:
                logger.error(f"API Error {resp.status_code}: {resp.text[:200]}")
            
            try:
                res_json = resp.json()
                return res_json
            except json.JSONDecodeError:
                return {"code": -1, "message": f"Invalid JSON: {resp.text[:100]}"}

        except httpx.RequestError as e:
            logger.error(f"Request connection error: {e}")
            return {"code": -1, "message": str(e)}
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return {"code": -1, "message": str(e)}

    # --- Business APIs (Async) ---

    async def login(self, username, password) -> Dict:
        """Login and return token"""
        res = await self._request("POST", "/api/login/login", data={"username": username, "password": password})
        if res.get("code", -1) >= 0:
            token = res.get("data", {}).get("token")
            if token:
                self._save_token(token, 0)
                # Auto-start device link
                asyncio.create_task(self.start_device_link())
                return {"success": True, "token": token}
        return {"success": False, "message": res.get("message", "Login failed")}

    async def get_user_info(self, token: Optional[str] = None) -> Dict:
        return await self._request("GET", "/api/member/info", token=token)

    # Project
    async def get_projects(self, page=1, page_size=100) -> Dict:
        return await self._request("GET", "/projectmanage/api/ProjectOpen/projects", params={"page": page, "page_size": page_size})

    async def create_project(self, name: str, description: str, path: str) -> Dict:
        payload = {"name": name, "description": description, "path": path, "source": "EvoLoopV3"}
        return await self._request("POST", "/projectmanage/api/ProjectOpen/createProject", data=payload)

    async def update_project(self, project_id: int, description: str) -> Dict:
        return await self._request("POST", "/projectmanage/api/ProjectOpen/updateProject", data={"project_id": project_id, "project_desc": description})

    async def delete_project(self, project_id: int) -> Dict:
        return await self._request("POST", "/projectmanage/api/ProjectOpen/deleteProject", data={"project_id": project_id})

    # Task
    async def get_project_tasks(self, project_id: int, page=1, page_size=50, status=None, token=None) -> Dict:
        p = {"project_id": project_id, "page": page, "page_size": page_size}
        if status is not None: p["status"] = status
        return await self._request("GET", "/projectmanage/api/task/projectTasks", params=p, token=token)

    async def get_task_detail(self, task_id: int, token=None) -> Dict:
        return await self._request("GET", f"/projectmanage/api/task/detail/{task_id}", token=token)

    async def create_task(self, data: Dict, token=None) -> Dict:
        return await self._request("POST", "/projectmanage/api/task/create", data=data, token=token)

    async def update_task(self, task_id: int, data: Dict, token=None) -> Dict:
        return await self._request("PUT", f"/projectmanage/api/task/update/{task_id}", data=data, token=token)

    async def delete_task(self, task_id: int, token=None) -> Dict:
        return await self._request("DELETE", "/projectmanage/api/task/delete", data={"task_id": task_id}, token=token)

    async def update_task_status(self, task_id: int, status: int, progress: int = 0, token=None) -> Dict:
        return await self._request("POST", "/projectmanage/api/task/updateStatus", data={"task_id": task_id, "status": status, "progress": progress}, token=token)

    # Modules
    async def get_budget_list(self, project_id: int, page=1, page_size=50, token=None) -> Dict:
        return await self._request("GET", "/projectmanage/api/budget/lists", params={"project_id": project_id, "page": page, "page_size": page_size}, token=token)

    async def get_budget_overview(self, project_id: int, token=None) -> Dict:
        return await self._request("GET", "/projectmanage/api/budget/overview", params={"project_id": project_id}, token=token)

    async def get_timesheet_list(self, project_id: int, page=1, page_size=50, token=None) -> Dict:
        return await self._request("GET", "/projectmanage/api/timesheet/lists", params={"project_id": project_id, "page": page, "page_size": page_size}, token=token)

    async def add_timesheet_quick(self, data: Dict, token=None) -> Dict:
        return await self._request("POST", "/projectmanage/api/timesheet/quickAdd", data=data, token=token)

    async def get_project_statistics(self, project_id=0, token=None) -> Dict:
        p = {"project_id": project_id} if project_id else {}
        return await self._request("GET", "/projectmanage/api/project/statistics", params=p, token=token)

    async def get_ai_global_config(self) -> Dict:
        return await self._request("GET", "/api/AI/globalConfig")

    # Cancellation
    async def get_cancellation_info(self) -> Dict:
        return await self._request("GET", "/membercancel/api/membercancel/info")
    
    async def apply_cancellation(self) -> Dict:
        return await self._request("POST", "/membercancel/api/membercancel/apply")

    async def cancel_cancellation_apply(self) -> Dict:
        return await self._request("POST", "/membercancel/api/membercancel/cancelApply")


    # --- Device Link / WebSocket Logic ---

    def _get_or_create_device_key(self) -> str:
        key_file = os.path.expanduser("~/.evoloop_device_key")
        if os.path.exists(key_file):
                return file_utils.read_file(key_file).strip()
        else:
            dk = gen_uuid()
            file_utils.write_file(key_file, dk)
            return dk

    def set_command_handler(self, handler: Callable):
        self._command_handler = handler

    def set_event_handler(self, handler: Callable):
        self._event_handler = handler

    async def start_device_link(self, token: Optional[str] = None):
        """Start the WebSocket connection and Heartbeat """
        if token:
            self._user_token = token
            
        if self._running:
            return
        
        if not self._user_token:
            logger.warning("[ImagicBox] Cannot start Device Link: No Token")
            return

        self._running = True
        
        # Register
        if not await self._register_device():
            logger.error("[ImagicBox] Device registration failed. Aborting Link.")
            self._running = False
            return

        logger.info("[ImagicBox] Starting Device Link Loops...")
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._ws_connect_loop())

    async def stop_device_link(self):
        self._running = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.warning(f"Error closing WS: {e}")
            self.ws = None

    # --- Device Management (Proxy) ---

    async def get_devices(self) -> Dict:
        """Get list of devices for current user"""
        return await self._request("GET", "/evolooplink/api/device/list")

    async def send_command_to_device(self, device_id: int, cmd_data: Dict) -> Dict:
        """Send remote command to a device"""
        data = {"device_id": device_id, **cmd_data}
        return await self._request("POST", "/evolooplink/api/command/send", data=data)

    async def get_device_logs(self, device_id: int, limit=20, project_id=None) -> Dict:
        params = {"device_id": device_id, "limit": limit}
        if project_id: params["project_id"] = project_id
        return await self._request("GET", "/evolooplink/api/log/recent", params=params)

    async def search_device_logs(self, device_id: int, query: str, limit=20, project_id=None) -> Dict:
        params = {"device_id": device_id, "query": query, "limit": limit}
        if project_id: params["project_id"] = project_id
        return await self._request("GET", "/evolooplink/api/log/search", params=params)

    async def _register_device(self) -> bool:
        res = await self._request(
            "POST", 
            "/evolooplink/api/device/register", 
            data={
                "device_key": self.device_key,
                "device_name": self.device_name,
                "device_type": "desktop",
                "os_info": f"{platform.system()} {platform.release()}"
            }
        )
        if res.get("code") == 0:
            self.device_id = res["data"]["device_id"]
            logger.info(f"[ImagicBox] Device Registered ID: {self.device_id}")
            return True
        logger.error(f"[ImagicBox] Register Failed: {res.get('message')}")
        return False

    async def _heartbeat_loop(self):
        while self._running:
            if self.device_id:
                try:
                    await self._request("POST", "/evolooplink/api/device/heartbeat", data={"device_id": self.device_id})
                except Exception as e:
                    logger.debug(f"Heartbeat failed: {e}")
            await asyncio.sleep(30)

    async def _ws_connect_loop(self):
        while self._running:
            try:
                logger.info(f"[ImagicBox] Connecting WS to {self.ws_url}...")
                async with websockets.connect(self.ws_url) as ws:
                    self.ws = ws
                    logger.info("[ImagicBox] WS Connected")
                    async for message in ws:
                        await self._handle_ws_message(message)
            except Exception as e:
                logger.warning(f"[ImagicBox] WS Connection Error: {e}")
            
            if self._running:
                await asyncio.sleep(self._reconnect_delay)

    async def _handle_ws_message(self, message: str):
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "init":
                client_id = data.get("data", {}).get("client_id")
                if client_id:
                    await self._bind_client_id(client_id)
            
            elif msg_type == "new_command":
                cmd = data.get("data", {})
                if self._command_handler:
                    asyncio.create_task(self._execute_command_wrapper(cmd))
            
            elif msg_type == "project_switch":
                if self._event_handler:
                    if asyncio.iscoroutinefunction(self._event_handler):
                        asyncio.create_task(self._event_handler(msg_type, data.get("data", {})))
                    else:
                        self._event_handler(msg_type, data.get("data", {}))

        except Exception as e:
            logger.error(f"[ImagicBox] WS Handle Error: {e}")

    async def _bind_client_id(self, client_id: str):
        if not self.device_id: return
        res = await self._request("POST", "/evolooplink/api/device/bind", data={"device_id": self.device_id, "client_id": client_id})
        if res.get("code") == 0:
            self.client_id = client_id
            logger.info(f"[ImagicBox] Bound Client ID: {client_id}")

    async def _execute_command_wrapper(self, cmd_data):
        cmd_id = cmd_data.get("command_id")
        await self.update_command_status(cmd_id, 2) # Running
        try:
            if asyncio.iscoroutinefunction(self._command_handler):
                await self._command_handler(cmd_data)
            else:
                await run_in_thread(self._command_handler, cmd_data)
            await self.update_command_status(cmd_id, 3) # Completed
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            await self.update_command_status(cmd_id, 4, str(e)) # Failed

    async def update_command_status(self, command_id, status, result=None):
        data = {"command_id": command_id, "status": status}
        if result: data["result"] = result
        await self._request("POST", "/evolooplink/api/command/updateStatus", data=data)

    async def upload_log(self, thread_id, log_type, content, command_id=None, project_id=None):
        if not self.device_id: return
        data = {
            "device_id": self.device_id, 
            "thread_id": thread_id, 
            "type": log_type, 
            "content": json_utils.dumps(content) if isinstance(content, (dict, list)) else str(content)
        }
        if command_id: data["command_id"] = command_id
        if project_id: data["project_id"] = project_id
        await self._request("POST", "/evolooplink/api/log/upload", data=data)


# Global Instance
imagicbox_client = ImagicBoxClient()
