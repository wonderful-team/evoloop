"""EvoCloud auth mixin: login, tokens, user info, password, captcha, register."""

import logging
from typing import Any

from app.core.config import settings
from app.core.identity import identity_service
from app.models.schemas.auth import EvoCloudProxyResponse, LoginResult

logger = logging.getLogger(__name__)


class AuthMixin:
    """Authentication and user management API methods."""

    async def login(self, username, password) -> LoginResult:
        res = await self.request(
            "POST",
            "/api/login/login",
            data={"username": username, "password": password},
        )
        if res.get("code", -1) >= 0:
            data = res.get("data", {})
            token = data.get("token")
            refresh_token = data.get("refresh_token")
            if token:
                await self.set_token(token, refresh_token)
                member_id = await self._fetch_member_id(token)
                if not settings.MULTI_TENANT_MODE:
                    await identity_service.store.save_member_id(member_id)
                return LoginResult(
                    success=True,
                    token=token,
                    member_id=member_id,
                    data=data,
                )
        return LoginResult(success=False, message=res.get("message", "Login failed"))

    async def login_mobile(
        self, mobile: str, key: str, code: str, token: str | None = None
    ) -> LoginResult:
        res = await self.request(
            "POST",
            "/passport/api/login/mobile",
            data={"mobile": mobile, "key": key, "code": code},
            token=token,
        )
        if res.get("code", -1) >= 0:
            data = res.get("data", {})
            token = data.get("token")
            refresh_token = data.get("refresh_token")
            if token:
                await self.set_token(token, refresh_token)
                member_id = await self._fetch_member_id(token)
                if not settings.MULTI_TENANT_MODE:
                    await identity_service.store.save_member_id(member_id)
                return LoginResult(
                    success=True,
                    token=token,
                    member_id=member_id,
                    data=data,
                )
        return LoginResult(success=False, message=res.get("message", "Login failed"))

    async def _fetch_member_id(self, token: str) -> int:
        try:
            user_info = await self.get_user_info(token=token)
            if user_info.get("code") == 0:
                return user_info.get("data", {}).get("member_id", 0)
        except Exception as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)
        return 0

    async def check_mobile_exist(
        self, mobile: str, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "GET",
                "/passport/api/mobile/check",
                params={"mobile": mobile},
                token=token,
            )
        )

    async def reset_password_by_mobile(
        self, mobile: str, code: str, key: str, password: str, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "POST",
                "/passport/api/password/reset/mobile",
                data={"mobile": mobile, "code": code, "key": key, "password": password},
                token=token,
            )
        )

    async def change_password(
        self, old_password: str, new_password: str, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "POST",
                "/passport/api/password/change",
                data={"old_password": old_password, "new_password": new_password},
                token=token,
            )
        )

    async def update_user_info(
        self, data: dict[str, Any], token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request("POST", "/api/member/update", data=data, token=token)
        )

    async def get_user_info(self, token: str | None = None) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request("GET", "/api/member/info", token=token)
        )

    async def get_captcha_config(
        self, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request("GET", "/api/captcha/config", token=token)
        )

    async def get_captcha(
        self, captcha_id: str, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "GET",
                "/api/captcha/get",
                params={"id": captcha_id},
                token=token,
            )
        )

    async def get_register_config(
        self, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request("GET", "/api/register/config", token=token)
        )

    async def get_register_agreement(
        self, type: str = "SERVICE", token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "GET",
                "/api/register/aggrement",
                params={"type": type},
                token=token,
            )
        )

    async def send_mobile_code(
        self,
        mobile: str,
        captcha_id: str,
        captcha_code: str,
        type: str = "login",
        token: str | None = None,
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request(
                "POST",
                "/api/sms/send",
                data={
                    "mobile": mobile,
                    "captcha_id": captcha_id,
                    "captcha_code": captcha_code,
                    "type": type,
                },
                token=token,
            )
        )

    async def register_mobile(
        self, data: dict, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request("POST", "/api/register/mobile", data=data, token=token)
        )

    async def register_username(
        self, data: dict, token: str | None = None
    ) -> EvoCloudProxyResponse:
        return EvoCloudProxyResponse.model_validate(
            await self.request("POST", "/api/register/username", data=data, token=token)
        )
