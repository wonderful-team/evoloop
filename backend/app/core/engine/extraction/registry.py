"""
Extraction Registry
===================

Central registry for extraction plugins. Each plugin describes what it
extracts and how to persist it. The Finish node uses the registry to:
1. Build a dynamic prompt section for the audit LLM
2. Parse <evoloop_extractions> from the LLM response
3. Dispatch parsed items to each plugin's handler (no additional LLM calls)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Regex to extract the <evoloop_extractions> block from LLM output
EXTRACTIONS_BLOCK_RE = re.compile(
    r"<evoloop_extractions>(.*?)</evoloop_extractions>",
    re.DOTALL,
)

# Regex to extract individual <extraction> items
EXTRACTION_ITEM_RE = re.compile(
    r'<extraction\s+name="([^"]+)"\s+confidence="([^"]+)"\s*>(.*?)</extraction>',
    re.DOTALL,
)


@dataclass
class ExtractionContext:
    """Context passed to every extraction handler for persistence."""

    thread_id: str
    project_id: int | None = None
    user_id: str | None = None
    run_id: str | None = None
    summary: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionPlugin:
    """A single extraction plugin.

    Each plugin declares what it extracts, the expected JSON schema, and
    the async handler that persists the extracted items.

    Attributes:
        name: Unique plugin identifier (e.g. ``"knowledge"``).
        description: Natural-language description shown to the LLM so it
            knows when to emit extractions for this plugin.
        output_schema: A JSON Schema dict or Pydantic BaseModel class describing
            the expected shape of each extracted item.
        confidence_threshold: Minimum confidence (0-1) required for the
            LLM's output to be accepted. Items below this threshold are
            silently dropped.
        handler: Async callable ``(data: dict, ctx: ExtractionContext) -> None``
            that persists the extracted item.
        enabled_config_key: SystemConfig key to check if plugin is enabled.
    """

    name: str
    description: str
    output_schema: Any
    confidence_threshold: float = 0.7
    handler: Callable[[dict[str, Any], ExtractionContext], None] | None = None
    enabled_config_key: str | None = None


# JSON Schema type → Python type mapping
_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _dict_schema_to_model(name: str, schema: dict) -> type:
    """Convert a JSON Schema dict to a dynamic Pydantic model."""
    from pydantic import Field, create_model

    props = schema.get("properties", {})
    required_set = set(schema.get("required", []))
    model_fields: dict[str, tuple] = {}

    for prop_name, prop_schema in props.items():
        json_type = prop_schema.get("type", "string")
        py_type = _JSON_TYPE_MAP.get(json_type, str)

        if prop_schema.get("items"):
            item_type = _JSON_TYPE_MAP.get(
                prop_schema.get("items", {}).get("type", "string"), str
            )
            py_type = list[item_type]  # type: ignore[valid-type]

        if prop_name in required_set:
            model_fields[prop_name] = (py_type, Field(..., description=prop_schema.get("description", "")))
        else:
            model_fields[prop_name] = (py_type | None, Field(default=None, description=prop_schema.get("description", "")))

    return create_model(f"{name.title()}Item", **model_fields)  # type: ignore[arg-type]


class ExtractionRegistry:
    """Global registry of extraction plugins.

    Usage::

        ExtractionRegistry.register(ExtractionPlugin(
            name="knowledge",
            description="Extract architectural decisions...",
            output_schema={...},
            handler=my_handler,
        ))
    """

    _plugins: dict[str, ExtractionPlugin] = {}
    _handled_threads: set[str] = set()
    _MAX_HANDLED = 10000

    @classmethod
    def mark_thread_handled(cls, thread_id: str) -> None:
        if len(cls._handled_threads) >= cls._MAX_HANDLED:
            cls._handled_threads.clear()
        cls._handled_threads.add(thread_id)

    @classmethod
    def is_thread_handled(cls, thread_id: str) -> bool:
        """Check if extraction was already dispatched for this thread."""
        return thread_id in cls._handled_threads

    @classmethod
    def register(cls, plugin: ExtractionPlugin) -> None:
        """Register an extraction plugin."""
        if plugin.name in cls._plugins:
            logger.warning(
                "[ExtractionRegistry] Overwriting existing plugin: %s", plugin.name
            )
        cls._plugins[plugin.name] = plugin
        logger.debug(
            "[ExtractionRegistry] Registered plugin: %s (threshold=%.2f)",
            plugin.name,
            plugin.confidence_threshold,
        )

    @classmethod
    def get(cls, name: str) -> ExtractionPlugin | None:
        """Get a registered plugin by name."""
        return cls._plugins.get(name)

    @classmethod
    def list_plugins(cls) -> list[ExtractionPlugin]:
        """Return all registered plugins."""
        return list(cls._plugins.values())

    @classmethod
    def get_active_plugins(cls) -> list[ExtractionPlugin]:
        """Return all active plugins based on settings/system config."""
        from app.infrastructure.config.service import SystemConfigService
        active = []
        for p in cls.list_plugins():
            if p.enabled_config_key:
                is_enabled = SystemConfigService.get_value(p.enabled_config_key, "true").lower() == "true"
                if not is_enabled:
                    continue
            active.append(p)
        return active

    @classmethod
    def build_dynamic_schema(cls, include_base_fields: bool = True) -> type | None:
        """Dynamically build a Pydantic model class for structured audit.

        Handles both Pydantic BaseModel and dict JSON Schema as output_schema.
        """
        from pydantic import BaseModel, Field, create_model

        active_plugins = cls.get_active_plugins()
        if not active_plugins and not include_base_fields:
            return None

        fields: dict = {}
        if include_base_fields:
            fields["is_completed"] = (
                bool,
                Field(
                    default=False,
                    description="Whether the main user task/goal was completed successfully.",
                ),
            )
            fields["summary"] = (
                str,
                Field(
                    default="Task completed.",
                    description="Concise summary of what was accomplished in this session (2-3 sentences).",
                ),
            )

        for plugin in active_plugins:
            schema = plugin.output_schema
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                fields[plugin.name] = (list[schema], Field(default_factory=list, description=plugin.description))
            elif isinstance(schema, dict):
                item_model = _dict_schema_to_model(plugin.name, schema)
                fields[plugin.name] = (list[item_model], Field(default_factory=list, description=plugin.description))
            else:
                logger.warning(
                    "[ExtractionRegistry] Plugin '%s' output_schema is neither dict nor BaseModel, skipping.",
                    plugin.name,
                )

        DynamicVerdict = create_model("DynamicVerdict", **fields)  # type: ignore[arg-type]
        return DynamicVerdict

    @classmethod
    def build_prompt_section(cls) -> str:
        """Build the dynamic extraction section for the LLM prompt.

        Returns a block of text describing all registered extraction types
        and their expected output format.  Insert this into the system prompt
        for the Session Reviewer agent.
        """
        plugins = cls.get_active_plugins()
        if not plugins:
            return ""

        lines = [
            "",
            "### Optional: Knowledge & State Extraction",
            "",
            "During your audit, if the conversation contains information worth "
            "preserving, you may optionally include an ``<evoloop_extractions>`` "
            "block in your response. Only include items with confidence >= 0.7.",
            "",
            "Available extraction types:",
            "",
        ]

        for i, p in enumerate(plugins, 1):
            from pydantic import BaseModel
            if isinstance(p.output_schema, type) and issubclass(p.output_schema, BaseModel):
                schema_dict = p.output_schema.model_json_schema()
            else:
                schema_dict = p.output_schema
            schema_str = json.dumps(schema_dict, ensure_ascii=False)
            lines.append(f"{i}. **{p.name}** — {p.description}")
            lines.append(f"   Schema: {schema_str}")
            lines.append("")

        lines.append("Output format within your ``<evoloop_extractions>`` block:")
        lines.append("""```xml
<evoloop_extractions>
  <extraction name="knowledge" confidence="0.85">
    {\\"title\\": \\"...\\", \\"content\\": \\"...\\"}
  </extraction>
  <extraction name="memory" confidence="0.9">
    {\\"type\\": \\"preference\\", \\"content\\": \\"...\\"}
  </extraction>
</evoloop_extractions>
```""")
        lines.append(
            "If nothing worth preserving was discussed, omit the "
            "<evoloop_extractions> block entirely."
        )
        lines.append("")

        return "\n".join(lines)

    @classmethod
    def parse_extractions(cls, llm_output: str) -> list[dict[str, Any]]:
        """Parse ``<evoloop_extractions>`` from the LLM output.

        Returns a list of dicts with keys: ``name``, ``confidence``, ``data``.
        """
        block_match = EXTRACTIONS_BLOCK_RE.search(llm_output)
        if not block_match:
            return []

        block_content = block_match.group(1).strip()
        items: list[dict[str, Any]] = []

        for item_match in EXTRACTION_ITEM_RE.finditer(block_content):
            name = item_match.group(1).strip()
            try:
                confidence = float(item_match.group(2).strip())
            except (ValueError, TypeError):
                confidence = 0.0

            raw_data = item_match.group(3).strip()
            try:
                data = json.loads(raw_data) if raw_data else {}
            except json.JSONDecodeError as e:
                logger.warning(
                    "[ExtractionRegistry] Failed to parse JSON for '%s': %s",
                    name,
                    e,
                )
                continue

            items.append(
                {
                    "name": name,
                    "confidence": confidence,
                    "data": data,
                }
            )

        return items

    @classmethod
    async def dispatch(
        cls,
        items: list[dict[str, Any]],
        ctx: ExtractionContext,
    ) -> int:
        """Dispatch parsed extraction items to their registered handlers.

        Returns the number of successfully handled items.
        """
        if ctx.thread_id:
            cls.mark_thread_handled(ctx.thread_id)
        handled = 0
        for item in items:
            name = item["name"]
            confidence = item["confidence"]
            data = item["data"]

            plugin = cls.get(name)
            if plugin is None:
                logger.debug(
                    "[ExtractionRegistry] No plugin registered for '%s', skipping",
                    name,
                )
                continue

            if confidence < plugin.confidence_threshold:
                logger.debug(
                    "[ExtractionRegistry] '%s' confidence %.2f below threshold %.2f",
                    name,
                    confidence,
                    plugin.confidence_threshold,
                )
                continue

            if plugin.handler is None:
                logger.debug(
                    "[ExtractionRegistry] Plugin '%s' has no handler, skipping",
                    name,
                )
                continue

            try:
                if asyncio.iscoroutinefunction(plugin.handler):
                    await plugin.handler(data, ctx)
                else:
                    plugin.handler(data, ctx)
                handled += 1
                logger.debug(
                    "[ExtractionRegistry] Dispatched '%s' (conf=%.2f)",
                    name,
                    confidence,
                )
            except Exception as e:
                logger.error(
                    "[ExtractionRegistry] Handler '%s' failed: %s",
                    name,
                    e,
                )

        return handled

    @classmethod
    async def dispatch_structured(
        cls,
        verdict_dict: dict[str, Any],
        ctx: ExtractionContext,
    ) -> int:
        """Dispatch structured dictionary from Pydantic dynamic verdict.

        verdict_dict contains keys corresponding to plugin names, and values as list of dicts.
        """
        if ctx.thread_id:
            cls.mark_thread_handled(ctx.thread_id)

        handled = 0
        for plugin in cls.list_plugins():
            items = verdict_dict.get(plugin.name)
            if not items:
                continue

            for item in items:
                # Check confidence if present
                confidence = item.get("confidence", 1.0)
                if confidence < plugin.confidence_threshold:
                    logger.debug(
                        "[ExtractionRegistry] '%s' confidence %.2f below threshold %.2f",
                        plugin.name,
                        confidence,
                        plugin.confidence_threshold,
                    )
                    continue

                if plugin.handler is None:
                    continue

                try:
                    # Deep copy ctx to avoid mutating shared extra fields
                    import copy
                    plugin_ctx = copy.copy(ctx)
                    # Expose the specific item's confidence in extraction context extra dict
                    plugin_ctx.extra = copy.copy(ctx.extra)
                    plugin_ctx.extra["confidence"] = confidence

                    if asyncio.iscoroutinefunction(plugin.handler):
                        await plugin.handler(item, plugin_ctx)
                    else:
                        plugin.handler(item, plugin_ctx)
                    handled += 1
                    logger.debug(
                        "[ExtractionRegistry] Dispatched structured '%s' (conf=%.2f)",
                        plugin.name,
                        confidence,
                    )
                except Exception as e:
                    logger.error(
                        "[ExtractionRegistry] Handler '%s' failed: %s",
                        plugin.name,
                        e,
                    )
        return handled

    @classmethod
    async def parse_and_dispatch_from_messages(
        cls,
        messages: list,
        ctx: ExtractionContext,
    ) -> int:
        """Convenience: find extractions in audit messages and dispatch them.

        Iterates messages in reverse, finds the last AIMessage containing
        ``<evoloop_extractions>``, parses it, and dispatches.
        """
        for msg in reversed(messages):
            from langchain_core.messages import AIMessage

            if not isinstance(msg, AIMessage):
                continue
            content = str(msg.content) if msg.content else ""
            if "<evoloop_extractions>" not in content:
                continue

            items = cls.parse_extractions(content)
            if items:
                handled = await cls.dispatch(items, ctx)
                return handled
        return 0
