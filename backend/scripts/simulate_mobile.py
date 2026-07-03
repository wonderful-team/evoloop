import asyncio
import json
import logging
import time
import uuid

import requests
import websockets

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("SimulateMobile")

# Production Endpoints
LOGIN_URL = "https://evoloop.develop-assistant.cn/member/api/login/login"
WS_URL = "wss://evoloop.develop-assistant.cn/gateway/ws"
COMMAND_URL = "https://evoloop.develop-assistant.cn/gateway/api/v1/command/send"

# Test Credentials
USERNAME = "preterchan"
PASSWORD = "hellomylife"

# The device key of the real online device provided by the user
TARGET_DEVICE_KEY = "a609165d-25f8-4e03-8d4b-08a505628188"


async def simulate_mobile_relay():
    """
    1. Login to retrieve JWT
    2. Connect to WebSocket Gateway as 'mobile'
    3. Send 'command.relay' message via HTTP API
    """

    # --- Step 1: Login ---
    logger.info(f"Logging in as {USERNAME}...")
    try:
        resp = requests.post(
            LOGIN_URL, json={"username": USERNAME, "password": PASSWORD}, timeout=10
        )

        if resp.status_code != 200:
            logger.error(f"Login failed: {resp.status_code}")
            return

        data = resp.json()
        token = data["data"]["token"]
        logger.info("Login successful.")

    except Exception as e:
        logger.error(f"Login error: {e}")
        return

    # --- Step 2: WebSocket Connection ---
    ws_url = f"{WS_URL}?token={token}"
    logger.info("Connecting to Gateway as Mobile...")
    try:
        async with websockets.connect(ws_url) as ws:
            # Identify as Mobile
            handshake = {
                "version": "2.0",
                "type": "connect",
                "message_id": f"sim-mobile-{uuid.uuid4().hex[:12]}",
                "timestamp": int(time.time()),
                "body": {
                    "device_type": "mobile",
                    "device_key": "mobile_test_device_001",
                },
            }
            await ws.send(json.dumps(handshake))

            # Wait for system.init
            response = await ws.recv()
            logger.info(f"Handshake response: {response}")

            # --- Step 3: Send Relay Command via HTTP API ---
            command_payload = {
                "device_key": TARGET_DEVICE_KEY,
                "command_type": "chat",
                "content": "Hello from Antigravity! Can you tell me what you see nearby?",
            }
            headers = {"Authorization": f"Bearer {token}"}
            logger.info(f"Sending real-time relay command to {TARGET_DEVICE_KEY}...")
            resp = requests.post(
                COMMAND_URL, json=command_payload, headers=headers, timeout=10
            )
            logger.info(f"Gateway relay result: {resp.status_code} {resp.text}")

            # Keep open for a bit to see if any response comes back
            logger.info("Waiting 5 seconds for potential agent feedback...")
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    logger.info(f"WS message: {msg}")
            except asyncio.TimeoutError:
                logger.info("No more messages within 5 seconds, closing.")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")


if __name__ == "__main__":
    asyncio.run(simulate_mobile_relay())
