import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.tools.registry import get_all_tools
from app.domain.research.generator import ReportGenerator

logger = logging.getLogger(__name__)


class DeepResearchEngine:
    """
    Engine that executes the Deep Research loop (Plan -> Iterate -> Conclude).
    Adapted from DeepWiki's logic.
    """

    TOOLS_LOOP_LIMIT = 5

    def __init__(self, llm: BaseChatModel, tools: list = None):
        self.llm = llm
        self.tools = tools

    async def run(
        self,
        topic: str,
        previous_history: list = None,
        max_iterations: int = settings.RESEARCH_MAX_ITERATIONS,
        config: RunnableConfig = None,
    ) -> str:
        """
        Run the full Deep Research process on a topic.

        Args:
            topic: The research topic/query.
            previous_history: List of prior messages in the conversation.
            max_iterations: Maximum number of research iterations.

        Returns:
            The final conclusion content (Markdown).
        """
        logs = []
        # Create a short topic identifier for logs (e.g. "Community Plugin...")
        topic_short = (topic[:30] + "..") if len(topic) > 30 else topic
        log_prefix = f"[{topic_short}]"

        logger.info(f"{log_prefix} Starting Deep Research Engine.")

        # 1. Plan Phase
        logger.info(f"{log_prefix} Phase 1: Planning")

        # Construct the planning prompt using Builder
        from app.core.engine.prompts import DeepResearchPromptBuilder

        # Context Formatting
        context_str = ""
        if previous_history:
            # Filter for vital info
            relevant_msgs = [m for m in previous_history if isinstance(m, HumanMessage | AIMessage | ToolMessage)]
            relevant_msgs = relevant_msgs[-10:]  # Limit to last 10 messages

            history_text = "\n".join([f"{m.type}: {str(m.content)[:500]}" for m in relevant_msgs])
            context_str = f"\n\nCONTEXT FROM PREVIOUS TURN:\n{history_text}\n"

        # Build prompt with language injection handled internally
        system_content = DeepResearchPromptBuilder.build_plan_prompt(context_str)

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=f"User Query: {topic}"),
        ]

        response = await self.llm.ainvoke(messages, config=config)
        logs.append(f"### Iteration 1: Plan\n{response.content}")

        # Log plan summary
        logger.info(f"{log_prefix} Plan Generated: {response.content[:200].replace(chr(10), ' ')}...")

        # 2. Iteration Phase
        current_iteration = 1

        # Get Tools
        tools = self.tools if self.tools else get_all_tools()
        llm_with_tools = self.llm.bind_tools(tools)
        tool_map = {t.name: t for t in tools}

        # Track executed tools in this run
        run_tool_history = set()

        while current_iteration < max_iterations:
            current_iteration += 1
            logger.info(f"{log_prefix} Phase 2: Iteration {current_iteration}")

            # Prepare Update Prompt using Builder
            current_logs_str = "\n\n".join(logs)

            update_system_content = DeepResearchPromptBuilder.build_update_prompt(iteration=current_iteration)
            update_user_content = f"Topic: {topic}\n\nPrevious Research:\n{current_logs_str}\n\nPlease proceed with Iteration {current_iteration}."

            # Inner ReAct Loop
            step_messages = [
                SystemMessage(content=update_system_content),
                HumanMessage(content=update_user_content),
            ]

            step_content = ""

            # Run tool loop
            for _ in range(self.TOOLS_LOOP_LIMIT):
                ai_msg = await llm_with_tools.ainvoke(step_messages, config=config)
                step_messages.append(ai_msg)

                if not ai_msg.tool_calls:
                    step_content = ai_msg.content
                    break

                for tool_call in ai_msg.tool_calls:
                    tool_name = tool_call["name"]
                    args = tool_call["args"]
                    tool_id = tool_call["id"]

                    # Promote tool usage to INFO for visibility
                    # Compact args for logging
                    args_str = str(args)[:100] + "..." if len(str(args)) > 100 else str(args)
                    logger.info(f"{log_prefix} Tool Call: {tool_name}({args_str})")

                    # Deduplication Check
                    try:
                        tool_sig = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
                    except Exception:
                        tool_sig = f"{tool_name}:{str(args)}"

                    if tool_sig in run_tool_history:
                        result = f"⚠️ SYSTEM ALERT: You have ALREADY executed `{tool_name}` with these exact arguments in a previous step. Do not repeat actions. Review your previous steps or summaries. Proceed to new inquiries."
                        logger.warning(f"{log_prefix} Prevented duplicate tool call: {tool_name}")
                    else:
                        run_tool_history.add(tool_sig)
                        tool = tool_map.get(tool_name)
                        result = "Tool not found"
                        if tool:
                            try:
                                result = await tool.ainvoke(args, config=config)
                            except Exception as e:
                                result = f"Error: {e}"

                    # Truncate result for context window
                    result_str = str(result)

                    # Log result summary
                    res_log = (
                        result_str[:100].replace("\n", " ") + "..."
                        if len(result_str) > 100
                        else result_str.replace("\n", " ")
                    )
                    logger.info(f"{log_prefix} Tool Output: {res_log}")

                    if len(result_str) > 5000:
                        result_str = result_str[:5000] + "...(truncated)"

                    step_messages.append(ToolMessage(content=result_str, tool_call_id=tool_id))

            if not step_content:
                step_content = "(No summary provided by agent)"

            logs.append(f"### Iteration {current_iteration}: Update\n{step_content}")
            logger.info(f"{log_prefix} Iteration Summary: {step_content[:200].replace(chr(10), ' ')}...")

            # Heuristic check for completion
            if "Final Conclusion" in step_content or "ready to conclude" in step_content.lower():
                logger.info(f"{log_prefix} Agent indicated readiness to conclude.")
                break

        # 3. Conclusion Phase
        logger.info(f"{log_prefix} Phase 3: Conclusion")
        current_logs_str = "\n\n".join(logs)

        conclusion_user_content = f"Topic: {topic}\n\nAll Findings:\n{current_logs_str}\n\nPlease provide the detailed Final Conclusion."

        system_content = DeepResearchPromptBuilder.build_conclusion_prompt()

        final_messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=conclusion_user_content),
        ]

        final_response = await self.llm.ainvoke(final_messages, config=config)
        logger.info(f"{log_prefix} Research Completed.")

        # Generate Structured Report
        final_report = ReportGenerator.generate_report(
            topic=topic,
            conclusion=final_response.content,
            logs=logs,
            metadata={"Iterations": max_iterations},
        )

        return final_report
