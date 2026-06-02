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
logger = logging.getLogger("SimulateAgent")

# Production Endpoints
LOGIN_URL = "https://evoloop.develop-assistant.cn/member/api/login/login"
# According to EvoLoopMobile/src/constants/api.ts line 10
# Updated to include /ws suffix to avoid Nginx redirects and match backend route
WS_URL = "wss://evoloop.develop-assistant.cn/gateway/ws" 

# Test Credentials
USERNAME = "preterchan"
PASSWORD = "hellomylife"

async def simulate_agent():
    """
    1. Login to retrieve JWT
    2. Connect to WebSocket Gateway
    3. Perform Handshake
    4. Maintain Connection
    """
    
    # --- Step 1: Login ---
    logger.info(f"Attempting to login at {LOGIN_URL}...")
    try:
        resp = requests.post(LOGIN_URL, json={
            "username": USERNAME,
            "password": PASSWORD
        }, timeout=10)
        
        if resp.status_code != 200:
            logger.error(f"Login HTTP failed: {resp.status_code} {resp.text}")
            return
            
        data = resp.json()
        if data.get("code") != 0:
            logger.error(f"Login API failed: {data.get('message')}")
            return
            
        token = data["data"]["token"]
        member_id = data["data"].get("member_id", "unknown")
        logger.info(f"Login successful. Member ID: {member_id}")
        logger.debug(f"Token: {token[:20]}...")

    except Exception as e:
        logger.error(f"Error during login: {e}")
        return

    # --- Step 2: WebSocket Connection ---
    logger.info(f"Connecting to Gateway at {WS_URL}...")
    try:
        # Use custom headers if needed, but Gateway uses payload for auth
        async with websockets.connect(WS_URL) as ws:
            logger.info("Successfully connected to WebSocket server.")

            # --- Step 3: Handshake ---
            handshake_payload = {
                "type": "auth",
                "request_id": "req_handshake_001",
                "payload": {
                    "token": token,
                    "device_type": "agent",
                    "device_key": "antigravity_test_unique_key_001",
                    "device_name": "Antigravity Simulation Agent",
                    "os_info": "Python/websockets (Simulator)"
                }
            }
            
            logger.info("Sending handshake payload...")
            await ws.send(json.dumps(handshake_payload))

            # --- Step 4: Event Loop ---
            async for message in ws:
                try:
                    msg = json.loads(message)
                    msg_type = msg.get("type")
                    data = msg.get("data")
                    
                    if msg_type == "connect_ok":
                        logger.info("=== [SUCCESS] Handshake Accepted by Gateway ===")
                        logger.info(f"Details: {data}")
                    
                    elif msg_type == "init":
                        device_key = data.get("device_key") if data else "N/A"
                        client_id = data.get("client_id") if data else "N/A"
                        logger.info(f"=== [SUCCESS] Device Initialized. MC Device ID: {device_key}, Gateway Client ID: {client_id} ===")
                        logger.info("Verification Point: Check the 'My Devices' list in the App or Web Admin.")
                    
                    elif msg_type == "error":
                        error_info = msg.get("error", {})
                        logger.error(f"!!! [ERROR] Gateway Error: {error_info.get('code')} - {error_info.get('message')}")
                    
                    elif msg_type == "pong":
                        logger.debug("Received pong from gateway.")
                    
                    else:
                        logger.info(f"Received msg type '{msg_type}': {data}")

                except json.JSONDecodeError:
                    logger.warning(f"Received non-JSON message: {message}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(f"WS Connection failed (Status {e.status_code}): {e}")
        if e.status_code == 404:
            logger.info("Tip: Gateway might be at a different path? Try /ws suffix.")
    except Exception as e:
        logger.error(f"WebSocket execution error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(simulate_agent())
    except KeyboardInterrupt:
        logger.info("Simulation stopped by user.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
