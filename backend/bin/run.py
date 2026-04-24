#!/usr/bin/env python3
"""
EvoLoop 统一运行入口 (ARM64)
"""

import argparse
import multiprocessing
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# 强制使用 spawn 方式启动子进程
if multiprocessing.get_start_method(allow_none=True) != "spawn":
    multiprocessing.set_start_method("spawn", force=True)


def run_api():
    """启动 API 服务器。"""
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8123"))
    workers = int(os.getenv("WORKERS", "1"))
    reload = os.getenv("RELOAD", "false").lower() == "true"

    print(f"Starting API Server on {host}:{port} (workers={workers})")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
    )


def run_worker():
    """启动任务队列 Worker（独立进程）。"""
    import subprocess
    
    # Run worker as separate process using scripts/run_worker.py
    # This avoids issues with signal handling and thread safety
    worker_script = PROJECT_DIR / "scripts" / "run_worker.py"
    
    # Pass through command line arguments
    cmd = [sys.executable, "-m", "scripts.run_worker"] + sys.argv[2:]
    
    print("Starting Task Queue Worker (separate process)...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Worker exited with code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nWorker interrupted")


def export_openapi():
    """导出 OpenAPI Schema 到前端。"""
    import json

    from app.main import app

    print("Exporting OpenAPI Schema...")
    openapi_data = app.openapi()

    # 默认输出到前端目录
    output_path = PROJECT_DIR.parent / "frontend" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(openapi_data, f, indent=2)

    print(f"Schema exported to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="EvoLoop Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bin/run.py api                       # Start API server
  python bin/run.py worker                    # Start Task Queue Worker
  python bin/run.py worker --workers=4        # Start Worker with 4 workers
  python bin/run.py export-openapi            # Export OpenAPI schema

Environment Variables:
  HOST                  API host (default: 0.0.0.0)
  PORT                  API port (default: 8123)
  WORKERS               Number of API workers (default: 1)
  RELOAD                Enable auto-reload (default: false)
  TASK_QUEUE_BACKEND    Task queue backend (huey/celery/local/auto)

Note:
  Worker now runs as separate process for better stability.
  Use 'python bin/run.py worker --workers=2' to start worker.
        """,
    )

    parser.add_argument(
        "command",
        choices=["api", "worker", "export-openapi"],
        help="Command to execute",
    )

    args = parser.parse_args()

    try:
        if args.command == "api":
            run_api()
        elif args.command == "worker":
            run_worker()
        elif args.command == "export-openapi":
            export_openapi()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
