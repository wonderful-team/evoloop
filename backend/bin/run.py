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
    port = int(os.getenv("PORT", "8000"))
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
    """启动 Celery Worker。"""
    from app.infrastructure.queue.celery import celery_app

    print("Starting Celery Worker...")
    argv = [
        "worker",
        "--loglevel=info",
        "--pool=solo",
        "--queues=celery",
    ]
    celery_app.worker_main(argv=argv)


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
  python bin/run.py api              # Start API server
  python bin/run.py worker           # Start Celery worker
  python bin/run.py export-openapi   # Export OpenAPI schema

Environment Variables:
  HOST        API host (default: 0.0.0.0)
  PORT        API port (default: 8000)
  WORKERS     Number of workers (default: 1)
  RELOAD      Enable auto-reload (default: false)
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
