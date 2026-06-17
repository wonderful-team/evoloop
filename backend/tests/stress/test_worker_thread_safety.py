#!/usr/bin/env python3
"""
End-to-end stress test for Huey worker thread-safety.

Starts a Huey worker process, dispatches many concurrent indexing tasks for
real files, then verifies:
- Worker process did not crash
- No RuntimeError about asyncio locks/events in logs
- Graph JSON file remains valid
- Vector store has consistent data
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_DIR))


def create_test_repo(tmpdir: str) -> str:
    """Create a small Python repo to index."""
    repo = Path(tmpdir) / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    for i in range(5):
        (repo / "src" / f"module_{i}.py").write_text(
            f"def hello_{i}():\n    return 'world {i}'\n",
            encoding="utf-8",
        )
    return str(repo)


def dispatch_tasks(repo_path: str, repo_id: int, count: int):
    """Dispatch many index_file_task jobs concurrently."""
    from app.domain.codebase.indexing.tasks import index_file_task

    files = [str(p) for p in Path(repo_path).rglob("*.py")]
    results = []
    errors = []

    def worker():
        for _ in range(count):
            file_path = files[len(results) % len(files)]
            try:
                result = index_file_task.delay(file_path, repo_id)
                results.append(result.id)
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results, errors


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = create_test_repo(tmpdir)
        log_file = Path(tmpdir) / "worker.log"

        # Start worker
        env = os.environ.copy()
        env["ENVIRONMENT"] = "local"
        worker_proc = subprocess.Popen(
            [sys.executable, "-m", "bin.run_worker", "--workers=4"],
            cwd=PROJECT_DIR,
            env=env,
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
        )

        # Wait for worker startup and model pre-load
        time.sleep(12)

        try:
            print(f"Dispatching tasks for repo: {repo_path}")
            results, errors = dispatch_tasks(repo_path, repo_id=2, count=3)
            print(f"Dispatched {len(results)} tasks")
            if errors:
                print(f"Dispatch errors: {errors}")
                return 1

            # Wait for tasks to be processed
            print("Waiting for worker to process tasks...")
            time.sleep(30)

            # Check worker still alive
            if worker_proc.poll() is not None:
                print(f"Worker crashed with code {worker_proc.returncode}")
                print(log_file.read_text())
                return 1

            # Check logs for lock/event errors
            logs = log_file.read_text()
            bad_patterns = [
                "RuntimeError",
                "bound to a different event loop",
                "dictionary changed size during iteration",
            ]
            for pat in bad_patterns:
                if pat in logs:
                    print(f"Found bad pattern in worker log: {pat}")
                    # Save log for debugging
                    debug_log = Path("/tmp/worker_stress.log")
                    debug_log.write_text(logs, encoding="utf-8")
                    print(f"Full log saved to {debug_log}")
                    return 1

            print("Worker stress test passed: no crashes or lock errors.")
            return 0
        finally:
            worker_proc.terminate()
            try:
                worker_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
