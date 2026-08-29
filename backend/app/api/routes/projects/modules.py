"""
API routes for project modules — budget, timesheet, statistics.
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import TokenDep, extract_bearer_token, require_benefit
from app.api.schemas.projects.modules import TimesheetQuickAddRequest
from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/budget/list")
async def get_budget_list(
    project_id: int, page: int = 1, page_size: int = 50, token: TokenDep = None
):
    return await evocloud_manager.api.get_budget_list(
        project_id, page, page_size, token=token
    )


@router.get("/budget/overview")
async def get_budget_overview(project_id: int, token: TokenDep = None):
    return await evocloud_manager.api.get_budget_overview(project_id, token=token)


@router.get("/timesheet/list", dependencies=[Depends(require_benefit("timesheet"))])
async def get_timesheet_list(
    project_id: int,
    page: int = 1,
    page_size: int = 50,
    authorization: str | None = Header(None),
):
    token = extract_bearer_token(authorization)
    res = await evocloud_manager.api.get_timesheet_list(
        project_id, page, page_size, token=token
    )
    if res.get("code") != 0:
        raise HTTPException(
            status_code=400, detail=res.get("message", "Failed to get timesheet list")
        )
    return res.get("data", {})


@router.post(
    "/timesheet/quick_add", dependencies=[Depends(require_benefit("timesheet"))]
)
async def quick_add_timesheet(
    req: TimesheetQuickAddRequest, authorization: str | None = Header(None)
):
    token = extract_bearer_token(authorization)
    data = req.model_dump()
    res = await evocloud_manager.api.add_timesheet_quick(data, token=token)
    if res.get("code") != 0:
        raise HTTPException(
            status_code=400, detail=res.get("message", "Failed to add timesheet")
        )
    return res


@router.get("/statistics/project")
async def get_project_statistics(
    project_id: int | None = None, authorization: str | None = Header(None)
):
    token = extract_bearer_token(authorization)
    res = await evocloud_manager.api.get_project_statistics(project_id, token=token)
    if res.get("code") != 0:
        raise HTTPException(
            status_code=400,
            detail=res.get("message", "Failed to get project statistics"),
        )
    return res.get("data", {})
