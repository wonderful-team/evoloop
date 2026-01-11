#!/bin/bash

# Ensure adb server is running or ready?
# Actually, if we use host adb, we don't start one.
# If we run adb client, it might try to start a server.

# Start Server
exec python3 server.py
