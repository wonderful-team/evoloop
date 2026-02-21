import logging
from langchain_core.runnables import RunnableConfig

from app.core.engine import AgentEngine, AgentState
from app.core.engine.prompts import DocumenterPromptBuilder
from app.core.tools.registry import get_node_tools

logger = logging.getLogger(__name__)


async def documenter_node(state: AgentState, config: RunnableConfig):
    """
    Information Architect Agent:
    Proactively manages project documentation (Filesystem & Wiki) and knowledge harvesting.
    """
    project_id = state.get("project_id", 1)
    
    # 1. Retrieve Skills (Knowledge Injection)
    skills = []
    try:
        from app.core.learning.discovery import skill_discovery
        scratchpad = state.get("scratchpad", {})
        topic = scratchpad.get("route_reason") or "documentation"
        skills = await skill_discovery.retrieve(topic, top_k=2)
    except Exception as e:
        logger.warning(f"[Documenter] Skill retrieval failed: {e}")

    # 2. Build Agent System Prompt
    system_prompt = DocumenterPromptBuilder.build_architect_system_prompt(
        project_id=project_id, 
        skills=skills
    )

    # 3. Define Toolset (Declarative from YAML)
    tools = get_node_tools("documenter")

    # 4. Run Agent Engine ReAct Loop
    logger.info(f"Nodes: Documenter - Starting Information Architect loop for project {project_id}")
    return await AgentEngine.run_node(
        state=state,
        config=config,
        system_prompt=system_prompt,
        tools=tools,
        name="Information Architect",
        max_steps=8,  # Allow more steps for complex documentation tasks
    )
