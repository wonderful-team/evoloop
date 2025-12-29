from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel

from app.infrastructure.external.imagicbox import imagicbox_client

router = APIRouter()

# --- Helper ---
def get_token(authorization: Optional[str] = Header(None)):
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "")
    return authorization

# --- Pydantic Models ---

class TimesheetQuickAddRequest(BaseModel):
    project_id: int
    hours: float
    description: str
    work_type: Optional[str] = 'development'
    
# --- Budget Routes ---

@router.get("/budget/list")
async def get_budget_list(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    authorization: Optional[str] = Header(None)
):
    token = get_token(authorization)
    res = imagicbox_client.get_budget_list(project_id, page, page_size, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to get budget list"))
    return res.get("data", {})

@router.get("/budget/overview")
async def get_budget_overview(project_id: int, authorization: Optional[str] = Header(None)):
    token = get_token(authorization)
    res = imagicbox_client.get_budget_overview(project_id, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to get budget overview"))
    return res.get("data", {})

# --- Timesheet Routes ---

@router.get("/timesheet/list")
async def get_timesheet_list(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    authorization: Optional[str] = Header(None)
):
    token = get_token(authorization)
    res = imagicbox_client.get_timesheet_list(project_id, page, page_size, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to get timesheet list"))
    return res.get("data", {})

@router.post("/timesheet/quick_add")
async def quick_add_timesheet(req: TimesheetQuickAddRequest, authorization: Optional[str] = Header(None)):
    token = get_token(authorization)
    data = req.model_dump()
    res = imagicbox_client.add_timesheet_quick(data, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to add timesheet"))
    return res

# --- Statistics Routes ---

@router.get("/statistics/project")
async def get_project_statistics(project_id: Optional[int] = None, authorization: Optional[str] = Header(None)):
    token = get_token(authorization)
    res = imagicbox_client.get_project_statistics(project_id, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to get project statistics"))
    return res.get("data", {})
