
import asyncio
import os
import sys
import logging
import json

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.engine.prompts.worker_builder import WorkerPromptBuilder
from app.core.context import ContextManager
from app.infrastructure.llm.factory import get_default_llm
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("RealAgentTest")

async def test_direct_agent_heuristic():
    print("\n" + "="*60)
    print("🤖 REAL AGENT VERIFICATION: PHASE 9 HEURISTIC (DIRECT LLM)")
    print("="*60)

    # 1. Setup Context
    ctx = ContextManager.current()
    ctx.metadata["has_android"] = True
    
    # 2. Build Prompt
    agent_config = {
        "role_name": "MobileSpecialist",
        "system_instructions": "You are a mobile automation expert. Use the Mobile Protocol to navigate WeChat. If you see icons but no text, use your spatial prior knowledge."
    }
    ticket = {
        "topic": "Search for 'File Transfer Assistant' in WeChat",
        "acceptance_criteria": ["Enter search UI", "Find the assistant"]
    }
    
    builder = WorkerPromptBuilder(agent_config, ticket)
    system_prompt = builder.build()
    
    # 3. Simulate Scenario (Difficult visual state)
    mock_ocr_result = """
### Visual Perception (OCR Result):
[0] "2:20" (93, 55) [text]
[1] "微信" (539, 160) [text]
[2] "Mac 微信已登录" (291, 274) [text]
[3] "新消息（8）" (180, 450) [text]
[4] "联系人" (120, 520) [text]
[5] "WeChat" (500, 160) [text]
[6] "通讯录" (404, 2309) [text]
[7] "发现" (673, 2309) [text]
[8] "我" (942, 2309) [text]

(Observation: The top-right area contains two symbolic icons, likely Search and More, but they have NO text labels in this OCR pass.)
"""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="Please search for 'File Transfer Assistant' in WeChat."),
        AIMessage(content="I am in the main WeChat list. Taking a screenshot to locate the search icon.", tool_calls=[{
            "name": "mobile_control",
            "args": {"action": "screenshot", "ocr": True},
            "id": "perception_1"
        }]),
        ToolMessage(content=mock_ocr_result, tool_call_id="perception_1")
    ]

    # 4. Invoke LLM
    print("\n🚀 Invoking LLM for next action...")
    llm = get_default_llm(temperature=0.0) 
    
    start_time = asyncio.get_event_loop().time()
    response = await llm.ainvoke(messages)
    duration = asyncio.get_event_loop().time() - start_time
    
    print(f"✅ LLM responded in {duration:.2f}s")
    
    # 5. Analysis
    print("\n" + "="*60)
    print("📊 AGENT DECISION ANALYSIS")
    print("="*60)
    
    # Clean up reasoning if it's too long
    reasoning = response.content.split("\n")[0] if response.content else "No reasoning text."
    print(f"\n🧠 Primary Reasoning: {reasoning}")
    
    if response.tool_calls:
        for tc in response.tool_calls:
            print(f"\n🛠️ TOOL: {tc['name']}")
            print(f"   ARGS: {json.dumps(tc['args'], ensure_ascii=False, indent=2)}")
            
            # Check for Blind Click
            args = tc['args']
            if tc['name'] == 'mobile_control' and args.get('action') == 'tap':
                x, y = args.get('x'), args.get('y')
                if x and y and x > 850 and y < 350:
                    print("\n✅ SUCCESS: The Agent applied the 'Blind Click' strategy to the top-right corner!")
                else:
                    print("\n❌ FAILED: The Agent clicked outside the expected search area.")
    else:
        print("\n❌ Agent did not suggest any action.")

if __name__ == "__main__":
    asyncio.run(test_direct_agent_heuristic())
