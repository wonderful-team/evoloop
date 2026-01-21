"""
Intent Classifier - Semantic routing using LLM.

Replaced heavy local 'adaptive-classifier' with lightweight LLM routing
to avoid huge dependency footprint and network timeouts.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


class IntentClassifier:
    """
    Semantic intent classifier using LLM.

    Features:
    1. Zero-shot / Few-shot Classification via LLM
    2. No local heavy dependencies (torch/transformers removed)
    3. Uses existing LLM config
    """

    # Definition of Intents and Examples for Few-Shot Prompting
    INTENTS = {
        "chat": "General conversation, greetings, small talk, or gratitude.",
        "browser_executor": "Requests to open URLs, search engines, or browse the web.",
        "computer_executor": "Desktop automation: clicking, typing, screenshots, opening local apps.",
        "mobile_executor": "Mobile device automation: swiping, tapping, installing apps.",
        "documenter": "Writing documentation, wikis, READMEs, or explaining project structure.",
        "coder": "Writing code for FINALIZED plans, performing specific refactors, or fixing simple bugs.",
        "deep_researcher": "Deep research, market analysis, learning about concepts.",
        "planner": "Planning system architecture, database design, or task breakdown.",
    }

    # Minimum confidence is less relevant for LLM generation unless we ask for probability,
    # but we can implement a "None" fallback if LLM is unsure.

    @classmethod
    async def classify(cls, message: str) -> str | None:
        """
        Classify user message and return target node.
        """
        if not message or len(message.strip()) < 2:
            return None

        try:
            llm = LLMFactory.create_llm(temperature=0.0)  # Determinstic

            # Construct Prompt
            intent_descriptions = "\n".join([f"- {k}: {v}" for k, v in cls.INTENTS.items()])

            system_prompt = f"""You are a Semantic Intent Router.
Classify the user's input into exactly ONE of the following categories:

{intent_descriptions}

Rules:
1. Output ONLY the Category Name (e.g., 'coder').
2. If the input matches NONE of the strict categories or is ambiguous, output 'None'.
3. 'chat' should catch generic greetings like 'hi', 'hello'.
"""

            response = await llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=message)
            ], config={"callbacks": []})

            predicted_label = response.content.strip().replace("'", "").replace('"', "")

            if predicted_label in cls.INTENTS:
                logger.info(f"[IntentClassifier] Routable Intent: '{predicted_label}'")
                return predicted_label

            logger.debug(f"[IntentClassifier] classification returned '{predicted_label}' (Not in schema), fallback.")
            return None

        except Exception as e:
            logger.error(f"[IntentClassifier] LLM Classification failed: {e}")
            return None

    @classmethod
    def update(cls, text: str, label: str):
        """
        Runtime updates not supported in prompt-based Lite version yet.
        (Could be implemented by appending to a dynamic few-shot list in Memory)
        """
        logger.warning("[IntentClassifier] 'update' called but LLM router is stateless.")
        pass
