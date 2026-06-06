#!/usr/bin/env python3
"""
EvoLoop Backend Sidecar Entry Point
===================================

用于 Tauri Sidecar 模式打包的入口点。
直接启动 API 服务器，无需子命令。

用法：
    EVOLOOP_BACKEND_PORT=20160 ./evoloop-backend-x86_64-apple-darwin --host 127.0.0.1

    或显式指定端口：
    ./evoloop-backend-x86_64-apple-darwin --host 127.0.0.1 --port 20160
"""

import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="EvoLoop Backend Sidecar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("EVOLOOP_BACKEND_PORT", "20160")),
        help="Port to bind the server to (default: 20160, 通过 EVOLOOP_BACKEND_PORT 环境变量覆盖)",
    )
    
    args = parser.parse_args()
    
    # Embedded mode: set default EMBEDDED_MODE=true for sidecar packaging
    if "PYTHON_ENV" in os.environ and os.environ["PYTHON_ENV"] == "embedded":
        os.environ.setdefault("EMBEDDED_MODE", "true")
    
    # Pre-import app.main to catch ImportError early (before uvicorn starts)
    try:
        import app.main  # noqa: F401
    except Exception as e:
        import traceback
        print(f"[Sidecar] Failed to import app.main: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    
    # Import uvicorn here to avoid early import issues with PyInstaller
    import uvicorn
    
    print(f"[Sidecar] Starting EvoLoop Backend on {args.host}:{args.port}")
    
    try:
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=False,
            workers=1,
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\n[Sidecar] Shutting down...")
        sys.exit(0)
    except SystemExit as e:
        # Uvicorn may raise SystemExit on startup failure
        print(f"[Sidecar] Server exited with code {e.code}", file=sys.stderr)
        sys.exit(e.code)
    except Exception as e:
        import traceback
        print(f"[Sidecar] Error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
