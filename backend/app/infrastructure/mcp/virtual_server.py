import logging
import json
from typing import Any, Dict, List, Optional, Type 

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, create_model

from app.core.learning.skill_executor import SkillExecutor
from app.models.learning import LearnedSkill
from app.infrastructure.database.sql.database import session_scope
from sqlalchemy import select

logger = logging.getLogger(__name__)


class VisualSkillServer:
    """
    Virtual MCP Server that exposes EvoLoop's LearnedSkills as standard MCP Tools.
    This allows external clients (like Claude Desktop) to discover and execute
    skills created within EvoLoop.
    """

    def __init__(self, mcp_server: FastMCP):
        self.mcp = mcp_server
        self.executor = SkillExecutor()

    async def sync_skills(self):
        """
        Fetch all 'verified' skills and register them as tools.
        This should be called during server startup.
        """
        try:
            async with session_scope() as session:
                # Only expose verified skills to external consumers to ensure reliability
                stmt = select(LearnedSkill).where(LearnedSkill.status == "verified")
                result = await session.execute(stmt)
                skills = result.scalars().all()
                
            logger.info(f"Syncing {len(skills)} verified skills to MCP server")
            
            for skill in skills:
                self._register_skill(skill)
                
        except Exception as e:
            logger.error(f"Failed to sync skills to MCP: {e}")

    def _register_skill(self, skill: LearnedSkill):
        """
        Dynamically create a Pydantic model and register a tool handler for the skill.
        """
        try:
            # 1. Parse Parameters to build Pydantic Model fields
            # skill.parameters is stored as a JSON string list of dicts
            params_list = []
            if isinstance(skill.parameters, str):
                params_list = json.loads(skill.parameters)
            elif isinstance(skill.parameters, list):
                params_list = skill.parameters
            
            field_definitions = {}
            for param in params_list:
                # Handle SkillParameter object or dict
                p_name = getattr(param, "name", None) or param.get("name")
                p_desc = getattr(param, "description", None) or param.get("description", "")
                p_type = getattr(param, "type", None) or param.get("type", "string")
                p_req = getattr(param, "required", None) or param.get("required", True)
                
                # Map type string to Python type
                py_type = str
                if p_type == "number":
                    py_type = float
                elif p_type == "integer":
                    py_type = int
                elif p_type == "boolean":
                    py_type = bool
                
                # Create field definition: (type, Field(...))
                if p_req:
                    field_definitions[p_name] = (py_type, Field(..., description=p_desc))
                else:
                    field_definitions[p_name] = (Optional[py_type], Field(None, description=p_desc))

            # Create dynamic Pydantic model
            # Model name needs to be valid Python identifier, sanitize skill name
            safe_name = "".join(x for x in skill.name.title() if x.isalnum()) + "Args"
            DynamicArgsModel = create_model(safe_name, **field_definitions)

            # 2. Define the execution handler
            # We must bind the specific skill_id to the function
            async def skill_handler(ctx=None, **kwargs) -> str:
                """
                Dynamic handler for skill execution.
                """
                logger.info(f"Executing MCP Skill: {skill.name} (ID: {skill.id})")
                try:
                    # Execute using EvoLoop's SkillExecutor
                    success, result = await self.executor.execute_skill(
                        skill_id=skill.id,
                        params=kwargs,
                        tool_registry={} # Tools are loaded internally by executor
                    )
                    
                    if success:
                        return f"Skill '{skill.name}' executed successfully.\nResult: {result}"
                    else:
                        return f"Skill '{skill.name}' failed.\nError: {result}"
                        
                except Exception as e:
                    return f"System Error executing skill: {str(e)}"

            # 3. Register with FastMCP
            # We manually update the metadata to match the skill
            skill_handler.__name__ = skill.name
            skill_handler.__doc__ = skill.description or f"Execute the '{skill.name}' skill."
            
            # Use the tool decorator but apply it manually
            # FastMCP tool decorator typically inspects the signature.
            # By passing the DynamicArgsModel as the type hint for the first arg (or kwargs), 
            # we hope FastMCP picks it up. 
            # Note: FastMCP usually relies on Type Hints of the function arguments.
            # So we need to construct a function with the correct signature dynamically or use `mcp.add_tool` if available.
            
            # Since generating dynamic signatures in Python is tricky, we might rely on 
            # FastMCP's inability to see dynamic models if we don't supply them explicitly.
            # Let's try to overwrite the annotations.
            skill_handler.__annotations__ = {name: typ for name, (typ, _) in field_definitions.items()}
            skill_handler.__annotations__["return"] = str

            self.mcp.tool(name=skill.name, description=skill.description)(skill_handler)
            logger.debug(f"Registered MCP tool: {skill.name}")

        except Exception as e:
            logger.error(f"Error registering skill {skill.name}: {e}")
