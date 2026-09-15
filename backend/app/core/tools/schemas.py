"""Schemas for tools module."""

from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class EvoLoopToolConfig(DynamicBaseModel):
    """Configuration for EvoLoop tool metadata injected by the @evoloop_tool decorator."""

    is_state_mutating: bool = False
    affected_path_keys: list[str] = Field(default_factory=list)
    summary_template: str | None = None
    is_memory_tool: bool = False
    is_multimodal: bool = False
    is_hidden: bool = False
    handle_tool_error: bool = True
    is_hitl: bool = False  # If True, this tool triggers a human-in-the-loop request
    required_benefit: str | None = None
    description: str = ""

    def model_post_init(self, __context: Any) -> None:
        if self.affected_path_keys is None:
            self.affected_path_keys = []

    def get_display_name(self, tool_name: str, args: dict | None = None) -> str:
        from app.i18n.service import i18n

        args = (args or {}).copy()
        args = {k.lower(): v for k, v in args.items()}
        if "path" not in args:
            args["path"] = (
                args.get("file_path")
                or args.get("target_file")
                or args.get("targetfile")
                or args.get("dest")
                or args.get("src")
                or "unknown"
            )
        if "prompt" not in args:
            args["prompt"] = (
                args.get("action_description")
                or args.get("message")
                or args.get("intent")
                or None
            )
        if "pattern" not in args:
            args["pattern"] = (
                args.get("query")
                or args.get("name")
                or args.get("question")
                or args.get("target")
                or ""
            )
        if "count" not in args:
            if isinstance(args.get("steps"), list):
                args["count"] = len(args["steps"])
            elif isinstance(args.get("edits"), list):
                args["count"] = len(args["edits"])
            elif isinstance(args.get("files"), list):
                args["count"] = len(args["files"])
        if self.summary_template:
            display_name = i18n.get(self.summary_template, context=args)
        else:
            display_name = tool_name.replace("_", " ").title()
        return display_name
