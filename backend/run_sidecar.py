import sys
import os

print("SIDECAR: Starting process...", file=sys.stderr, flush=True)

# Force unbuffered output for Tauri capturing
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

try:
    import multiprocessing
    from dotenv import load_dotenv

    # Locate .env
    # We look up to 3 levels up
    cwd = os.getcwd()
    env_path = None
    for i in range(4):
        p = os.path.join(cwd, *(['..'] * i), ".env")
        if os.path.exists(p):
            env_path = os.path.abspath(p)
            break

    if env_path:
        print(f"SIDECAR: Loading .env from {env_path}", file=sys.stderr, flush=True)
        load_dotenv(env_path)
    else:
        print("SIDECAR: .env not found, relying on environment variables", file=sys.stderr, flush=True)

    from app.logging import logger

    print("SIDECAR: Imports successful", file=sys.stderr, flush=True)
except Exception as e:
    print(f"SIDECAR: Import Error: {e}", file=sys.stderr, flush=True)
    sys.exit(1)

# Initialize sys.path if needed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_api():
    import uvicorn
    import app.main

    # Retrieve port/host from env or args if needed, but for now strict defaults or env vars
    # In Rust we called: fastapi run app/main.py --workers 4
    # uvicorn.run equivalents:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    logger.info(f"Starting API Server on {host}:{port}")
    # Pass the app object directly to ensure PyInstaller bundles it
    # Use workers=1 for safer frozen execution (multiprocessing can be flaky in sidecars)
    uvicorn.run(app.main.app, host=host, port=port, reload=False, workers=1)


def run_worker():
    from app.celery_app import celery_app
    from celery.bin import worker

    logger.info("Starting Celery Worker...")
    # celery -A app.celery_app worker -l info -P solo -Q celery
    argv = [
        'worker',
        '--loglevel=info',
        '--pool=solo',
        '--queues=celery'
    ]
    celery_app.worker_main(argv=argv)


if __name__ == "__main__":
    multiprocessing.freeze_support()

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "api":
            try:
                run_api()
            except Exception as e:
                logger.error(f"API Server crashed: {e}")
                sys.exit(1)
        elif command == "worker":
            try:
                run_worker()
            except Exception as e:
                logger.error(f"Celery Worker crashed: {e}")
                sys.exit(1)
        else:
            print(f"Unknown command: {command}")
            print("Usage: evoloop-backend [api|worker]")
            sys.exit(1)
    else:
        # Default to API if no args? Or error?
        print("Usage: evoloop-backend [api|worker]")
        sys.exit(1)
