#!/usr/bin/env python3
"""
EvoLoop Client 运行入口
======================

支持运行模式：
- start: 启动客户端守护进程
- stop: 停止守护进程

用法：
    python bin/run.py start
    python bin/run.py stop
"""

import argparse
import os
import sys
from pathlib import Path

# 确保项目根目录在路径中
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))


def run_client():
    """启动客户端守护进程。"""
    import asyncio
    from app.main import main

    print("Starting EvoLoop Client...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nClient stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="EvoLoop Client Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bin/run.py start    # Start client daemon
  python bin/run.py stop     # Stop client daemon (TODO)

Environment Variables:
  LOG_LEVEL     Log level (default: INFO)
  WORKSPACE_ROOT    Project workspace root
        """,
    )

    parser.add_argument(
        "command",
        choices=["start", "stop"],
        help="Command to execute",
    )

    args = parser.parse_args()

    try:
        if args.command == "start":
            run_client()
        elif args.command == "stop":
            print("Stop command not implemented yet.")
            # TODO: Implement stop via PID file or signal
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
