import json
from datetime import datetime, date
from typing import Any, Callable, Optional

def _json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def dumps(obj: Any, ensure_ascii: bool = False, default: Optional[Callable] = None, **kwargs) -> str:
    """
    Serialize object to JSON string.
    Defaults directly to supporting datetime serialization and disabling ASCII escaping (for UTF-8).
    """
    if default is None:
        default = _json_serial
        
    return json.dumps(obj, ensure_ascii=ensure_ascii, default=default, **kwargs)

def loads(s: str | bytes, **kwargs) -> Any:
    """
    Deserialize JSON string to object.
    Wrapper for consistency.
    """
    return json.loads(s, **kwargs)
