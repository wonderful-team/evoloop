#!/bin/bash

# Start Xvfb in background
Xvfb :99 -screen 0 1920x1080x24 &
xvfb_pid=$!

echo "Started Xvfb (PID: $xvfb_pid)"

# Wait for Xvfb to be ready
sleep 1

# Start MCP Server
# Using explicit host 0.0.0.0 is crucial for Docker
# Start MCP Server
# Using explicit host 0.0.0.0 is crucial for Docker
# Assuming FastMCP exposes an ASGI app at 'mcp.sse_app' or similar? 
# Actually, if we use 'python server.py', we need to ensure server.py binds 0.0.0.0.
# The previous step updated server.py to use mcp.run(). 
# BUT mcp.run() might default to 127.0.0.1.
# Better approach: access the underlying ASGI app and serve it with uvicorn CLI to control host.
# FastMCP usually has an .app or .sse_app attribute if it's based on Starlette/FastAPI.
# If not, we rely on python server.py.
# Let's try python server.py first, and assuming we can pass args via env or code.

# Wait, I can just patch server.py to use uvicorn directly if I want full control.
# Modify server.py to not use mcp.run() but expose 'app = mcp.sse_app'??
# Let's trust 'python server.py' for now but pass environment variables that FastMCP *might* respect?
# Or update server.py again to be sure?

# Let's update server.py to force uvicorn.
exec python3 server.py
