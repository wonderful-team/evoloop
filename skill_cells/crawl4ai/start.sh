#!/bin/bash

# Crawl4AI usually handles its own browser cycle, but Playwright might need Xvfb if not purely headless configured?
# The Dockerfile sets CRAWL4AI_HEADLESS=true.
# But let's start Xvfb just to be safe if 'headless=False' is ever requested or useful.
Xvfb :99 -screen 0 1920x1080x24 &
sleep 1

# Start Server
exec python3 server.py
