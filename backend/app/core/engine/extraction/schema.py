import logging
from typing import Any, Dict, List, Type, Union

from pydantic import BaseModel, Field, create_model

from app.core.events.schemas.lifecycle import ExtractionRequest

logger = logging.getLogger(__name__)


def _dict_schema_to_model(name: str, schema: dict) -> Type[BaseModel]:
    """Convert a simple JSON schema dict to a Pydantic model class."""
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    fields = {}
    for prop_name, prop_def in properties.items():
        prop_type = prop_def.get("type", "string")
        is_required = prop_name in required

        if prop_type == "string":
            py_type = str
        elif prop_type == "integer":
            py_type = int
        elif prop_type == "number":
            py_type = float
        elif prop_type == "boolean":
            py_type = bool
        elif prop_type == "array":
            py_type = list
        elif prop_type == "object":
            py_type = dict
        else:
            py_type = str

        if not is_required:
            py_type = Union[py_type, None]

        default = ... if is_required else None
        fields[prop_name] = (py_type, Field(default=default, description=prop_def.get("description", "")))

    return create_model(name.capitalize() + "Item", **fields)  # type: ignore[no-any-return]


def build_dynamic_schema(requests: List[ExtractionRequest], include_base_fields: bool = True) -> Type[BaseModel] | None:
    if not requests and not include_base_fields:
        return None

    fields: Dict[str, Any] = {}
    if include_base_fields:
        fields["is_completed"] = (
            bool,
            Field(default=False, description="Whether the main user task/goal was completed successfully."),
        )
        fields["summary"] = (
            str,
            Field(default="Task completed.", description="Concise summary of what was accomplished in this session (2-3 sentences)."),
        )

    for req in requests:
        schema = req.schema_dict
        if isinstance(schema, dict):
            item_model = _dict_schema_to_model(req.name, schema)
            fields[req.name] = (list[item_model], Field(default_factory=list, description=req.description))
        else:
            logger.warning("[build_dynamic_schema] Plugin '%s' schema is not a dict.", req.name)

    return create_model("DynamicVerdict", **fields)  # type: ignore[no-any-return]
