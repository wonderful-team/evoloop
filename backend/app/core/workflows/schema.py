from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

class NodeConfig(BaseModel):
    id: str
    xpath: Optional[str] = Field(alias="path", default=None)  # e.g. "app.core.workflows.nodes.coder.coder_node"
    # Subgraph Support
    type: str = "function" # "function" | "generic" | "subgraph"
    # Note: We rely on 'path' being present for function/generic, or 'subgraph_config' for subgraph.
    subgraph_config: Optional[str] = None # Path to YAML file for subgraph
    
    @property
    def path(self):
        return self.xpath
    
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)

class EdgeConfig(BaseModel):
    from_node: str = Field(alias="from")
    to_node: Optional[str] = Field(alias="to", default=None)
    type: str = "simple"  # simple | conditional
    router: Optional[str] = None # Path to router function
    map: Optional[Dict[str, str]] = None # Mapping for conditional
    # Dynamic Router Support
    conditions: Optional[List[Dict[str, str]]] = None # [{"expr": "...", "to": "..."}]
    default: Optional[str] = None # Fallback node

class AgentConfig(BaseModel):
    name: str
    version: str
    state_schema: str = "app.core.workflows.state.AgentState"
    nodes: List[NodeConfig]
    edges: List[EdgeConfig]
