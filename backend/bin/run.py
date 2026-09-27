#!/usr/bin/env python3
"""
EvoLoop 统一运行入口 (ARM64)
"""

import argparse
import multiprocessing
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# 强制使用 spawn 方式启动子进程
if multiprocessing.get_start_method(allow_none=True) != "spawn":
    multiprocessing.set_start_method("spawn", force=True)

# 历史归档日志保留天数（默认 7 天），可用环境变量 LOG_RETENTION_DAYS 覆盖
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "7"))


def _cleanup_old_archives(logs_dir: Path, role: str, retention_days: int) -> int:
    """清除超过保留期的历史归档日志 {role}.log.bak_*。

    按归档文件的 mtime 判断，超过 retention_days 天的归档会被删除。
    返回删除的文件数。retention_days <= 0 表示不清理。
    """
    if retention_days <= 0:
        return 0
    cutoff = time.time() - retention_days * 86400
    removed = 0
    for f in logs_dir.glob(f"{role}.log.bak_*"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        sys.stdout.write(
            f"[run.py] 清理超过 {retention_days} 天的日志归档 {removed} 个 ({role}.log.bak_*)\n"
        )
        sys.stdout.flush()
    return removed


def _setup_log_redirect(role: str) -> Path:
    """将 stdout/stderr 重定向到 logs/{role}.log，并归档旧日志。

    不接收任何日志路径参数，路径固定为 backend/logs/{role}.log。
    每次启动时先把已存在的 {role}.log 归档为 {role}.log.bak_<时间戳>，
    并清除超过 LOG_RETENTION_DAYS 天的历史归档（默认 7 天）。
    子进程（worker）会继承重定向后的 fd，日志同样落入该文件。
    """
    logs_dir = PROJECT_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file = logs_dir / f"{role}.log"

    if log_file.exists() and log_file.stat().st_size > 0:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = logs_dir / f"{role}.log.bak_{ts}"
        os.replace(str(log_file), str(archive))
        sys.stdout.write(f"[run.py] 归档旧日志: {log_file.name} -> {archive.name}\n")
        sys.stdout.flush()

    _cleanup_old_archives(logs_dir, role, LOG_RETENTION_DAYS)

    fd = os.open(str(log_file), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    os.dup2(fd, sys.stdout.fileno())
    os.dup2(fd, sys.stderr.fileno())
    if fd > 2:
        os.close(fd)
    return log_file


def _reject_log_args(argv: list[str]) -> None:
    """run.py 不接受任何日志相关参数，日志路径固定。"""
    for a in argv:
        low = a.lower()
        if low in ("--log", "--log-file", "--logfile", "-l") or low.startswith("--log"):
            sys.stderr.write(
                f"[run.py] 错误：不接受日志参数 `{a}`；日志固定写入 backend/logs/ 目录。\n"
            )
            sys.exit(2)


def run_api():
    """启动 API 服务器。"""
    import uvicorn

    from app.core.config import settings

    # 硬闸 1（文件锁单例）：api 进程持有排他锁直到退出——比端口探针可靠
    # （端口探针存在 macOS 双绑/竞态绕过，2026-09-25 实测两实例并存）。
    # 锁随进程生死自动释放（含 SIGKILL），无残留。
    import fcntl

    _lock_path = PROJECT_DIR / "logs" / "api.lock"
    _lock_path.parent.mkdir(parents=True, exist_ok=True)
    _lock_fd = os.open(str(_lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.stderr.write(
            "[run.py] 单例锁已被持有：已有 API 实例在运行，拒绝启动"
            "（幽灵 supervisor 会造成双派发并行）。如需重启请先 `evo stop`。\n"
        )
        sys.exit(2)
    os.write(_lock_fd, f"pid={os.getpid()} started={datetime.now().isoformat()}\n".encode())

    _setup_log_redirect("api")

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "20160"))
    workers = int(os.getenv("WORKERS", "1"))
    reload = os.getenv("RELOAD", "false").lower() == "true"

    # 硬闸 2（端口探针，防御第二层）：端口已被占用 → 直接退出。否则会出现
    # "无端口但 supervisor 照跑"的幽灵实例——两个 dispatcher 各自认领派发，
    # 值守任务并行执行（2026-09-25 实测脑裂事故：执行中 2，串行失效）。
    if not reload:
        import socket

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(1.0)
        try:
            probe.connect(("127.0.0.1", port))
            probe.close()
            sys.stderr.write(
                f"[run.py] 端口 {port} 已被占用：已有 API 实例在运行，拒绝启动"
                "（幽灵 supervisor 会造成双派发并行）。如需重启请先 `evo stop`。\n"
            )
            sys.exit(2)
        except OSError:
            probe.close()

    print(f"Starting API Server on {host}:{port} (workers={workers})")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
        loop="asyncio",
        log_level=str(settings.LOG_LEVEL).lower(),
    )


def run_worker():
    """启动任务队列 Worker（独立进程）。"""
    import subprocess

    _setup_log_redirect("worker")

    # Pass through command line arguments
    cmd = [sys.executable, "-m", "bin.run_worker"] + sys.argv[2:]
    
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
    _reject_log_args(sys.argv[1:])

    parser = argparse.ArgumentParser(
        description="EvoLoop Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bin/run.py api                       # Start API server (logs -> backend/logs/api.log)
  python bin/run.py worker                    # Start Task Queue Worker (logs -> backend/logs/worker.log)
  python bin/run.py worker --workers=4        # Start Worker with 4 workers
  python bin/run.py export-openapi            # Export OpenAPI schema

Environment Variables:
  HOST                  API host (default: 0.0.0.0)
  PORT                  API port (default: 8123)
  WORKERS               Number of API workers (default: 1)
  RELOAD                Enable auto-reload (default: false)
  EMBEDDED_MODE         true→Huey / false→Celery

Logging:
  日志不接收参数，固定写入 backend/logs/ 目录：
    - api:    backend/logs/api.log
    - worker: backend/logs/worker.log
  每次启动自动归档旧日志为 {role}.log.bak_<时间戳>，
  并清除超过 LOG_RETENTION_DAYS 天的归档（默认 7 天，可用环境变量覆盖）。

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

    args, unknown = parser.parse_known_args()

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
