from langchain_core.prompts import ChatPromptTemplate

# To avoid circular import, we might need to redefine RoutingDecision or pass Pydantic object
# Better to define the Pydantic model here or in a shared schema file.
# For now, let's assume we pass the format instructions as a string.

class SupervisorPromptBuilder:
    @staticmethod
    def build_routing_prompt(format_instructions: str) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", """You are the Supervisor. Decide the next step.
            
            Options:
            - "requirement_analyst": IF the user's request is AMBIGUOUS or VAGUE.
            - "planner": If requirements are clear but complex.
            - "coder": If you have a plan and need to write code.
            - "deep_researcher": If you need to search or investigate.
            - "documenter": For documentation, WIKI, or README tasks.
            - "finish": If the user's request is fully satisfied.
            
            CRITICAL: If the LAST AI message contains a direct answer, choose "finish".
            
            Specific Rules:
            - "Build a blog" -> requirement_analyst
            - "Implement", "Write code", "Fix this" -> coder
            - "Plan verified. Ready for Coder" -> coder
            - "Need more research" -> deep_researcher
            - "Generate Wiki" -> documenter
            
            {format_instructions}
            
            system_info: {system_info}
            """),
            ("placeholder", "{messages}"),
            ("system", "Analyze the conversation. Output ONLY the JSON object."),
        ])
