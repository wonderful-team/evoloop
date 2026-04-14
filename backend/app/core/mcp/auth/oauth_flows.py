"""OAuth 2.0 flow implementations for MCP servers."""

import asyncio
import base64
import hashlib
import logging
import secrets
import time
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import aiohttp

from app.core.identity.store import IdentityStore
from app.core.mcp.auth.base import AuthConfig, AuthHandler, AuthMethod, AuthToken

logger = logging.getLogger(__name__)


class OAuthAuthorizationCodeHandler(AuthHandler):
    """
    OAuth 2.0 Authorization Code flow handler.
    
    Flow:
    1. Generate PKCE parameters
    2. Open browser for user authorization
    3. Start local server to receive callback
    4. Exchange code for token
    """

    method = AuthMethod.OAUTH_AUTH_CODE

    def __init__(self, server_name: str, config: AuthConfig):
        super().__init__(server_name, config)
        self._pending_codes: dict[str, asyncio.Future] = {}
        self._code_verifier: str | None = None
        self._state: str | None = None

    def _generate_pkce(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge."""
        code_verifier = base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode("utf-8").rstrip("=")

        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode("utf-8").rstrip("=")

        return code_verifier, code_challenge

    def _get_storage_key(self) -> str:
        """Get key for secure storage."""
        return f"mcp_{self.server_name}_oauth_token"

    def _get_refresh_key(self) -> str:
        """Get key for refresh token storage."""
        return f"mcp_{self.server_name}_oauth_refresh"

    async def load_stored_token(self) -> AuthToken | None:
        """Load token from secure storage if available."""
        # Try to get from IdentityStore
        token_data = IdentityStore._file_storage_get(self._get_storage_key())
        if not token_data:
            return None

        try:
            import json
            data = json.loads(token_data)
            token = AuthToken.model_validate(data)

            # Check if expired and refresh if needed
            if token.is_expired() and token.refresh_token:
                logger.info(f"Token for {self.server_name} expired, refreshing...")
                return await self.refresh(token)

            return token
        except Exception as e:
            logger.error(f"Failed to load stored token: {e}")
            return None

    def _store_token(self, token: AuthToken) -> None:
        """Store token in secure storage."""
        try:
            import json
            token_data = json.dumps({
                "access_token": token.access_token,
                "token_type": token.token_type,
                "expires_at": token.expires_at,
                "refresh_token": token.refresh_token,
                "scope": token.scope,
            })
            IdentityStore._file_storage_set(self._get_storage_key(), token_data)

            # Also store refresh token separately for safety
            if token.refresh_token:
                IdentityStore._file_storage_set(
                    self._get_refresh_key(),
                    token.refresh_token
                )
        except Exception as e:
            logger.error(f"Failed to store token: {e}")

    async def authenticate(self) -> AuthToken:
        """
        Perform OAuth Authorization Code flow.
        
        Returns:
            AuthToken with access token
        """
        # Check for stored token first
        stored = await self.load_stored_token()
        if stored and not stored.is_expired():
            logger.info(f"Using stored token for {self.server_name}")
            return stored

        # Generate PKCE
        self._code_verifier, code_challenge = self._generate_pkce()
        self._state = secrets.token_urlsafe(32)

        # Build authorization URL
        auth_url = self._build_auth_url(code_challenge)

        # Open browser
        logger.info(f"Opening browser for OAuth authorization: {auth_url}")
        webbrowser.open(auth_url)

        # Wait for callback
        code = await self._wait_for_callback()

        # Exchange code for token
        token = await self._exchange_code(code)

        # Store token
        self._store_token(token)

        return token

    def _build_auth_url(self, code_challenge: str) -> str:
        """Build authorization URL with PKCE."""
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "redirect_uri": self.config.redirect_uri,
            "state": self._state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        if self.config.scopes:
            params["scope"] = " ".join(self.config.scopes)

        return f"{self.config.authorization_endpoint}?{urlencode(params)}"

    async def _wait_for_callback(self) -> str:
        """
        Wait for OAuth callback.
        
        Returns:
            Authorization code from callback
        """
        # Create future to wait for callback
        future = asyncio.get_event_loop().create_future()
        self._pending_codes[self._state] = future

        try:
            # Wait with timeout
            result = await asyncio.wait_for(future, timeout=300)  # 5 minutes
            return result["code"]
        except asyncio.TimeoutError:
            raise RuntimeError("OAuth authorization timed out")
        finally:
            self._pending_codes.pop(self._state, None)

    async def handle_callback(self, url: str) -> None:
        """
        Handle OAuth callback URL.
        
        Args:
            url: Callback URL with code and state
        """
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        if error:
            raise RuntimeError(f"OAuth error: {error}")

        if not code or not state:
            raise ValueError("Missing code or state in callback")

        if state not in self._pending_codes:
            raise ValueError("Invalid state parameter")

        # Resolve the future
        future = self._pending_codes[state]
        future.set_result({"code": code, "state": state})

    async def _exchange_code(self, code: str) -> AuthToken:
        """Exchange authorization code for access token."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "code_verifier": self._code_verifier,
        }

        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.token_endpoint,
                data=data,
                headers={"Accept": "application/json"}
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Token exchange failed: {resp.status} - {text}")

                result = await resp.json()

                return AuthToken(
                    access_token=result["access_token"],
                    token_type=result.get("token_type", "Bearer"),
                    expires_at=time.time() + result.get("expires_in", 3600) if "expires_in" in result else None,
                    refresh_token=result.get("refresh_token"),
                    scope=result.get("scope"),
                )

    async def refresh(self, token: AuthToken) -> AuthToken:
        """Refresh an access token."""
        if not token.refresh_token:
            raise ValueError("No refresh token available")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": self.config.client_id,
        }

        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.token_endpoint,
                data=data,
                headers={"Accept": "application/json"}
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Token refresh failed: {resp.status} - {text}")

                result = await resp.json()

                new_token = AuthToken(
                    access_token=result["access_token"],
                    token_type=result.get("token_type", "Bearer"),
                    expires_at=time.time() + result.get("expires_in", 3600) if "expires_in" in result else None,
                    refresh_token=result.get("refresh_token", token.refresh_token),
                    scope=result.get("scope", token.scope),
                )

                # Store new token
                self._store_token(new_token)

                return new_token


