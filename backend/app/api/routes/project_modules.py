from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from app.api.deps import TokenDep

from app.infrastructure.external.evocloud import evocloud_client

router = APIRouter()

# --- Helper ---
def get_token(authorization: str | None = Header(None)):
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "")
# The get_token helper is replaced by TokenDep in the new route definitions.

# --- Pydantic Models ---

class TimesheetQuickAddRequest(BaseModel):
    project_id: int
    hours: float
    description: str
    work_type: str | None = 'development'

# --- Budget & Timesheet ---

@router.get("/budget/list")
async def get_budget_list(project_id: int, page: int = 1, page_size: int = 50, token: TokenDep = None):
    return await evocloud_client.get_budget_list(project_id, page, page_size, token)

@router.get("/budget/overview")
async def get_budget_overview(project_id: int, token: TokenDep = None):
    return await evocloud_client.get_budget_overview(project_id, token)

@router.get("/timesheet/list")
async def get_timesheet_list(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    authorization: str | None = Header(None)
):
    token = get_token(authorization)
    res = await evocloud_client.get_timesheet_list(project_id, page, page_size, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to get timesheet list"))
    return res.get("data", {})

@router.post("/timesheet/quick_add")
async def quick_add_timesheet(req: TimesheetQuickAddRequest, authorization: str | None = Header(None)):
    token = get_token(authorization)
    data = req.model_dump()
    res = await evocloud_client.add_timesheet_quick(data, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to add timesheet"))
    return res

# --- Statistics Routes ---

@router.get("/statistics/project")
async def get_project_statistics(project_id: int | None = None, authorization: str | None = Header(None)):
    token = get_token(authorization)
    res = await evocloud_client.get_project_statistics(project_id, token=token)
    if res.get("code") != 0:
        raise HTTPException(status_code=400, detail=res.get("message", "Failed to get project statistics"))
    return res.get("data", {})
