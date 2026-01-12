
import os
import sys
import traceback

# Add backend directory to path
sys.path.append(os.getcwd())

try:
    print("Checking imports...")
    from app.main import app
    print("SUCCESS: app.main imported successfully.")
    
    from app.core import config
    print("SUCCESS: app.core.config imported successfully.")

    from app.api.deps import get_current_user_optional
    print("SUCCESS: app.api.deps.get_current_user_optional imported successfully.")

    from app.api.routes import agent, projects, mcp
    print("SUCCESS: New API routes imported successfully.")

except Exception:
    print("FAILURE: Import validation failed:")
    traceback.print_exc()
    sys.exit(1)
