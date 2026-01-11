from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from app.core.workflows.state import AgentState
from app.core.llm.factory import LLMFactory
from app.logging import logger
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models.learning import TraceEvent
from sqlalchemy import select, func, text
import json

from datetime import datetime, timedelta, timezone

logger = logger.getChild("system_scanner")

async def system_scanner_node(state: AgentState, config: RunnableConfig):
    """
    System Scanner Node: The 'Doctor' that diagnoses system health.
    Analyzes Trace Memory for recurrent failures.
    """
    # 0. Check if Evolution is Enabled
    from app.domain.system.evolution_config import EvolutionConfigService
    if not EvolutionConfigService.is_enabled():
        return {
            "messages": [],
            "next_node": "finish" # Or END
        }

    logger.info("🏥 System Scanner: Starting Health Check...")

    # 1. Scan Trace Memory for Failures
    # We look for 'finish' nodes where action_payload might identify strict failure?
    # Or 'MetaReviewer' interventions?
    # Let's count Meta-Reviewer interventions as a strong signal of failure.
    
    health_report = []
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=1)
    
    async with session_scope() as session:
        # Count Meta-Reviewer interventions in last 24h
        stmt = (
            select(func.count(TraceEvent.id))
            .where(TraceEvent.node_name == "meta_reviewer")
            .where(TraceEvent.created_at > cutoff_time)
        )
        result = await session.execute(stmt)
        intervention_count = result.scalar()
        
        if intervention_count > 0:
            health_report.append(f"⚠️ High Failure Rate: Meta-Reviewer intervened {intervention_count} times in the last 24h.")
            
        # TODO: More sophisticated pattern matching using Graph Memory
        # e.g., "Find episodes where result='Failed' group by goal"
        
    # 2. Analyze Report
    if not health_report:
        return {
            "messages": [AIMessage(content="✅ System Healthy. No evolutionary pressure detected.")],
            "next_node": "finish" # Or specific end for evolution graph
        }
        
    report_text = "\n".join(health_report)
    
    # 3. Create Evolution Plan Proposal
    # We ask an LLM to propose a focus area based on the report
    llm = LLMFactory.create_llm(temperature=0.2)
    
    prompt = f"""You are the System Scanner (Medical Diagnostic AI).
    
    Health Report:
    {report_text}
    
    Your Task:
    1. Identify the most critical issue.
    2. Formulate a specific "Evolution Objective" for the Architect.
    
    Output Format:
    Evolution Objective: [One sentence description]
    Severity: [Low/Medium/High/Critical]
    """
    
    response = await llm.ainvoke([SystemMessage(content=prompt)])
    
    return {
        "messages": [AIMessage(content=f"🩺 Health Scan Complete.\n\n{response.content}")],
        "evolution_report": response.content,
        "next_node": "evolution_planner" # Signal to proceed
    }
