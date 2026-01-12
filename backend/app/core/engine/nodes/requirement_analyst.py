import logging

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory

logger = logging.getLogger(__name__)

class RequirementAnalystNode:
    """
    Adapts DeepCode's RequirementAnalysisAgent for EvoLoop.
    
    Responsibilities:
    1. Analyze partial user requests.
    2. Generate structured guiding questions (5-8 max).
    3. Summarize answers into a Formal Requirement Document.
    """

    @staticmethod
    async def node(state: AgentState, config: RunnableConfig):
        """
        Main entry point for the node.
        Decides mode based on conversation history.
        """
        llm = LLMFactory.create_llm(temperature=0.3)
        messages = state.get("messages", [])

        # 1. Determine Phase
        # Heuristic:
        # - If last message was AI asking questions -> Phase: SUMMARIZE
        # - If last message was AI showing Req Doc -> Phase: MODIFY (or Supervisor handles)
        # - Else -> Phase: GENERATE_QUESTIONS

        # We need to look at what the AI said previously.
        # But wait, Supervisor routes here.
        # If Supervisor routed here, it implies we need analysis.

        last_ai_msg = None
        for m in reversed(messages):
            if isinstance(m, AIMessage):
                last_ai_msg = m
                break

        # Phase Detection
        phase = "GENERATE_QUESTIONS"
        if last_ai_msg and "Guiding Questions" in (last_ai_msg.content or ""):
            phase = "SUMMARIZE"
        elif last_ai_msg and "## Functional Requirements" in (last_ai_msg.content or ""):
            phase = "MODIFY"

        logger.info(f"Requirement Analyst Phase: {phase}")

        if phase == "GENERATE_QUESTIONS":
            return await RequirementAnalystNode._generate_questions(state, llm)
        elif phase == "SUMMARIZE":
            return await RequirementAnalystNode._summarize_requirements(state, llm)
        elif phase == "MODIFY":
            return await RequirementAnalystNode._modify_requirements(state, llm)

        return {"messages": [AIMessage(content="Error: Unknown Requirement Phase")]}

    @staticmethod
    async def _generate_questions(state: AgentState, llm):
        messages = state.get("messages", [])
        last_human_msg = messages[-1].content if messages else "No input"

        from app.core.prompts.requirement_analyst_builder import (
            RequirementAnalystPromptBuilder,
        )
        prompt = RequirementAnalystPromptBuilder.build_question_generator_prompt(last_human_msg)

        response = await llm.ainvoke([HumanMessage(content=prompt)])

        if "REQUIREMENTS_CLEAR" in response.content:
             # Identify that we can skip to planning
             # We return a special signal or just a message saying "Ready"
             return {
                 "messages": [AIMessage(content="Requirements are clear. Proceeding to Planning.")],
                 "next_node": "planner" # Optional fast track if graph supports dynamic next
             }

        # Add metadata title
        response.content = f"### 🧐 Requirement Clarification\n\n{response.content}"
        return {"messages": [response]}

    @staticmethod
    async def _summarize_requirements(state: AgentState, llm):
        # We have questions and answers in history.
        # We need to consolidate them.

        # Extract context (simplify for token efficiency)
        # We take the last 10 messages
        history = state.get("messages", [])[-10:]
        history_text = "\n".join([f"{m.type.upper()}: {m.content}" for m in history])

        from app.core.prompts.requirement_analyst_builder import (
            RequirementAnalystPromptBuilder,
        )
        prompt = RequirementAnalystPromptBuilder.build_summarizer_prompt(history_text)

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return {"messages": [response]}

    @staticmethod
    async def _modify_requirements(state: AgentState, llm):
        # User wants changes to the existing doc
        history = state.get("messages", [])[-6:] # Last few messages
        history_text = "\n".join([f"{m.type.upper()}: {m.content}" for m in history])

        from app.core.prompts.requirement_analyst_builder import (
            RequirementAnalystPromptBuilder,
        )
        prompt = RequirementAnalystPromptBuilder.build_modifier_prompt(history_text)

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return {"messages": [response]}

# Export as runnable
requirement_analyst_node = RequirementAnalystNode.node