class OAuthDeviceCodeHandler(AuthHandler):
    """
    OAuth 2.0 Device Authorization Grant flow.
    
    Flow:
    1. Request device code from authorization server
    2. Display user code and verification URI to user
    3. Poll token endpoint until user completes authorization
    """

    method = AuthMethod.OAUTH_DEVICE_CODE

    def __init__(self, server_name: str, config: AuthConfig):
        super().__init__(server_name, config)

    def _get_storage_key(self) -> str:
        return f"mcp_{self.server_name}_device_token"

    async def authenticate(self) -> AuthToken:
        """
        Perform OAuth Device Code flow.
        
        Returns:
            AuthToken with access token
        """
        # Step 1: Request device code
        device_data = await self._request_device_code()

        user_code = device_data["user_code"]
        verification_uri = device_data["verification_uri"]
        device_code = device_data["device_code"]
        interval = device_data.get("interval", 5)
        expires_in = device_data.get("expires_in", 600)

        # Step 2: Display to user
        logger.info(f"""
╔════════════════════════════════════════════════════════════╗
║  OAuth Device Authorization Required                       ║
╠════════════════════════════════════════════════════════════╣
║  User Code: {user_code:<46} ║
║                                                            ║
║  Please visit: {verification_uri:<43} ║
║  and enter the code above.                                 ║
╚════════════════════════════════════════════════════════════╝
        """)

        # Step 3: Poll for token
        return await self._poll_for_token(device_code, interval, expires_in)

    async def _request_device_code(self) -> dict:
        """Request device code from authorization server."""
        data = {
            "client_id": self.config.client_id,
        }

        if self.config.scopes:
            data["scope"] = " ".join(self.config.scopes)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.device_authorization_endpoint,
                data=data,
                headers={"Accept": "application/json"}
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Device code request failed: {resp.status} - {text}")

                return await resp.json()

    async def _poll_for_token(
        self,
        device_code: str,
        interval: int,
        expires_in: int
    ) -> AuthToken:
        """Poll token endpoint until authorization complete."""
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": self.config.client_id,
        }

        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret

        start_time = time.time()

        async with aiohttp.ClientSession() as session:
            while time.time() - start_time < expires_in:
                await asyncio.sleep(interval)

                async with session.post(
                    self.config.token_endpoint,
                    data=data,
                    headers={"Accept": "application/json"}
                ) as resp:
                    result = await resp.json()

                    if "error" not in result:
                        # Success!
                        token = AuthToken(
                            access_token=result["access_token"],
                            token_type=result.get("token_type", "Bearer"),
                            expires_at=time.time() + result.get("expires_in", 3600) if "expires_in" in result else None,
                            refresh_token=result.get("refresh_token"),
                            scope=result.get("scope"),
                        )

                        # Store token
                        import json
                        IdentityStore._file_storage_set(
                            self._get_storage_key(),
                            json.dumps({
                                "access_token": token.access_token,
                                "token_type": token.token_type,
                                "expires_at": token.expires_at,
                                "refresh_token": token.refresh_token,
                                "scope": token.scope,
                            })
                        )

                        return token

                    error = result.get("error")

                    if error == "authorization_pending":
                        # Still waiting for user
                        continue
                    elif error == "slow_down":
                        # Increase interval
                        interval += 5
                    elif error == "expired_token":
                        raise RuntimeError("Device code expired")
                    elif error == "access_denied":
                        raise RuntimeError("User denied authorization")
                    else:
                        raise RuntimeError(f"OAuth error: {error}")

        raise RuntimeError("Device authorization timed out")

    async def refresh(self, token: AuthToken) -> AuthToken:
        """Refresh an access token using refresh token."""
        # Same as authorization code flow
        if not token.refresh_token:
            raise ValueError("No refresh token available")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": self.config.client_id,
        }

        if self.config.client_secret:
            data["client_secret"] = self.config.client_secret

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.config.token_endpoint,
                data=data,
                headers={"Accept": "application/json"}
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Token refresh failed: {resp.status} - {text}")

                result = await resp.json()

                new_token = AuthToken(
                    access_token=result["access_token"],
                    token_type=result.get("token_type", "Bearer"),
                    expires_at=time.time() + result.get("expires_in", 3600) if "expires_in" in result else None,
                    refresh_token=result.get("refresh_token", token.refresh_token),
                    scope=result.get("scope", token.scope),
                )

                # Store new token
                import json
                IdentityStore._file_storage_set(
                    self._get_storage_key(),
                    json.dumps({
                        "access_token": new_token.access_token,
                        "token_type": new_token.token_type,
                        "expires_at": new_token.expires_at,
                        "refresh_token": new_token.refresh_token,
                        "scope": new_token.scope,
                    })
                )

                return new_token
