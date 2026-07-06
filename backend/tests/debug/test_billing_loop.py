import asyncio
import logging
import os
import sys
import time

backend_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(os.path.dirname(backend_dir))  # evoloop/backend/
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# Override environment to prevent trying to start web server stuff
os.environ["ENVIRONMENT"] = "local"
os.environ["EMBEDDED_MODE"] = "True"

from app.core.evocloud import evocloud_manager
from app.core.identity import identity_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("test_billing")

async def run_test():
    logger.info("Initializing EvoCloud Manager...")
    try:
        evocloud_manager.initialize()
    except Exception as e:
        logger.warning(f"Initialization had some issues: {e}")

    client = evocloud_manager.api

    # Step 0: Login to MC and verify token with Gateway
    logger.info("Attempting to login with local test credentials...")
    login_res = await client.login("peter1", "hellomylife")
    if not login_res.get("success"):
        logger.error(f"Failed to login: {login_res}")
        return

    token = login_res["token"]
    await client.set_token(token)
    logger.info(f"Login success, token: {token[:30]}...")

    # Verify token with Gateway (Gateway returns user_id which equals member_id)
    logger.info("Verifying token with local Gateway...")
    auth_res = await client.request("POST", "/api/v1/auth/verify", data={"token": token})
    if "user_id" not in auth_res:
        logger.error(f"Gateway token verification failed: {auth_res}")
        return

    member_id = auth_res["user_id"]
    logger.info(f"Gateway verified. Member ID: {member_id}")

    # Save member_id to identity store
    await identity_service.store.save_member_id(member_id)

    logger.info("Skipping auto-recharge (testing with current quota)")

    # Step 1: Query Gateway for Current Quota
    # This automatically maps to /gateway/api/v1/quota/{member_id}
    quota_endpoint = f"/api/v1/quota/{member_id}"
    logger.info(f"\n[Step 1] Fetching current quota via EvoCloud Client: {quota_endpoint}")

    try:
        r = await client.request("GET", quota_endpoint)
        if "quota" not in r:
            logger.error(f"Failed to fetch quota, raw response: {r}")
            return

        logger.info(f"Before Test - Quota Info: {r}")
        before_quota = r.get('quota', 0)
        before_used = r.get('quota_used', 0)
        before_remains = before_quota
        logger.info(f"Before Test - Quota(remaining): {before_quota}, Used: {before_used}")
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return

    # Step 2: Call LLM through AdaptiveChatOpenAI which will route to EVoCloud Gateway
    logger.info("\n[Step 2] Using LLMFactory platform mode to call LLM...")
    try:
        # We need LLMFactory platform mode!
        # By default this will try to verify config. We must enforce platform mode.
        import app.infrastructure.config.service as config_svc
        from app.infrastructure.llm.factory import LLMFactory
        # Monkey patch config for test
        original_get = config_svc.SystemConfigService.get_value
        def fake_get(key, default=None):
            if key == "LLM_CONFIG_TYPE": return "platform"
            if key == "LLM_MODEL": return "deepseek-chat" # Fallback if unavailable
            return original_get(key, default)
        config_svc.SystemConfigService.get_value = fake_get

        llm = await LLMFactory.create_llm(model_name="kimi-k2-thinking-turbo", temperature=0.1) # Or whatever model is supported

        logger.info("Sending non-streaming request to generate some tokens...")
        start_t = time.time()
        res = await llm.ainvoke("Please reply with: 'INTEGRATION_TEST_SUCCESS'")
        logger.info(f"LLM Reply in {time.time()-start_t:.2f}s: {res.content}")
        logger.info(f"Token Usage Tracking: {res.response_metadata.get('token_usage')}")
    except Exception as e:
        logger.error(f"LLM Call failed: {e}")
        return

    # Step 3: Wait for asynchronous background batching (Gateway has a 30s usage flush + sync delay)
    # However, quotaManager deducts in memory INSTANTLY! We can query Gateway again immediately.
    logger.info("\n[Step 3] Fetching quota again to verify Gateway Memory Deduction...")

    try:
        r3 = await client.request("GET", quota_endpoint)

        after_quota = r3.get('quota', 0)
        after_used = r3.get('quota_used', 0)
        after_remains = after_quota

        logger.info(f"After Test - Quota Info: {r3}")
        logger.info(f"After Test - Quota(remaining): {after_quota}, Used: {after_used}")

        diff = before_remains - after_remains
        if diff > 0:
            logger.info(f"✅ SUCCESS: Quota correctly deducted by {diff} in Gateway Memory!")
        elif diff == 0:
            logger.warning("⚠️ WARNING: Quota did not change. Perhaps the model is free or quota sync is disabled?")
        else:
            logger.warning(f"⚠️ WARNING: Quota increased by {-diff}?")
    except Exception as e:
        logger.error(f"Failed to fetch post-test quota: {e}")

    logger.info("\n[Step 4] (Manual Verification Required)")
    logger.info("The usage details will be batch uploaded to the PHP Backend in up to 30 seconds.")
    logger.info("Please login to your PHP Backend Database and check the following:")
    logger.info("1. Table `evoloop_llm_usage` for a new record with the tokens used.")
    logger.info("2. Table `member_quota` for the permanent quota deduction.")

if __name__ == "__main__":
    asyncio.run(run_test())
