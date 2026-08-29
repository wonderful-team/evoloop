"""EvoCloud subscription mixin: subscription, AI quota, LLM models."""


class SubscriptionMixin:
    """Subscription and AI quota API methods."""

    async def get_subscription_status(self, token: str | None = None) -> dict:
        return await self.request(
            "GET", "/subscription/api/subscription/status", token=token
        )

    async def get_member_benefits(self, token: str | None = None) -> dict:
        return await self.request(
            "GET", "/subscription/api/subscription/benefits", token=token
        )

    async def check_benefit(self, code: str, token: str | None = None) -> dict:
        return await self.request(
            "POST",
            "/subscription/api/subscription/checkBenefit",
            data={"code": code},
            token=token,
        )

    async def get_subscription_plans(self, token: str | None = None) -> dict:
        return await self.request(
            "GET", "/subscription/api/subscription/plans", token=token
        )

    async def calculate_upgrade_price(
        self, target_level_id: int, token: str | None = None
    ) -> dict:
        return await self.request(
            "POST",
            "/subscription/api/plan/calculateUpgradePrice",
            data={"target_level_id": target_level_id},
            token=token,
        )

    async def create_subscription_order(
        self,
        level_id: int,
        auto_renew: bool = False,
        pay_type: str = "wechatpay",
        token: str | None = None,
    ) -> dict:
        return await self.request(
            "POST",
            "/subscription/api/subscription/createOrder",
            data={
                "level_id": level_id,
                "auto_renew": 1 if auto_renew else 0,
                "app_type": "pc",
                "pay_type": pay_type,
            },
            token=token,
        )

    async def check_subscription_order_status(
        self, order_id: str, token: str | None = None
    ) -> dict:
        return await self.request(
            "GET",
            "/subscription/api/order/checkStatus",
            params={"order_id": order_id},
            token=token,
        )

    async def get_subscription_detail(self, token: str | None = None) -> dict:
        return await self.request(
            "GET", "/subscription/api/subscription/getDetail", token=token
        )

    async def cancel_subscription(
        self, cancel_type: str = "expire", reason: str = "", token: str | None = None
    ) -> dict:
        return await self.request(
            "POST",
            "/subscription/api/subscription/cancel",
            data={"cancel_type": cancel_type, "reason": reason},
            token=token,
        )

    async def get_ai_quota(self, token: str | None = None) -> dict:
        return await self.request(
            "GET", "/subscription/api/aiQuota/getQuota", token=token
        )

    async def get_all_ai_quotas(self, token: str | None = None) -> dict:
        return await self.get_ai_quota()

    async def get_ai_quota_history(
        self, page: int = 1, page_size: int = 20, token: str | None = None
    ) -> dict:
        params = {"page": page, "page_size": page_size}
        return await self.request(
            "GET",
            "/subscription/api/aiQuota/getUsageHistory",
            params=params,
            token=token,
        )

    async def get_llm_models(self, token: str | None = None) -> dict:
        return await self.request("GET", "/evolooplink/api/llm/getModels", token=token)
