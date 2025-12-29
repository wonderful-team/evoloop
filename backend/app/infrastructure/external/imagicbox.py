import os
import json
import time
import hashlib
import hmac
import requests
import logging
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

class ImagicBoxClient:
    """
    Client for ImagicBox (Member Center) API.
    Handles Authentication and Project Management.
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
            
        self.base_url = settings.IMAGICBOX_API_URL.rstrip('/')
        # Optional: API Key/Secret for signed requests (if needed later)
        self.api_key = settings.IMAGICBOX_API_KEY
        self.api_secret = settings.IMAGICBOX_API_SECRET
        
        self.timeout = 30
        self.session = requests.Session()
        
        # In-memory storage for token
        # In production, we should persist this to a file to survive restarts
        self._user_token = None
        self._member_id = None
        self._load_token()

        self._initialized = True

    def _load_token(self):
        """Load token from local storage (.evoloop/auth.json)"""
        try:
            auth_file = os.path.join(os.getcwd(), ".evoloop", "auth.json")
            if os.path.exists(auth_file):
                with open(auth_file, "r") as f:
                    data = json.load(f)
                    self._user_token = data.get("token")
                    self._member_id = data.get("member_id")
                    logger.info(f"Loaded saved session for member {self._member_id}")
        except Exception as e:
            logger.warning(f"Failed to load auth token: {e}")

    def _save_token(self, token: str, member_id: int):
        """Save token to local storage"""
        try:
            self._user_token = token
            self._member_id = member_id
            
            auth_dir = os.path.join(os.getcwd(), ".evoloop")
            os.makedirs(auth_dir, exist_ok=True)
            
            with open(os.path.join(auth_dir, "auth.json"), "w") as f:
                json.dump({"token": token, "member_id": member_id}, f)
        except Exception as e:
            logger.error(f"Failed to save auth token: {e}")

    def logout(self):
        """Clear session"""
        self._user_token = None
        self._member_id = None
        try:
            auth_file = os.path.join(os.getcwd(), ".evoloop", "auth.json")
            if os.path.exists(auth_file):
                os.remove(auth_file)
        except:
            pass

    def get_status(self):
        """Get current auth status"""
        return {
            "is_logged_in": bool(self._user_token),
            "member_id": self._member_id
        }

    def login(self, username, password) -> Dict:
        """
        Login with username/password.
        Calls /api/login/login
        """
        url = f"{self.base_url}/api/login/login"
        payload = {
            "username": username,
            "password": password
        }
        
        logger.info(f"Attempting login to {url}")
        try:
            # Login endpoint is usually public, no signature needed
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            res_json = resp.json()
            
            if res_json.get("code") >= 0:
                data = res_json.get("data", {})
                token = data.get("token")
                # Usually login returns member_id in data or we fetch it later
                # Based on PHP code: return ['token' => $token, 'can_receive_registergift' => ...]
                # It doesn't seem to return member_id explicitly in that array, but let's assume valid token.
                # We might need to fetch profile or parse token if it's JWT (it's random string in Niushop usually).
                # Actually Login.php createToken returns token.
                
                # Let's save token. We might not have member_id yet.
                self._save_token(token, 0) # 0 as placeholder
                return {"success": True, "token": token}
            else:
                return {"success": False, "message": res_json.get("message", "Login failed")}
                
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return {"success": False, "message": str(e)}

    def get_current_project(self) -> Dict:
        """
        Get current project. 
        Calls /projectmanage/api/ProjectOpen/getCurrentProject
        Requires Token.
        """
        return self._make_request("GET", "/projectmanage/api/ProjectOpen/getCurrentProject")

    def get_projects(self, page=1, page_size=100) -> Dict:
        """
        Get project list.
        Calls /projectmanage/api/ProjectOpen/projects
        Requires Token.
        """
        params = {"page": page, "page_size": page_size}
        return self._make_request("GET", "/projectmanage/api/ProjectOpen/projects", params=params)

    def update_project(self, project_id: int, description: str) -> Dict:
        """
        Update project description.
        Calls /projectmanage/api/ProjectOpen/updateProject
        Requires Token.
        """
        payload = {
            "project_id": project_id,
            "project_desc": description
        }
        # Note: updateProject expects POST with body
        return self._make_request("POST", "/projectmanage/api/ProjectOpen/updateProject", data=payload)

    def create_project(self, name: str, description: str, path: str) -> Dict:
        """
        Create a new project in Member Center.
        Calls /projectmanage/api/ProjectOpen/createProject
        """
        payload = {
            "name": name,
            "description": description,
            "path": path,
            "source": "EvoLoopV3"
        }
        return self._make_request("POST", "/projectmanage/api/ProjectOpen/createProject", data=payload)

    def delete_project(self, project_id: int) -> Dict:
        """
        Delete project in Member Center.
        Calls /projectmanage/api/ProjectOpen/deleteProject
        """
        payload = {"project_id": project_id}
        return self._make_request("POST", "/projectmanage/api/ProjectOpen/deleteProject", data=payload)

    # --- Member Cancellation ---

    def get_cancellation_info(self) -> Dict:
        """
        Get member cancellation info.
        Calls /membercancel/api/membercancel/info
        """
        return self._make_request("GET", "/membercancel/api/membercancel/info")

    def apply_cancellation(self) -> Dict:
        """
        Apply for member cancellation.
        Calls /membercancel/api/membercancel/apply
        """
        return self._make_request("POST", "/membercancel/api/membercancel/apply")

    def cancel_cancellation_apply(self) -> Dict:
        """
        Cancel the application for member cancellation.
        Calls /membercancel/api/membercancel/cancelApply
        """
        return self._make_request("POST", "/membercancel/api/membercancel/cancelApply")

    # --- Project Task Management ---

    def get_project_tasks(self, project_id: int, page: int = 1, page_size: int = 50, status: Optional[int] = None, token: Optional[str] = None) -> Dict:
        """
        Get tasks for a project.
        Calls /projectmanage/api/task/projectTasks
        """
        params = {
            "project_id": project_id,
            "page": page,
            "page_size": page_size
        }
        if status is not None:
            params["status"] = status
        return self._make_request("GET", "/projectmanage/api/task/projectTasks", params=params, token=token)

    def get_task_detail(self, task_id: int, token: Optional[str] = None) -> Dict:
        """
        Get task details.
        Calls /projectmanage/api/task/detail
        """
        # Note: The API might be /projectmanage/api/task/detail/{id} or query param
        # Based on analysis, it seemed to be detail/{id} or query. 
        # Let's assume path param based on Vue code: `/projectmanage/api/task/detail/${this.taskId}` ??
        # Wait, Vue code says: hybridApiCall('GET', `/projectmanage/api/task/detail/${this.taskId}`, {}) (Step 70, Line 471)
        # But wait, looking at python code or php controller...
        # Task.php usually maps `detail` action. 
        # Let's try path param style first as per Vue code usage observation.
        return self._make_request("GET", f"/projectmanage/api/task/detail/{task_id}", token=token)

    def create_task(self, data: Dict, token: Optional[str] = None) -> Dict:
        """
        Create a task.
        Calls /projectmanage/api/task/create
        """
        return self._make_request("POST", "/projectmanage/api/task/create", data=data, token=token)

    def update_task(self, task_id: int, data: Dict, token: Optional[str] = None) -> Dict:
        """
        Update a task.
        Calls /projectmanage/api/task/update/{id}
        """
        return self._make_request("PUT", f"/projectmanage/api/task/update/{task_id}", data=data, token=token)

    def delete_task(self, task_id: int, token: Optional[str] = None) -> Dict:
        """
        Delete a task.
        Calls /projectmanage/api/task/delete
        """
        return self._make_request("DELETE", "/projectmanage/api/task/delete", data={"task_id": task_id}, token=token)
    
    def update_task_status(self, task_id: int, status: int, progress: int = 0, token: Optional[str] = None) -> Dict:
         """
         Update task status.
         Calls /projectmanage/api/task/updateStatus
         """
         data = {
             "task_id": task_id,
             "status": status,
             "progress": progress
         }
         return self._make_request("POST", "/projectmanage/api/task/updateStatus", data=data, token=token)

    # --- Project Budget Management ---

    def get_budget_list(self, project_id: int, page: int = 1, page_size: int = 50, token: Optional[str] = None) -> Dict:
        """
        Get budget list.
        Calls /projectmanage/api/budget/lists
        """
        params = {"project_id": project_id, "page": page, "page_size": page_size}
        return self._make_request("GET", "/projectmanage/api/budget/lists", params=params, token=token)

    def get_budget_overview(self, project_id: int, token: Optional[str] = None) -> Dict:
        """
        Get budget overview stats.
        Calls /projectmanage/api/budget/overview
        """
        return self._make_request("GET", "/projectmanage/api/budget/overview", params={"project_id": project_id}, token=token)

    # --- Project Timesheet Management ---

    def get_timesheet_list(self, project_id: int, page: int = 1, page_size: int = 50, token: Optional[str] = None) -> Dict:
        """
        Get timesheet list.
        Calls /projectmanage/api/timesheet/lists
        """
        params = {"project_id": project_id, "page": page, "page_size": page_size}
        return self._make_request("GET", "/projectmanage/api/timesheet/lists", params=params, token=token)

    def add_timesheet_quick(self, data: Dict, token: Optional[str] = None) -> Dict:
        """
        Quick add timesheet.
        Calls /projectmanage/api/timesheet/quickAdd
        """
        return self._make_request("POST", "/projectmanage/api/timesheet/quickAdd", data=data, token=token)

    # --- Project Statistics ---

    def get_project_statistics(self, project_id: int = 0, token: Optional[str] = None) -> Dict:
        """
        Get project statistics.
        Calls /projectmanage/api/project/statistics
        """
        params = {}
        if project_id:
            params['project_id'] = project_id
        return self._make_request("GET", "/projectmanage/api/project/statistics", params=params, token=token)

    # --- AI Config ---
    def get_ai_global_config(self) -> Dict:
        """
        Get global AI configuration (including guest limits).
        Calls /api/AI/globalConfig
        """
        return self._make_request("GET", "/api/AI/globalConfig")


    def _generate_signature(self, method: str, uri: str, body: str, timestamp: int) -> str:
        """Generate HMAC-SHA256 signature (Ported from chatgpt-on-wechat)"""
        if not self.api_secret:
            return ""
            
        string_to_sign = f"{method}\\n{uri}\\n{body}\\n{timestamp}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None, token: Optional[str] = None) -> Dict:
        """
        Generic request wrapper with Token injection.
        """
        # Prioritize explicit token, then stored token
        active_token = token or self._user_token

        if not active_token:
             # Fail fast if no token
             # But maybe we want generic public access? 
             # For GetProjects, token is required usually for context.
             pass # proceed, maybe params has it?

        url = f"{self.base_url}{endpoint}"
        timestamp = int(time.time())
        body_str = json.dumps(data) if data else ""
        
        # Headers
        headers = {
            'Content-Type': 'application/json',
            'X-Timestamp': str(timestamp)
        }
        
        # Inject API Key Signature if keys exist (optional app-level auth)
        if self.api_key and self.api_secret:
            headers['X-API-Key'] = self.api_key
            headers['X-Signature'] = self._generate_signature(method, endpoint, body_str, timestamp)
            
        # Inject User Token
        if params is None:
            params = {}
        
        if active_token:
            params['token'] = active_token
            
        try:
            logger.info(f"ImagicBox Request: {method} {url} Params={params} Data={data}")
            resp = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                headers=headers,
                timeout=self.timeout
            )
            
            # Log response summary
            logger.info(f"ImagicBox Response: {resp.status_code} {resp.text[:500]}...") # Truncate for sanity

            try:
                res_json = resp.json()
                # Log parsed JSON for easier debugging
                logger.debug(f"ImagicBox Response JSON: {res_json}")
            except:
                logger.error(f"ImagicBox Invalid JSON response: {resp.text}")
                return {"code": -1, "message": f"Invalid JSON response: {resp.text}"}
                
            return res_json
            
        except Exception as e:
            logger.error(f"Request failed: {url} -> {e}")
            return {"code": -1, "message": str(e)}

# Global instance
imagicbox_client = ImagicBoxClient()
