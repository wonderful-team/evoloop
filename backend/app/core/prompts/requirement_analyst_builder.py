from app.domain.system.service import SystemConfigService


class RequirementAnalystPromptBuilder:

    @staticmethod
    def _get_lang_instruction() -> str:
        user_lang = SystemConfigService.get_language_preference()
        return f"\nIMPORTANT: Respond in {user_lang}."

    @staticmethod
    def build_question_generator_prompt(user_request: str) -> str:
        return f"""Based on the user's initial request, generate 3-5 critical NEW questions to clarify the Requirements.
        
        User Request: {user_request}
        
        Focus on:
        1. Functional Scope (What exactly to build?)
        2. Technical Constraints (Stack, Performance?)
        3. User Experience (UI/Workflow?)
        
        Output format:
        Return a polite message starting with "To ensure I build exactly what you need, I have a few clarifying questions:"
        followed by the numbered list of questions.
        If the request is already very detailed, just reply "REQUIREMENTS_CLEAR" (and nothing else).

        {RequirementAnalystPromptBuilder._get_lang_instruction()}
        """

    @staticmethod
    def build_summarizer_prompt(history_text: str) -> str:
        return f"""You are a professional Technical Business Analyst.
        
        Based on the conversation history below, compile a formal **Requirement Specification Document**.
        
        Conversation:
        {history_text}
        
        Output strictly in Markdown:
        
        # Project Requirements Document (PRD)
        
        ## 1. Overview
        (Brief summary)
        
        ## 2. Functional Requirements
        - ...
        
        ## 3. Technical Constraints
        - ...
        
        ## 4. UI/UX Flow
        - ...
        
        IMPORTANT: This document will be used by the Architect to build the system. Be precise.
        {RequirementAnalystPromptBuilder._get_lang_instruction()}
        """

    @staticmethod
    def build_modifier_prompt(history_text: str) -> str:
        return f"""The user wants to modify the previous Requirement Document.
        
        Context:
        {history_text}
        
        Task:
        Regenerate the FULL Requirement Specification Document with the requested changes applied.
        Maintain the same format (Overview, Functional, Technical...).
        {RequirementAnalystPromptBuilder._get_lang_instruction()}
        """
