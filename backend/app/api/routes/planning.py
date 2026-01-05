from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, Any

from app.core.globals import get_graph
from app.logging import logger

router = APIRouter(prefix="/conversations/{thread_id}/plan", tags=["planning"])

@router.get("")
async def get_plan(thread_id: str):
    """
    Get the current execution plan from the agent state.
    """
    graph = get_graph()
    if not graph:
        # If no graph (e.g. server restart), returns distinct status
        return {"status": "no_graph", "plan": None}
        
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)
        
        if not state.values:
            return {"status": "no_state", "plan": None}
            
        # Extract Plan from state
        # We prefer 'structured_plan' (JSON string) if available, 
        # otherwise fallback to 'current_plan' (text)
        structured_plan_str = state.values.get("structured_plan")
        current_plan_text = state.values.get("current_plan")
        
        plan_data = None
        if structured_plan_str:
            try:
                import json
                plan_data = json.loads(structured_plan_str)
            except Exception as e:
                logger.warning(f"Failed to parse structured_plan: {e}")
                
        # If no structured plan, we might construct a dummy one from text or just return text?
        # Frontend expects { title, steps: [] }
        # If we only have text, we return it as description? 
        # For now, let's return whatever we have.
        
        return {
            "status": "success", 
            "plan": plan_data, 
            "text_summary": current_plan_text,
            "state": {
                "scratchpad": state.values.get("scratchpad"),
                "project_id": state.values.get("project_id"),
                "working_directory": state.values.get("working_directory"),
                "last_node": state.next, # graph.aget_state returns Checkpoint tuple, state.next is standard
                "snapshot_time": state.created_at
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get plan for {thread_id}: {e}")
        return {"status": "error", "error": str(e)}
