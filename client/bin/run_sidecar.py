#!/usr/bin/env python3
"""
EvoLoop Sidecar Entry (Compatibility Layer)
============================================

This is the PyInstaller entry point for the desktop application.
It delegates to bin/run.py for unified handling.

Usage:
    run_sidecar api       # Start API server
    run_sidecar worker    # Start Celery worker
"""

import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Delegate to unified runner
from run import main

if __name__ == "__main__":
    main()
