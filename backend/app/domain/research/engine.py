import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.prompts.deep_research import RESEARCH_PLAN_PROMPT, RESEARCH_UPDATE_PROMPT, RESEARCH_CONCLUSION_PROMPT
from app.domain.tools.registry import get_all_tools

logger = logging.getLogger(__name__)


class DeepResearchEngine:
    """
    Engine that executes the Deep Research loop (Plan -> Iterate -> Conclude).
    Adapted from DeepWiki's logic.
    """

    TOOLS_LOOP_LIMIT = 5

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self._init_prompts()

    def _init_prompts(self):
        """Initialize PromptTemplates."""
        # Clean placeholders: Ensure prompts are format-ready
        self.plan_prompt_template = PromptTemplate.from_template(RESEARCH_PLAN_PROMPT)
        # Note: RESEARCH_UPDATE_PROMPT expects {iteration}
        self.update_prompt_template = PromptTemplate.from_template(RESEARCH_UPDATE_PROMPT)
        self.conclusion_prompt_template = PromptTemplate.from_template(RESEARCH_CONCLUSION_PROMPT)

    async def run(self, topic: str, max_iterations: int = settings.RESEARCH_MAX_ITERATIONS, config: RunnableConfig = None) -> str:
        """
        Run the full Deep Research process on a topic.
        
        Args:
            topic: The research topic/query.
            max_iterations: Maximum number of research iterations.
        
        Returns:
            The final conclusion content (Markdown).
        """
        logs = []
        # Create a short topic identifier for logs (e.g. "Community Plugin...")
        topic_short = (topic[:30] + '..') if len(topic) > 30 else topic
        log_prefix = f"[{topic_short}]"
        
        logger.info(f"{log_prefix} Starting Deep Research Engine.")

        # 1. Plan Phase
        logger.info(f"{log_prefix} Phase 1: Planning")

        # Construct the planning prompt
        # We inject the topic directly. If prompts have placeholders, use format.
        
        # Language Injection
        from app.domain.system.service import SystemConfigService
        user_lang = SystemConfigService.get_language_preference()
        lang_msg = SystemMessage(content=f"LANGUAGE PROTOCOL (STRICT):\nUser Language: {user_lang}\nYou MUST write your plans, updates, and conclusions in {user_lang}.")

        messages = [
            lang_msg,
            SystemMessage(content=RESEARCH_PLAN_PROMPT),
            HumanMessage(content=f"User Query: {topic}")
        ]

        response = await self.llm.ainvoke(messages, config=config)
        logs.append(f"### Iteration 1: Plan\n{response.content}")
        
        # Log plan summary
        logger.info(f"{log_prefix} Plan Generated: {response.content[:200].replace(chr(10), ' ')}...")

        # 2. Iteration Phase
        current_iteration = 1

        # Get Tools
        tools = get_all_tools()
        llm_with_tools = self.llm.bind_tools(tools)
        tool_map = {t.name: t for t in tools}

        while current_iteration < max_iterations:
            current_iteration += 1
            logger.info(f"{log_prefix} Phase 2: Iteration {current_iteration}")

            # Prepare Update Prompt
            current_logs_str = "\n\n".join(logs)

            try:
                # Try formatting if the prompt has placeholders
                update_system_content = self.update_prompt_template.format(iteration=current_iteration)
            except KeyError:
                # Fallback if no placeholder
                update_system_content = RESEARCH_UPDATE_PROMPT

            update_user_content = f"Topic: {topic}\n\nPrevious Research:\n{current_logs_str}\n\nPlease proceed with Iteration {current_iteration}."

            # Inner ReAct Loop
            step_messages = [
                lang_msg,
                SystemMessage(content=update_system_content),
                HumanMessage(content=update_user_content)
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
                    res_log = result_str[:100].replace('\n', ' ') + "..." if len(result_str) > 100 else result_str.replace('\n', ' ')
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

        final_messages = [
            lang_msg,
            SystemMessage(content=RESEARCH_CONCLUSION_PROMPT),
            HumanMessage(content=conclusion_user_content)
        ]

        final_response = await self.llm.ainvoke(final_messages, config=config)
        logger.info(f"{log_prefix} Research Completed.")

        return final_response.content
