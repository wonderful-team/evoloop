"""API routes for macro CRUD (mirror of /learning/skills for the macros table)."""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import TokenDep
from app.core.events.publishers import publish_macro_mutated
from app.core.execution.macro import lifecycle
from app.infrastructure.database import session_scope
from app.models.macro import Macro

logger = logging.getLogger(__name__)

router = APIRouter(tags=["macros"])


class MacroDTO(BaseModel):
    id: int
    app_map_id: int | None
    entity: str | None
    name: str
    description: str
    trigger_patterns: list
    parameters: list
    risk_tier: str
    requires_confirmation: bool
    allow_self_healing: bool
    status: str
    is_active: bool
    namespace: str | None
    fallback_skill_id: int | None
    project_id: int | None


class MacroDetailDTO(MacroDTO):
    macro_script: str
    app_map_version: int | None
    source_thread_id: str | None


class MacroUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger_patterns: list | None = None
    parameters: list | None = None
    macro_script: str | None = None
    namespace: str | None = None
    fallback_skill_id: int | None = None
    allow_self_healing: bool | None = None
    risk_tier: str | None = None
    requires_confirmation: bool | None = None


class MacroCreateRequest(BaseModel):
    name: str = "未命名宏"
    description: str = ""
    project_id: int | None = None
    macro_script: str = "steps: []"


class ConfirmBulkRequest(BaseModel):
    macro_ids: list[int]


class MacroExecuteRequest(BaseModel):
    thread_id: str | None = None
    params: dict = {}


def _to_dto(m: Macro) -> MacroDTO:
    return MacroDTO(
        id=m.id,
        app_map_id=m.app_map_id,
        entity=m.entity,
        name=m.name,
        description=m.description,
        trigger_patterns=m.trigger_patterns or [],
        parameters=m.parameters or [],
        risk_tier=m.risk_tier,
        requires_confirmation=bool(m.requires_confirmation),
        allow_self_healing=bool(m.allow_self_healing),
        status=m.status,
        is_active=bool(m.is_active),
        namespace=m.namespace,
        fallback_skill_id=m.fallback_skill_id,
        project_id=m.project_id,
        macro_script=m.macro_script,
        app_map_version=m.app_map_version,
        source_thread_id=m.source_thread_id,
    )


@router.post("/", response_model=MacroDTO, status_code=201)
async def create_macro(req: MacroCreateRequest, _token: TokenDep):
    async with session_scope() as db:
        macro = await lifecycle.create_macro_from_synthesis(
            db=db,
            name=req.name,
            description=req.description,
            macro_script=req.macro_script,
            project_id=req.project_id,
        )
        macro_id = macro.id

    await publish_macro_mutated(macro_id, action="create")
    return _to_dto(await lifecycle.load_macro(macro_id))


@router.get("/", response_model=list[MacroDTO])
async def list_macros(
    _token: TokenDep,
    project_id: int | None = Query(default=None),
    app_map_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    macros = await lifecycle.list_macros(
        project_id=project_id,
        app_map_id=app_map_id,
        status=status,
        offset=skip,
        limit=limit,
    )
    return [_to_dto(m) for m in macros]


@router.get("/{macro_id}", response_model=MacroDetailDTO)
async def get_macro(macro_id: int, _token: TokenDep):
    macro = await lifecycle.load_macro(macro_id)
    if macro is None:
        raise HTTPException(404, f"Macro #{macro_id} not found")
    return _to_dto(macro)


@router.put("/{macro_id}", response_model=MacroDTO)
async def update_macro(macro_id: int, req: MacroUpdateRequest, _token: TokenDep):
    if req.macro_script is not None:
        from app.core.execution.macro.schemas import MacroScript

        try:
            MacroScript.from_yaml(req.macro_script)
        except (ValueError, TypeError, KeyError) as e:
            raise HTTPException(400, f"Invalid macro YAML: {e}")
    fields = req.model_dump(exclude_unset=True)
    ok = await lifecycle.update_macro(macro_id, fields)
    if not ok:
        raise HTTPException(404, f"Macro #{macro_id} not found")
    return _to_dto(await lifecycle.load_macro(macro_id))


@router.delete("/{macro_id}")
async def delete_macro(macro_id: int, _token: TokenDep):
    ok = await lifecycle.delete_macro(macro_id)
    if not ok:
        raise HTTPException(404, f"Macro #{macro_id} not found")
    return {"status": "deleted", "id": macro_id}


@router.post("/{macro_id}/confirm", response_model=MacroDTO)
async def confirm_macro(macro_id: int, _token: TokenDep):
    ok = await lifecycle.confirm_macro(macro_id)
    if not ok:
        raise HTTPException(404, f"Macro #{macro_id} not found")
    return _to_dto(await lifecycle.load_macro(macro_id))


@router.post("/confirm-bulk")
async def confirm_bulk(req: ConfirmBulkRequest, _token: TokenDep):
    count = await lifecycle.confirm_bulk(req.macro_ids)
    return {"status": "ok", "confirmed": count}


@router.post("/{macro_id}/execute")
async def execute_macro(
    macro_id: int,
    req: MacroExecuteRequest,
    _token: TokenDep,
):
    macro = await lifecycle.load_macro(macro_id)
    if macro is None:
        raise HTTPException(404, f"Macro #{macro_id} not found")
    if not macro.is_routable():
        raise HTTPException(
            400, f"Macro #{macro_id} is {macro.status}; confirm it first"
        )

    from app.core.execution.macro.schemas import MacroScript
    from app.core.execution.macro.service import MacroService

    try:
        script = MacroScript.from_yaml(macro.macro_script)
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(400, f"Invalid macro YAML: {e}")

    execution_params = dict(req.params or {})
    execution_params["_macro_id"] = macro.id
    execution_params["_macro_name"] = macro.name
    thread_id = req.thread_id or f"macro-exec-{macro_id}"
    result = await MacroService.run(
        thread_id=thread_id,
        script_input=script,
        params=execution_params,
        macro=macro,
    )
    return {
        "success": result.success if hasattr(result, "success") else getattr(result, "get", lambda k: None)("success"),
        "message": result.message if hasattr(result, "message") else getattr(result, "get", lambda k: None)("message"),
        "extracted_data": result.extracted_data if hasattr(result, "extracted_data") else getattr(result, "get", lambda k: None)("extracted_data"),
    }
