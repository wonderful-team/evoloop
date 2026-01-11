#!/bin/bash

# Start Xvfb (Browser Use needs a display even if headless=False logic is used, or maybe not if pure headless)
# Playwright headless=True works without Xvfb usually.
# But just in case we want non-headless mode later.
Xvfb :99 -screen 0 1920x1080x24 &
sleep 1

# Start Server
exec python3 server.py
