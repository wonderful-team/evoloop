from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core.config import settings


class IntentionOutput(BaseModel):
    intent: Literal["browser", "computer", "mobile", "general"] = Field(
        description="The determined intent of the user. 'browser' for web tasks, 'computer' for OS/desktop tasks, 'mobile' for phone tasks, 'general' for questions/coding."
    )
    reasoning: str = Field(description="Brief reasoning for the classification.")
    refined_instruction: str = Field(description="The instruction optimized for the selected agent.")

class IntentionPredictor:
    async def predict(self, instruction: str) -> IntentionOutput:
        from app.core.llm.factory import LLMFactory
        from langchain_core.output_parsers import JsonOutputParser
        
        # Dynamic LLM creation
        llm = LLMFactory.create_llm(temperature=0)
        
        # We manually construct the parser and inject instructions
        parser = JsonOutputParser(pydantic_object=IntentionOutput)
        
        # Override the prompt to be extremely explicit for the parser
        format_instructions = parser.get_format_instructions()
        
        final_prompt = ChatPromptTemplate.from_template("""You are an expert intent classifier.
Your goal is to route the user's request.

Agents:
1. **Browser**: Web tasks.
2. **Computer**: Desktop/File tasks.
3. **Mobile**: APP/Phone tasks.
4. **General**: Coding, Questions, Chat.

CRITICAL: 
- If request is broad/unclear, SELECT "general".
- OUTPUT JSON ONLY. NO MARKDOWN. NO EXPLANATIONS.
- DO NOT use "**Analysis:**" or "**Intent:**" prefixes. Just pure JSON.

{format_instructions}

User Request: {instruction}
""")
        
        chain = final_prompt | llm | parser
        
        try:
            result = await chain.ainvoke({"instruction": instruction, "format_instructions": format_instructions})
            # Fix: Parser returns dict, need to convert to Pydantic
            if isinstance(result, dict):
                return IntentionOutput(**result)
            return result
        except Exception:
            # Fallback for parsing errors
            return IntentionOutput(intent="general", reasoning="Error parsing intention", refined_instruction=instruction)

intention_predictor = IntentionPredictor()
