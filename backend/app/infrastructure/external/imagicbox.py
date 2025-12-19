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

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict:
        """
        Generic request wrapper with Token injection.
        """
        if not self._user_token:
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
        
        if self._user_token:
            params['token'] = self._user_token
            
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
