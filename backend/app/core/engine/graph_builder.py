import importlib
import inspect
import logging
from typing import Any

import yaml
from langgraph.graph import END, StateGraph

from app.core.engine.schema import AgentGraphConfig as AgentConfig

logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    Factory class that builds a LangGraph StateGraph from a configuration file.
    """

    def _import_obj(self, path: str) -> Any:
        """
        Dynamically imports an object (class, function, variable) from a string path.
        e.g. "app.core.engine.nodes.worker.WorkerNode"
        """
        try:
            module_name, obj_name = path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            return getattr(module, obj_name)
        except (ImportError, AttributeError, ValueError) as e:
            logger.error(f"Failed to import {path}: {e}")
            raise

    def build(self, config_path: str, checkpointer=None):
        """
        Build a StateGraph from YAML configuration.
        
        Args:
            config_path: Path to YAML configuration file
            checkpointer: Optional checkpointer for persistence
            
        Returns:
            Compiled StateGraph
        """
        logger.info(f"Building Agent Graph from {config_path}")

        # 1. Load Config
        with open(config_path) as f:
            raw_config = yaml.safe_load(f)

        agent_config = AgentConfig.model_validate(raw_config)

        # 2. Load State Schema
        StateClass = self._import_obj(agent_config.state_schema)
        workflow = StateGraph(StateClass)

        # 3. Add Nodes
        for node in agent_config.nodes:
            node_impl = self._import_obj(node.path)
            if inspect.isclass(node_impl):
                node_func = node_impl()
                logger.info(
                    f"Adding Node: {node.id} | Implementation: {node.path} | "
                    f"Auto-instantiated class: {node_impl.__name__}"
                )
            elif callable(node_impl):
                node_func = node_impl
                logger.info(
                    f"Adding Node: {node.id} | Implementation: {node.path} | "
                    f"Callable: {getattr(node_func, '__name__', type(node_func).__name__)}"
                )
            else:
                raise TypeError(f"Node {node.id} at {node.path} is not callable")

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
                    # Expression Router
                    from app.core.engine.routers import make_expression_router
                    router_func = make_expression_router(edge.conditions, edge.default or "")
                    mapping = {c.to: c.to for c in edge.conditions}
                    if edge.default:
                        mapping[edge.default] = edge.default
                    for k, v in mapping.items():
                        if v == "END":
                            mapping[k] = END
                    workflow.add_conditional_edges(edge.from_node, router_func, mapping)
                else:
                    # Python Router Function
                    router_func = self._import_obj(edge.router)
                    mapping = edge.map.copy() if edge.map else {}
                    for k, v in mapping.items():
                        if v == "END":
                            mapping[k] = END
                    workflow.add_conditional_edges(edge.from_node, router_func, mapping)

        # 5. Set Entry Point
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
