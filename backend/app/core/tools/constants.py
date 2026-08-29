"""Tool registry constants."""

from pathlib import Path

#: Default YAML config path for node-level tool RBAC.
DEFAULT_CONFIG_PATH = (
    Path(__file__).parent.parent / "engine" / "config" / "agent_main.yaml"
)
