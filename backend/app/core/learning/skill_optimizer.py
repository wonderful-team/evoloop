import logging
import json
from typing import List, Dict, Any, Optional
from app.models.learning import LearnedSkill, TraceEvent
from app.core.llm.factory import LLMFactory
from app.infrastructure.database.sql.database import session_scope
from sqlalchemy import select, and_
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

OPTIMIZATION_PROMPT = """
You are a "Skill Optimization Expert". Your goal is to refine the natural language instructions for an AI Skill based on its actual execution performance.

## Skill Context
Name: {name}
Current Instructions:
```markdown
{current_instructions}
```

## Execution Data (Historical Traces)
Below are narratives from historical runs, including both successes and failures.
{trace_narratives}

## Your Task
Analyze why the skill might be failing or where it is inefficient. 
1. Identify ambiguous instructions that led the Agent astray.
2. Suggest new instructions to handle edge cases discoverd in the traces.
3. Remove redundant or outdated guidance.

Return ONLY the refined Markdown content for the SKILL.md body. Do NOT include frontmatter or explanations.
"""

class SkillOptimizer:
    """
    Optimizes skill instructions using LLM analysis of execution history.
    """
    
    @classmethod
    async def optimize_skill(cls, skill_id: int) -> Dict[str, Any]:
        """
        Analyze traces for a skill and suggest instruction refinements.
        """
        async with session_scope() as db:
            # 1. Fetch skill
            stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
            skill = (await db.execute(stmt)).scalar_one_or_none()
            
            if not skill:
                return {"success": False, "error": "Skill not found"}
            
            # 2. Fetch associated traces
            # We look for traces that match the skill name in their context or were explicitly linked
            # For now, we'll fetch the most recent traces for the thread where this skill was used
            # Improved logic: SkillExecutor should tag traces with skill_id in the future.
            # For this MVP, we fetch traces related to the skill's name in nodes or specific sessions.
            trace_stmt = select(TraceEvent).where(
                TraceEvent.action_payload.like(f"%{skill.name}%")
            ).limit(20)
            traces = (await db.execute(trace_stmt)).scalars().all()
            
            if not traces:
                return {"success": False, "error": "No execution traces found for optimization"}
            
            # 3. Build trace narratives for LLM
            trace_narratives = cls._prepare_trace_narratives(list(traces))
            
            # 4. Call LLM for optimization
            llm = LLMFactory.create_llm()
            sys_msg = SystemMessage(content="You are a senior AI engineer specializing in agentic workflows.")
            hum_raw = OPTIMIZATION_PROMPT.format(
                name=skill.name,
                current_instructions=skill.instructions or "No instructions available.",
                trace_narratives=trace_narratives
            )
            hum_msg = HumanMessage(content=hum_raw)
            
            try:
                res = await llm.ainvoke([sys_msg, hum_msg])
                optimized_instructions = res.content.strip()
                
                return {
                    "success": True,
                    "original": skill.instructions,
                    "optimized": optimized_instructions,
                    "trace_count": len(traces)
                }
            except Exception as e:
                logger.error(f"Optimization failed: {e}")
                return {"success": False, "error": str(e)}

    @staticmethod
    def _prepare_trace_narratives(traces: List[TraceEvent]) -> str:
        narratives = []
        for i, t in enumerate(traces):
            try:
                payload = json.loads(t.action_payload) if isinstance(t.action_payload, str) else t.action_payload
                status = "SUCCESS" if t.reward and t.reward > 0 else "FAILED/NEUTRAL"
                narratives.append(f"Run {i+1} ({status}):\nNode: {t.node_name}\nAction: {t.action_type}\nPayload: {str(payload)[:200]}...")
            except:
                continue
        return "\n---\n".join(narratives)
