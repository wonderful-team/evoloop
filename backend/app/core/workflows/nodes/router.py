from app.core.workflows.state import AgentState
from langchain_core.runnables import RunnableConfig
from app.domain.intention.predictor import intention_predictor
from langchain_core.messages import HumanMessage

async def router_node(state: AgentState, config: RunnableConfig):
    """
    Router Node that intercepts user input and decides if it should go to a specialized agent.
    This runs BEFORE the Supervisor.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"next_node": "supervisor"}

    last_message = messages[-1]
    # Only route on HumanMessage (user input), otherwise continue normal flow
    if not isinstance(last_message, HumanMessage):
        return {"next_node": "supervisor"}

    instruction = last_message.content
    instruction = last_message.content
    try:
        thread_id = config.get("configurable", {}).get("thread_id")
        prediction = await intention_predictor.predict(instruction, thread_id=thread_id)
        intent = prediction.intent
        
        # Mapping intent to Nodes/Tools
        # Note: In the current graph, we might want to route to a node that CALLS the tool, 
        # or have the Supervisor handle it but with a strong hint.
        # For Supercomplete, we want direct routing if possible.
        
        if intent == "browser":
             # We can route to a specialized 'browser_node' that invokes the tool
             # Or inform supervisor. For now, let's route to supervisor but inject the intent
             # Actually, best practice: Route to a node that runs the tool
             return {"next_node": "browser_executor", "refined_instruction": prediction.refined_instruction}
        elif intent == "computer":
             return {"next_node": "computer_executor", "refined_instruction": prediction.refined_instruction}
        elif intent == "mobile":
             return {"next_node": "mobile_executor", "refined_instruction": prediction.refined_instruction}
        else:
             return {"next_node": "supervisor"}

    except Exception as e:
        # Fallback to general
        return {"next_node": "supervisor"}
