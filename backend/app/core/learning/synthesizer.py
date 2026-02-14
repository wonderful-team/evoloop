import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from app.core.llm.factory import LLMFactory
from app.core.system import SystemConfigService
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.models import TraceEvent

logger = logging.getLogger(__name__)

META_ARCHITECT_PROMPT = """
You are the "Meta-Architect" for the EvoLoop Agent System.
Your goal is to practice "Imitation Learning": Analyze a trace of human-agent interaction and synthesize a reusable Agent Configuration (YAML) that can perform the same task autonomously.

## Input: Execution Trace
You will receive a chronological list of events containing:
- State Snapshots (what the agent knew)
- Actions (Tools called, inputs provided)
- Interventions (User corrections)

## Output: Agent YAML
Generate a YAML configuration for a `GenericLLMNode` that encapsulates this behavior.
Schema:
```yaml
nodes:
  - id: "learned_agent"
    path: "app.core.engine.nodes.generic.GenericLLMNode"
    config:
      system_prompt: |
        [Synthesized Role and Instructions based on what was done]
      tools:
        - [List of tools used in the trace]
```

## Rules
1. **Deduce Intent**: Look at the *outcome* of the trace. What was strictly necessary?
2. **Generalize**: If the user searched for "error in auth.py", the prompt should be "Search for errors in the specified file", not hardcoded to "auth.py".
3. **Tool Selection**: Only include tools that were actually used or clearly needed.
4. **Valid YAML**: Output ONLY valid YAML code block.
"""


class WorkflowSynthesizer:
    def __init__(self, thread_id: str):
        self.thread_id = thread_id

    async def synthesize(self) -> str:
        """
        Main entry point: Fetches trace -> Calls LLM -> Returns YAML string.
        """
        trace_text = await self._fetch_and_format_trace()
        if not trace_text:
            return "# No trace data found."

        yaml_config = await self._generate_yaml(trace_text)
        return yaml_config

    async def _fetch_and_format_trace(self) -> str | None:
        async with session_scope() as session:
            stmt = select(TraceEvent).where(TraceEvent.thread_id == self.thread_id).order_by(TraceEvent.step_number)
            result = await session.execute(stmt)
            events = result.scalars().all()

            if not events:
                return None

            # Format as Narrative
            narrative = []
            for ev in events:
                step_desc = f"Step {ev.step_number} [{ev.action_type}] ({ev.node_name}):\n"

                # Payload
                try:
                    payload = json.loads(ev.action_payload)
                    if ev.action_type == "tool_call":
                        step_desc += f"  Reference Tool: {payload.get('name')}\n"
                        step_desc += f"  Args: {payload.get('args')}\n"
                    elif ev.action_type == "llm_output":
                        step_desc += f"  Thought: {payload.get('content')}\n"
                except Exception:
                    step_desc += f"  Raw: {ev.action_payload}\n"

                narrative.append(step_desc)

            return "\n".join(narrative)

    async def _generate_yaml(self, trace_text: str) -> str:
        # Get LLM (Use smart model for synthesis)
        llm = LLMFactory.create_llm(temperature=0.0)

        user_lang = SystemConfigService.get_language_preference()
        sys_prompt = META_ARCHITECT_PROMPT + i18n.get("prompts.learning.synthesis_lang_constraint", lang=user_lang)

        messages = [
            SystemMessage(content=sys_prompt),
            HumanMessage(
                content=i18n.get("prompts.domain_tools.learning.synthesis.instruction", trace_text=trace_text)
            ),
        ]

        response = await llm.ainvoke(messages)
        content = response.content

        # Strip markdown fences if present
        if "```yaml" in content:
            content = content.split("```yaml")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return content
