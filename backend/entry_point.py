"""Entry point for PyInstaller to start the EvoLoop backend server."""
import os
import sys

# PyInstaller multiprocessing fix
from multiprocessing import freeze_support
freeze_support()

# Embedded mode: Use file-based token storage instead of macOS Keychain
# This avoids keychain authorization prompts in PyInstaller builds
os.environ["EVOLOOP_BUNDLED_APP"] = "true"
os.environ["EVOLOOP_TOKEN_STORAGE"] = "file"

# Ensure the app package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def parse_args():
    """Parse command line arguments. Supports both --host/--port and env vars."""
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8123"))
    
    # Parse command line arguments (sidecar passes --host and --port)
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            i += 1
    
    return host, port

def main():
    # Parse command line arguments
    host, port = parse_args()
    
    # Log startup info
    print(f"Starting EvoLoop Backend on {host}:{port}", flush=True)
    
    # Import here to avoid multiprocessing issues
    import uvicorn
    from uvicorn.config import Config
    from uvicorn.server import Server
    
    # Use single process mode (no workers)
    config = Config(
        "app.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
        workers=None,  # None = single process
        loop="asyncio",
    )
    server = Server(config)
    server.run()

if __name__ == "__main__":
    freeze_support()
    main()
