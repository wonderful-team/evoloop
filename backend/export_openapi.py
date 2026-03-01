
import os
import sys
import json
from app.main import app


def generate_openapi():
    print("Exporting OpenAPI Schema...")
    openapi_data = app.openapi()

    # Save to file
    output_path = "../frontend/openapi.json"
    with open(output_path, "w") as f:
        json.dump(openapi_data, f, indent=2)
    print(f"Schema exported to {os.path.abspath(output_path)}")


if __name__ == "__main__":
    generate_openapi()
