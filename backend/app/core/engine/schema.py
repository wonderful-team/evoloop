from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.infrastructure.pydantic_base import DynamicBaseModel


class NodeParameters(DynamicBaseModel):
    pass


class NodeConfigPayload(DynamicBaseModel):
    intent: str | None = None
    parameters: NodeParameters = Field(default_factory=NodeParameters)
    tools: list[str] = Field(default_factory=list)


class EdgeCondition(DynamicBaseModel):
    expr: str
    to: str


class NodeConfig(DynamicBaseModel):
    """Configuration for a graph node."""
    id: str
    xpath: str | None = Field(alias="path", default=None)  # e.g. "app.core.engine.nodes.worker.worker_node"
    type: Literal["function", "generic"] = "function"

    @property
    def path(self):
        return self.xpath

    config: NodeConfigPayload | None = Field(default_factory=NodeConfigPayload)
    tools: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_node_type(self) -> 'NodeConfig':
        if not self.xpath:
            raise ValueError(f"Node '{self.id}' is missing 'path'")
        return self


class EdgeConfig(DynamicBaseModel):
    """Configuration for a graph edge."""
    from_node: str = Field(alias="from")
    to_node: str | None = Field(alias="to", default=None)
    type: Literal["simple", "conditional"] = "simple"
    router: str | None = None  # Path to router function
    map: dict[str, str] | None = None  # Mapping for conditional
    conditions: list[EdgeCondition] | None = None
    default: str | None = None  # Fallback node

    @model_validator(mode="after")
    def validate_edge_type(self) -> 'EdgeConfig':
        if self.type == "simple" and not self.to_node:
            raise ValueError(f"Simple edge from '{self.from_node}' is missing 'to' field")
        if self.type == "conditional" and not (self.router or self.conditions):
            raise ValueError(f"Conditional edge from '{self.from_node}' must have either 'router' or 'conditions'")
        return self


class AgentGraphConfig(DynamicBaseModel):
    """Configuration for an agent graph."""
    name: str
    version: str
    state_schema: str = "app.core.engine.state.AgentState"
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]
    interrupt_before: list[str] = Field(default_factory=list)
    interrupt_after: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph_connectivity(self) -> 'AgentGraphConfig':
        """Ensure all nodes referenced in edges exist in the node list."""
        node_ids = {node.id for node in self.nodes}
        node_ids.add("END")
        
        for edge in self.edges:
            if edge.from_node not in node_ids:
                raise ValueError(f"Edge starts from unknown node '{edge.from_node}'")
            
            if edge.to_node and edge.to_node not in node_ids:
                raise ValueError(f"Edge to unknown node '{edge.to_node}'")
                
            if edge.conditions:
                for cond in edge.conditions:
                    if cond.to not in node_ids:
                        raise ValueError(f"Conditional edge branch lead to unknown node '{cond.to}'")
            
            if edge.map:
                for target_node in edge.map.values():
                    if target_node not in node_ids:
                        raise ValueError(f"Router map target '{target_node}' is an unknown node")
            
            if edge.default and edge.default not in node_ids:
                raise ValueError(f"Default edge target '{edge.default}' is an unknown node")
        
        return self
