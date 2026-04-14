"""Integration between Worker nodes and MCP sessions."""

import logging

from langchain_core.tools import StructuredTool

from app.core.engine.state.config import ExecutionTicket
from app.core.mcp import mcp_client_manager
from app.core.mcp.worker import worker_mcp_manager
from app.core.mcp.worker_config import WorkerMcpConfig

logger = logging.getLogger(__name__)


class WorkerMcpIntegration:
    """
    Integrates Worker-specific MCP into tool management.
    
    This class bridges the gap between Worker lifecycle and MCP connections:
    1. Initialize MCP sessions when Worker starts
    2. Provide tools to Worker during execution
    3. Cleanup sessions when Worker ends
    """
    
    @staticmethod
    async def initialize_worker_mcp(
        worker_id: str,
        worker_name: str,
        mcp_config: WorkerMcpConfig | None,
        execution_ticket: ExecutionTicket | None
    ) -> list[StructuredTool]:
        """
        Initialize MCP for a Worker and return available tools.
        
        Args:
            worker_id: Unique worker instance ID
            worker_name: Worker role name
            mcp_config: Worker's MCP configuration
            execution_ticket: Execution ticket with mcp_servers_required
            
        Returns:
            List of tools available to this Worker
        """
        if not mcp_config or mcp_config.is_empty():
            # No Worker-specific MCP config, use global MCP only
            # Check execution_ticket for requested global servers
            requested_servers = execution_ticket.mcp_servers_required or [] if execution_ticket else []
            if requested_servers:
                # Ensure global servers are connected and return their tools
                tools = []
                for server_name in requested_servers:
                    server_tools = await mcp_client_manager.get_tools(server_name)
                    tools.extend(server_tools)
                return tools
            return []
        
        # Create isolated Worker MCP session
        session = worker_mcp_manager.create_session(worker_id, worker_name)
        all_tools: list[StructuredTool] = []
        
        # 1. Connect Worker-specific servers
        if mcp_config.auto_connect:
            for server_config in mcp_config.servers:
                # Skip if inheriting from global
                if server_config.inherit_from_global:
                    continue
                
                mcp_cfg = server_config.to_mcp_config()
                success = await session.connect_server(mcp_cfg)
                
                if success:
                    # Add tools from this server
                    server_tools = session.get_tools_for(server_config.name)
                    all_tools.extend(server_tools)
                    logger.info(
                        f"[WorkerMcp] {worker_name} loaded {len(server_tools)} tools "
                        f"from {server_config.name}"
                    )
                else:
                    logger.warning(
                        f"[WorkerMcp] {worker_name} failed to connect to "
                        f"{server_config.name}"
                    )
        
        # 2. Handle inherited global servers
        for server_name in mcp_config.inherit_servers:
            # Check if this server was explicitly requested in ticket
            requested_servers = execution_ticket.mcp_servers_required or [] if execution_ticket else []
            
            if server_name in requested_servers:
                # Use global connection, get tools
                server_tools = await mcp_client_manager.get_tools(server_name)
                # Rename tools to indicate they're from global
                for tool in server_tools:
                    # Update description to indicate shared connection
                    tool.description = f"[Shared] {tool.description}"
                all_tools.extend(server_tools)
                logger.info(
                    f"[WorkerMcp] {worker_name} inherited {len(server_tools)} tools "
                    f"from global {server_name}"
                )
        
        # 3. Handle dynamically requested servers from execution_ticket
        # These are servers requested via use_mcp_server tool
        requested_servers = execution_ticket.mcp_servers_required or [] if execution_ticket else []
        for server_name in requested_servers:
            # Skip if already handled
            if any(s.name == server_name for s in mcp_config.servers):
                continue
            if server_name in mcp_config.inherit_servers:
                continue
            
            # Try to connect dynamically
            server_tools = await mcp_client_manager.get_tools(server_name)
            all_tools.extend(server_tools)
            logger.info(
                f"[WorkerMcp] {worker_name} dynamically loaded {len(server_tools)} tools "
                f"from {server_name}"
            )
        
        # Log summary
        summary = session.get_connection_summary()
        logger.info(
            f"[WorkerMcp] {worker_name} initialized with "
            f"{summary['tools_count']} tools from "
            f"{len(summary['connected_servers'])} servers"
        )
        
        return all_tools
    
    @staticmethod
    def get_worker_tools(worker_id: str) -> list[StructuredTool]:
        """
        Get tools from a Worker's existing MCP session.
        
        Args:
            worker_id: Worker instance ID
            
        Returns:
            List of tools (empty if no session)
        """
        session = worker_mcp_manager.get_session(worker_id)
        if session:
            return session.get_tools()
        return []
    
    @staticmethod
    async def cleanup_worker_mcp(worker_id: str) -> None:
        """
        Cleanup MCP session for a Worker.
        
        Args:
            worker_id: Worker instance ID
        """
        await worker_mcp_manager.cleanup_session(worker_id)
    
    @staticmethod
    def has_worker_mcp(worker_id: str) -> bool:
        """Check if a Worker has an active MCP session."""
        return worker_mcp_manager.get_session(worker_id) is not None


# Singleton
worker_mcp_integration = WorkerMcpIntegration()
