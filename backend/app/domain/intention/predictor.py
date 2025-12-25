from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from app.core.config import settings

class IntentionOutput(BaseModel):
    intent: Literal["browser", "computer", "mobile", "general"] = Field(
        description="The determined intent of the user. 'browser' for web tasks, 'computer' for OS/desktop tasks, 'mobile' for phone tasks, 'general' for questions/coding."
    )
    reasoning: str = Field(description="Brief reasoning for the classification.")
    refined_instruction: str = Field(description="The instruction optimized for the selected agent.")

class IntentionPredictor:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL_NAME,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            temperature=0
        )
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert intent classifier for a multi-modal agent system.
            Your goal is to route the user's request to the most appropriate specialist agent.
            
            Agents available:
            1. **Browser Agent**: Can visit websites, extract data, interact with web apps. Use for queries like "search google", "check price on amazon", "login to website".
            2. **Computer Agent (OS/Desktop)**: Can control the local computer mouse/keyboard. Use for "open calculator", "move files on desktop", "open VS Code", "system settings".
            3. **Mobile Agent (Phone)**: Can control a connected Android/iOS device. Use for "open WeChat", "swipe on phone", "check mobile app", "send SMS".
            4. **General Agent**: For general coding, questions, file editing (VS Code extension), or if unsure.
            
            Analyze the user's request and classify the intent. Also verify if the request implies a specific device (e.g. "on my phone" -> Mobile).
            """),
            ("human", "{instruction}")
        ])
        self.chain = self.prompt | self.llm.with_structured_output(IntentionOutput)

    async def predict(self, instruction: str) -> IntentionOutput:
        return await self.chain.ainvoke({"instruction": instruction})

intention_predictor = IntentionPredictor()
