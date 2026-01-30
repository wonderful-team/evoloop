import json
import os
import sys

from fastapi.openapi.utils import get_openapi

from app.main import app

# Add project root to path
sys.path.append(os.getcwd())


def generate_openapi():
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    print(json.dumps(openapi_schema, indent=2))


if __name__ == "__main__":
    generate_openapi()
