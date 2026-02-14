import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm.factory import LLMFactory
from app.i18n.service import i18n

logger = logging.getLogger(__name__)

META_OPTIMIZER_PROMPT = """
You are an Expert Prompt Engineer and Coach for AI Agents.
Your goal is to IMPROVE an Agent's System Prompt based on a reported failure or feedback.

## Inputs
1. **Current System Prompt**: The instructions the agent was following.
2. **Context/Trace**: A summary of what the agent did (and failed at).
3. **Feedback/Error**: What went wrong or what the user complained about.

## Your Task
1. Analyze the root cause. Did the agent misunderstand? Did it ignore a rule? Did it lack a rule?
2. Rewrite the System Prompt to strictly prevent this specific failure in the future.
3. **Constraint**: Keep the prompt concise. Do not remove essential existing instructions unless they conflict. Add a specific "Rule" or "Constraint".

## Output
Return ONLY the new System Prompt text. Do not wrap in markdown blocks if not necessary (just the text).
"""


class PromptOptimizer:

    async def optimize(self, current_prompt: str, trace_summary: str, feedback: str, thread_id: str = None) -> str:
        """
        Reflects on the failure and returns a better prompt.
        """
        try:
            llm = LLMFactory.create_llm(temperature=0.0)

            user_content = f"""
## Current Prompt
{current_prompt}

## Execution Pattern (Trace)
{trace_summary}

## Feedback (The Failure)
{feedback}

Please optimize the prompt to fix this.
"""
            messages = [
                SystemMessage(content=META_OPTIMIZER_PROMPT),
                HumanMessage(content=user_content),
            ]

            response = await llm.ainvoke(messages, config={"callbacks": []})
            new_prompt = response.content.strip()

            # Basic cleanup
            if new_prompt.startswith("```"):
                lines = new_prompt.splitlines()
                # Remove first and last lines if they are fences
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                new_prompt = "\n".join(lines).strip()

            logger.info(f"Optimized prompt based on feedback: {feedback}")

            # Phase 6: Transparent Thought
            if thread_id:
                try:
                    from app.core.monitoring.activity import activity_monitor

                    await activity_monitor.update_agent_state(
                        thread_id=thread_id,
                        mode="LEARNING",
                        task_name=i18n.get("prompts.optimizer.task_name"),
                        task_status=i18n.get("prompts.optimizer.status_correction"),
                        details={
                            "type": "thought",
                            "thought_type": "optimization",
                            "original_length": len(current_prompt),
                            "new_length": len(new_prompt),
                            "feedback": feedback,
                        },
                    )
                except Exception:
                    pass

            return new_prompt

        except Exception as e:
            logger.error(f"Prompt optimization failed: {e}")
            return current_prompt  # Fallback
