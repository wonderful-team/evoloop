from typing import Literal

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.llm.factory import LLMFactory
from app.core.monitoring.activity import activity_monitor


class IntentionOutput(BaseModel):
    intent: Literal["browser", "computer", "mobile", "chat", "general"] = Field(
        description="The determined intent of the user. 'browser' for web tasks, 'computer' for OS/desktop tasks, 'mobile' for phone tasks, 'chat' for casual conversation/greetings, 'general' for questions/coding."
    )
    reasoning: str = Field(description="Brief reasoning for the classification.")
    refined_instruction: str = Field(description="The instruction optimized for the selected agent.")

class IntentionPredictor:

    async def _load_few_shots(self) -> str:
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope
        from app.infrastructure.database.sql.models.learning import RouterTrainingData

        try:
            async with session_scope() as session:
                query = select(RouterTrainingData).where(RouterTrainingData.is_active == True).order_by(RouterTrainingData.id.desc()).limit(20)
                result = await session.execute(query)
                data = result.scalars().all()

                if not data:
                    return "No examples available."

                examples = []
                for item in data:
                    examples.append(f"- User: \"{item.instruction}\" -> Intent: {item.intent.upper()} (Reason: {item.reasoning})")

                return "\n".join(examples)
        except Exception:
            # Fallback for DB errors
            return "No examples available."

    async def predict(self, instruction: str, thread_id: str = None) -> IntentionOutput:
        # Dynamic LLM creation
        # Optimization: Use a faster model if possible (e.g. gpt-4o-mini)
        llm = LLMFactory.create_llm(temperature=0)

        # We manually construct the parser and inject instructions
        parser = JsonOutputParser(pydantic_object=IntentionOutput)

        # Override the prompt to be extremely explicit for the parser
        format_instructions = parser.get_format_instructions()

        # Load Dynamic Examples (Async now)
        examples = await self._load_few_shots()

        final_prompt = ChatPromptTemplate.from_template("""You are an expert intent classifier.
Your goal is to route the user's request.

Agents:
1. **Chat**: Casual conversation, greetings, "thank you", "who are you", simple chit-chat. NO functional request.
2. **Browser**: Web tasks.
3. **Computer**: Desktop/File tasks.
4. **Mobile**: APP/Phone tasks.
5. **General**: Coding, Questions, Planner, Complex Instructions.

Few-Shot Examples (Learn from these!):
{examples}

CRITICAL: 
- If request is broad/unclear, SELECT "general".
- If request is "Hi" or "How are you", SELECT "chat".
- OUTPUT JSON ONLY. NO MARKDOWN. NO EXPLANATIONS.
- DO NOT use "**Analysis:**" or "**Intent:**" prefixes. Just pure JSON.

{format_instructions}

User Request: {instruction}
""")

        chain = final_prompt | llm | parser

        try:
            result = await chain.ainvoke(
                {"instruction": instruction, "format_instructions": format_instructions, "examples": examples},
                config={"callbacks": []}  # Disable global callbacks (streaming) for internal thought
            )

            output = None
            if isinstance(result, dict):
                output = IntentionOutput(**result)
            else:
                output = result

            # Phase 6: Side Channel for Transparent Thought
            if thread_id:
                try:
                    await activity_monitor.update_agent_state(
                        thread_id=thread_id,
                        mode="ROUTING",
                        task_name="Intent Analysis",
                        task_status=f"Intent detected: {output.intent.upper()}",
                        details={
                            "type": "thought",
                            "thought_type": "intent",
                            "intent": output.intent,
                            "reasoning": output.reasoning,
                            "confidence": 0.95 # Proxy high confidence for success
                        }
                    )
                except Exception:
                    pass # Non-blocking

            return output

        except Exception:
            # Fallback for parsing errors
            return IntentionOutput(intent="general", reasoning="Error parsing intention", refined_instruction=instruction)

    async def learn(self, instruction: str, correct_intent: str, reasoning: str = "User feedback"):
        """
        Dynamically add a new training example to the DB.
        """
        from app.infrastructure.database.sql.database import session_scope
        from app.infrastructure.database.sql.models.learning import RouterTrainingData

        try:
            async with session_scope() as session:
                new_example = RouterTrainingData(
                    instruction=instruction,
                    intent=correct_intent,
                    reasoning=reasoning,
                    is_active=True,
                    source="user_feedback"
                )
                session.add(new_example)
                # Commit handled by context manager

            return True
        except Exception as e:
            print(f"Failed to learn: {e}")
            return False

intention_predictor = IntentionPredictor()
