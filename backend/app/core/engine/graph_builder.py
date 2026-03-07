import importlib
import logging
import os
from typing import Any

import yaml
from langgraph.graph import END, StateGraph

from app.core.engine.schema import AgentConfig

logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    Factory class that builds a LangGraph StateGraph from a configuration file.
    """

    def _import_obj(self, path: str) -> Any:
        """
        Dynamically imports an object (class, function, variable) from a string path.
        e.g. "app.core.engine.nodes.worker.worker_node"
        """
        try:
            module_name, obj_name = path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            return getattr(module, obj_name)
        except (ImportError, AttributeError, ValueError) as e:
            logger.error(f"Failed to import {path}: {e}")
            raise

    def build(self, config_path: str, checkpointer=None):
        logger.info(f"Building Agent Graph from {config_path}")

        # 1. Load Config
        with open(config_path) as f:
            raw_config = yaml.safe_load(f)

        agent_config = AgentConfig(**raw_config)

        # 2. Load State Schema
        StateClass = self._import_obj(agent_config.state_schema)
        workflow = StateGraph(StateClass)

        # 3. Add Nodes
        for node in agent_config.nodes:
            if node.type == "subgraph":
                # Recursive Sub-Graph Construction
                # Resolve relative path
                if not node.subgraph_config:
                    logger.error(f"Subgraph node {node.id} missing configuration path.")
                    continue
                base_dir = os.path.dirname(os.path.abspath(config_path))
                sub_config_path = os.path.join(base_dir, node.subgraph_config)

                logger.info(f"Recursively building Sub-Graph node: {node.id} from {sub_config_path}")

                # Recursion!
                sub_builder = GraphBuilder()
                # Pass checkpointer down if needed, or null for subgraphs usually
                compiled_subgraph = sub_builder.build(sub_config_path, checkpointer=checkpointer)

                node_func = compiled_subgraph

            else:
                # Legacy: Dynamic Import of Python Function
                node_func = self._import_obj(node.path)

            workflow.add_node(node.id, node_func)

        # 4. Add Edges
        for edge in agent_config.edges:
            if edge.type == "simple":
                logger.info(f"Adding Edge: {edge.from_node} -> {edge.to_node}")
                src = edge.from_node
                dst = edge.to_node
                if dst == "END":
                    dst = END
                workflow.add_edge(src, dst)

            elif edge.type == "conditional":
                logger.info(f"Adding Conditional Edge from {edge.from_node}")

                if edge.conditions:
                    # New: Expression Router
                    from app.core.engine.routers import make_expression_router

                    router_func = make_expression_router(edge.conditions, edge.default or "")

                    # Construct mapping automatically from conditions
                    mapping = {c["to"]: c["to"] for c in edge.conditions}
                    if edge.default:
                        mapping[edge.default] = edge.default

                    # Handle END
                    for k, v in mapping.items():
                        if v == "END":
                            mapping[k] = END

                    workflow.add_conditional_edges(edge.from_node, router_func, mapping)
                else:
                    # Legacy: Python Router Function
                    if not edge.router:
                        logger.error(f"Conditional edge from {edge.from_node} missing router path.")
                        continue
                    router_func = self._import_obj(edge.router)
                    mapping = edge.map.copy() if edge.map else {}

                    # Resolving END mapping
                    for k, v in mapping.items():
                        if v == "END":
                            mapping[k] = END

                    workflow.add_conditional_edges(edge.from_node, router_func, mapping)

        # 5. Set Entry Point
        # Heuristic: The first node defined is usually the entry point?
        # Or explicit field. Let's assume 'router' or first node.
        # For now, let's hardcode 'router' if exists, else first node.
        node_ids = [n.id for n in agent_config.nodes]
        if "router" in node_ids:
            workflow.set_entry_point("router")
        else:
            workflow.set_entry_point(node_ids[0])

        return workflow.compile(
            checkpointer=checkpointer,
            interrupt_before=agent_config.interrupt_before or None,
            interrupt_after=agent_config.interrupt_after or None,
        )
