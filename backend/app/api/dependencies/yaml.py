"""
YAML Content-Type support for FastAPI
"""

from fastapi import Request, HTTPException

from app.utils.yaml import macro_from_yaml, YAMLError


async def parse_macro_body(request: Request) -> list[dict]:
    """
    Parse request body as macro steps, supporting both JSON and YAML.
    
    Content-Type headers:
    - application/json -> JSON parsing
    - application/yaml or text/yaml -> YAML parsing
    - application/x-yaml -> YAML parsing
    """
    content_type = request.headers.get("content-type", "application/json").lower()
    body = await request.body()
    content = body.decode("utf-8")
    
    try:
        if "yaml" in content_type or content_type == "text/yaml":
            return macro_from_yaml(content)
        else:
            import json
            data = json.loads(content)
            # Handle both {steps: [...]} and [...] formats
            return data.get("steps", data) if isinstance(data, dict) else data
    except (YAMLError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid format: {str(e)}")
