from typing import Any

from pydantic import BaseModel, Field


class NodeConfig(BaseModel):
    id: str
    xpath: str | None = Field(alias="path", default=None)  # e.g. "app.core.engine.nodes.coder.coder_node"
    # Subgraph Support
    type: str = "function"  # "function" | "generic" | "subgraph"
    # Note: We rely on 'path' being present for function/generic, or 'subgraph_config' for subgraph.
    subgraph_config: str | None = None  # Path to YAML file for subgraph

    @property
    def path(self):
        return self.xpath

    config: dict[str, Any] | None = Field(default_factory=dict)
    # Phase PD: Tool declarations for each node (replaces hardcoded RBAC in get_node_tools)
    tools: list[str] = Field(default_factory=list)


class EdgeConfig(BaseModel):
    from_node: str = Field(alias="from")
    to_node: str | None = Field(alias="to", default=None)
    type: str = "simple"  # simple | conditional
    router: str | None = None  # Path to router function
    map: dict[str, str] | None = None  # Mapping for conditional
    # Dynamic Router Support
    conditions: list[dict[str, str]] | None = None  # [{"expr": "...", "to": "..."}]
    default: str | None = None  # Fallback node


class AgentConfig(BaseModel):
    name: str
    version: str
    state_schema: str = "app.core.engine.state.AgentState"
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]
    # Human-in-the-Loop Support
    interrupt_before: list[str] = []  # Node IDs to interrupt BEFORE execution
    interrupt_after: list[str] = []  # Node IDs to interrupt AFTER execution
