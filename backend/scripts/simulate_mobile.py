import asyncio
import json
import logging
import requests
import websockets
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SimulateMobile")

# Production Endpoints
LOGIN_URL = "https://evoloop.develop-assistant.cn/member/api/login/login"
WS_URL = "wss://evoloop.develop-assistant.cn/gateway/ws"

# Test Credentials
USERNAME = "preterchan"
PASSWORD = "hellomylife"

# The device key of the real online device provided by the user
TARGET_DEVICE_KEY = "a609165d-25f8-4e03-8d4b-08a505628188"

async def simulate_mobile_relay():
    """
    1. Login to retrieve JWT
    2. Connect to WebSocket Gateway as 'mobile'
    3. Send 'command_relay' message
    """
    
    # --- Step 1: Login ---
    logger.info(f"Logging in as {USERNAME}...")
    try:
        resp = requests.post(LOGIN_URL, json={
            "username": USERNAME,
            "password": PASSWORD
        }, timeout=10)
        
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
    logger.info(f"Connecting to Gateway as Mobile...")
    try:
        async with websockets.connect(WS_URL) as ws:
            # Identfy as Mobile
            handshake = {
                "type": "auth",
                "request_id": "mobile_auth_001",
                "payload": {
                    "token": token,
                    "device_type": "mobile",
                    "device_key": "mobile_test_device_001"
                }
            }
            await ws.send(json.dumps(handshake))
            
            # Wait for connect_ok
            response = await ws.recv()
            logger.info(f"Handshake response: {response}")

            # --- Step 3: Send Relay Command ---
            # Refined payload to match app/core/evocloud/bridge/handlers.py expectations
            relay_msg = {
                "type": "command_relay",
                "request_id": "relay_test_456",
                "payload": {
                    "target_device_key": TARGET_DEVICE_KEY,
                    "type": "chat_message",  # Explicitly set to trigger agent conversation
                    "message": "Hello from Antigravity! Can you tell me what you see nearby?", # Use 'message' field instead of 'content' string
                    "timestamp": int(asyncio.get_event_loop().time())
                }
            }
            
            logger.info(f"Sending real-time relay command to {TARGET_DEVICE_KEY}...")
            await ws.send(json.dumps(relay_msg))

            # Wait for relay_ok from Gateway
            response = await ws.recv()
            logger.info(f"Gateway relay result: {response}")
            
            # Keep open for a bit to see if any response comes back
            logger.info("Waiting 5 seconds for potential agent feedback...")
            await asyncio.sleep(5)

    except Exception as e:
        logger.error(f"WebSocket error: {e}")

if __name__ == "__main__":
    asyncio.run(simulate_mobile_relay())
