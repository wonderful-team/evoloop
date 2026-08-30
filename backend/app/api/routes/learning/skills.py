"""Skills sub-router — skill CRUD, validation, YAML import/export, execution."""

import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    HTTPException,
    Query,
    Response,
)

from app.api.deps import CurrentUserOptional, require_benefit
from app.api.responses import BaseAPIResponse
from app.constants import DEFAULT_PROJECT_ID
from app.core.engine.dispatch import DispatchStatus, dispatch_agent_run
from app.core.events.publishers import publish_macro_mutated, publish_skill_mutated
from app.core.learning.macro import (
    WEB_POLICY,
    MacroEngine,
    MacroScriptCompiler,
    confirm_macro,
    load_macro,
)
from app.core.learning.macro.service import MacroService
from app.core.learning.schemas import (
    CreateSkillFromYamlRequest,
    CreateSkillFromYamlResponse,
    ExecuteSkillRequest,
    ExecuteSkillResponse,
    ImportSkillsRequest,
    ImportSkillsResponse,
    PaginatedSkillsResponse,
    SkillDetailResponse,
    SkillDTO,
    SynthesizeRequest,
    SynthesizeSkillResponse,
    UpdateSkillFromYamlResponse,
    UpdateSkillRequest,
    UpdateSkillResponse,
    ValidateSkillResponse,
    ValidateYamlRequest,
    ValidateYamlResponse,
)
from app.core.learning.skills.discovery import skill_discovery
from app.core.learning.skills.importer import SkillImporter
from app.core.learning.skills.lifecycle import (
    SkillConflictError,
    SkillNotFoundError,
    apply_validation_result,
    confirm_skill,
    create_from_synthesis,
    deduplicate_name,
)
from app.core.learning.skills.lifecycle import delete_skill as delete_skill_record
from app.core.learning.skills.lifecycle import update_skill as update_skill_record
from app.core.learning.skills.repository import skill_repository
from app.core.learning.skills.validator import SkillValidator
from app.core.learning.trace.parser import TraceParser
from app.core.learning.workflow_synthesizer import WorkflowSynthesizer
from app.infrastructure.database import session_scope
from app.utils.json import safe_load_json_list
from app.utils.parameters import (
    derive_parameters_from_macro,
    missing_required_params,
)
from app.utils.template import render_template
from app.utils.yaml import YAMLError, macro_from_yaml, validate_macro_yaml

from .shared import _member_id, _normalize_skill_params

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/skills/synthesize",
    response_model=SynthesizeSkillResponse,
    dependencies=[Depends(require_benefit("skill_learning"))],
)
async def synthesize_skill(body: SynthesizeRequest, current_user: CurrentUserOptional = None):
    """Synthesize a new skill from a trace sequence."""
    try:
        parser = TraceParser(body.thread_id, body.session_id)
        sequence = await parser.parse()
        synthesizer = WorkflowSynthesizer(body.thread_id, body.session_id, sequence=sequence)
        result = await synthesizer.synthesize()
        skill = result.skill
        if skill is None:
            raise ValueError("Skill synthesis did not produce a skill")
        macro_script = MacroScriptCompiler().compile(sequence).to_yaml()

        async with session_scope() as db:
            db_skill = await create_from_synthesis(
                db,
                member_id=_member_id(current_user),
                name=skill.name,
                description=skill.description,
                trigger_patterns=skill.trigger_patterns,
                parameters=skill.parameters,
                preconditions=skill.preconditions,
                tools_used=skill.tools_used,
                source_thread_id=skill.source_thread_id,
                source_session_id=skill.source_session_id,
                instructions=skill.instructions,
            )
            new_macro = await MacroService.create_for_skill(
                db,
                db_skill,
                macro_script,
                project_id=body.project_id,
                member_id=_member_id(current_user),
                source_thread_id=skill.source_thread_id,
            )

        await publish_skill_mutated(skill_id=db_skill.id, action="create")
        await publish_macro_mutated(new_macro.id, action="create")

        return SynthesizeSkillResponse(
            success=True,
            skill_id=db_skill.id,
            skill_name=db_skill.name,
            skill_yaml=skill.to_yaml(),
        )

    except Exception as e:
        logger.exception(f"Skill synthesis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")
    finally:
        await skill_discovery.reload()


@router.post(
    "/skills/import",
    response_model=ImportSkillsResponse,
    dependencies=[Depends(require_benefit("skill_learning"))],
)
async def import_skills(body: ImportSkillsRequest):
    """Bulk import skills from a local directory."""
    try:
        results = await SkillImporter.import_from_directory(body.directory)
        return ImportSkillsResponse(success=True, results=results.model_dump())
    except Exception as e:
        logger.exception(f"Skill import failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    finally:
        await skill_discovery.reload()


@router.get("/skills", response_model=PaginatedSkillsResponse)
async def list_skills(
    active_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: CurrentUserOptional = None,
):
    """List all learned skills with pagination."""
    try:
        await skill_discovery.ensure_system_skills_synced()
    except Exception as e:
        logger.warning(f"Background skill sync failed during list: {e}", exc_info=True)

    skills, total = await skill_repository.list_page(
        page=page,
        page_size=page_size,
        member_id=_member_id(current_user),
        active_only=active_only,
    )

    return PaginatedSkillsResponse(
        data=[
            SkillDTO(
                id=s.id,
                name=s.name,
                description=s.description,
                namespace=s.namespace,
                trigger_patterns=safe_load_json_list(s.trigger_patterns),
                parameters=_normalize_skill_params(s.parameters),
                tools_used=safe_load_json_list(s.tools_used),
                success_count=s.success_count,
                failure_count=s.failure_count,
                is_active=s.is_active,
                status=s.status,
                macro_id=s.macro_id,
                validation_report=s.validation_report,
                instructions=s.instructions,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in skills
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/skills/{skill_id}", response_model=SkillDetailResponse)
async def get_skill(skill_id: int, current_user: CurrentUserOptional = None):
    """Get full details of a specific skill."""
    skill = await skill_repository.get_by_id(
        skill_id, member_id=_member_id(current_user)
    )
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    macro = None
    if skill.macro_id:
        async with session_scope() as db:
            macro = await load_macro(skill.macro_id, db=db)

    return SkillDetailResponse(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        namespace=skill.namespace,
        trigger_patterns=safe_load_json_list(skill.trigger_patterns),
        parameters=_normalize_skill_params(skill.parameters),
        preconditions=safe_load_json_list(skill.preconditions),
        tools_used=safe_load_json_list(skill.tools_used),
        source_thread_id=skill.source_thread_id,
        source_session_id=skill.source_session_id,
        success_count=skill.success_count,
        failure_count=skill.failure_count,
        is_active=skill.is_active,
        status=skill.status,
        macro_id=skill.macro_id,
        macro_script=macro.macro_script if macro else "",
        allow_self_healing=macro.allow_self_healing if macro else True,
        validation_report=skill.validation_report,
        instructions=skill.instructions,
        resource_path=skill.resource_path,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


@router.delete("/skills/{skill_id}", response_model=BaseAPIResponse)
async def delete_skill(skill_id: int, current_user: CurrentUserOptional = None):
    """Physically delete a skill and its resources."""
    try:
        async with session_scope() as db:
            try:
                skill = await delete_skill_record(
                    db, skill_id, _member_id(current_user)
                )
            except SkillNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

        await publish_skill_mutated(
            skill_id=skill_id,
            action="delete",
            namespace=skill.namespace,
            name=skill.name,
        )

        return BaseAPIResponse(
            success=True, message=f"Skill {skill_id} physically deleted"
        )
    finally:
        await skill_discovery.reload()


@router.put("/skills/{skill_id}", response_model=UpdateSkillResponse)
async def update_skill(
    skill_id: int, body: UpdateSkillRequest, current_user: CurrentUserOptional = None
):
    """Update a learned skill."""
    try:
        async with session_scope() as db:
            try:
                skill = await update_skill_record(
                    db,
                    skill_id,
                    _member_id(current_user),
                    name=body.name,
                    description=body.description,
                    namespace=body.namespace,
                    instructions=body.instructions,
                    trigger_patterns=body.trigger_patterns,
                    parameters=body.parameters,
                    preconditions=body.preconditions,
                )
            except SkillNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except SkillConflictError as e:
                raise HTTPException(status_code=400, detail=str(e))

        await publish_skill_mutated(skill_id=skill_id, action="update")

        macro = None
        if skill.macro_id:
            async with session_scope() as db:
                macro = await load_macro(skill.macro_id, db=db)

        return UpdateSkillResponse(
            success=True,
            message=f"Skill {skill_id} updated",
            skill=SkillDetailResponse(
                id=skill.id,
                name=skill.name,
                description=skill.description,
                namespace=skill.namespace,
                trigger_patterns=safe_load_json_list(skill.trigger_patterns),
                parameters=_normalize_skill_params(skill.parameters),
                preconditions=safe_load_json_list(skill.preconditions),
                tools_used=safe_load_json_list(skill.tools_used),
                source_thread_id=skill.source_thread_id,
                source_session_id=skill.source_session_id,
                success_count=skill.success_count,
                failure_count=skill.failure_count,
                is_active=skill.is_active,
                status=skill.status,
                macro_id=skill.macro_id,
                macro_script=macro.macro_script if macro else "",
                allow_self_healing=macro.allow_self_healing if macro else True,
                validation_report=skill.validation_report,
                instructions=skill.instructions,
                resource_path=skill.resource_path,
                created_at=skill.created_at,
                updated_at=skill.updated_at,
            ),
        )
    finally:
        await skill_discovery.reload()


@router.post("/skills/{skill_id}/execute", response_model=ExecuteSkillResponse)
async def run_skill(
    skill_id: int,
    body: ExecuteSkillRequest,
    current_user: CurrentUserOptional = None,  # noqa: ARG001
):
    """Execute a skill by injecting a directive into the agent's conversation."""
    async with session_scope() as db:
        skill = await skill_repository.get_by_id(skill_id, db=db)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        macro = None
        if skill.macro_id:
            macro = await load_macro(skill.macro_id, db=db)

    params = body.params.model_dump()
    if macro is not None:
        result = await MacroEngine.run(
            body.thread_id,
            macro,
            params=params,
            project_id=body.project_id
            if body.project_id is not None
            else DEFAULT_PROJECT_ID,
            policy=WEB_POLICY,
        )
        if result.status in ("not_routable", "missing_params", "bad_macro"):
            status = {
                "not_routable": 403,
                "missing_params": 400,
                "bad_macro": 500,
            }.get(result.status, 400)
            raise HTTPException(status_code=status, detail=result.message)
        if result.status == "fallback_required":
            return ExecuteSkillResponse(
                success=True,
                message=result.message
                or f"Macro failed; self-healing queued for '{skill.name}'",
                execution_mode="deterministic",
            )
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
        return ExecuteSkillResponse(
            success=True,
            message=result.message or f"Executed '{skill.name}'",
            execution_mode="deterministic",
        )

    missing = missing_required_params(skill.parameters, params)
    if missing:
        raise HTTPException(
            status_code=400, detail=f"Missing required parameters: {', '.join(missing)}"
        )

    skill_name = skill.name

    directive = render_template(
        "core/learning/skill_directive.prompt.j2",
        skill_name=skill_name,
        parameters=params,
    )
    result = await dispatch_agent_run(
        thread_id=body.thread_id,
        message_content=directive,
        project_id=body.project_id
        if body.project_id is not None
        else DEFAULT_PROJECT_ID,
        metadata={"goal_prefix": f"[Skill: {skill_name}] "},
    )

    if result.status == DispatchStatus.FAILED:
        raise HTTPException(status_code=500, detail=result.error)
    if result.inputs is None:
        raise HTTPException(status_code=500, detail="Failed to prepare agent inputs")

    # 用用户线程执行技能 → 统一走 session_manager.submit（进会话主循环，
    # 享受统一生命周期），与 voice/web/mobile 主交互路径一致。
    from app.core.engine.session.manager import session_manager

    await session_manager.submit(body.thread_id, result.inputs)

    return ExecuteSkillResponse(
        success=True,
        message=f"Agentic execution queued for '{skill_name}'",
        execution_mode="agentic",
    )


@router.get("/skills/{skill_id}/validate", response_model=ValidateSkillResponse)
async def validate_skill(skill_id: int, current_user: CurrentUserOptional = None):  # noqa: ARG001
    """Run the validator on a skill and return its health status."""
    async with session_scope() as db:
        skill = await skill_repository.get_by_id(skill_id, db=db)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        if not skill.resource_path:
            return ValidateSkillResponse(
                success=False, error="Skill has no resource path (cannot validate)"
            )

        validation = SkillValidator.validate_folder(Path(skill.resource_path))
        await apply_validation_result(skill, validation)

        return ValidateSkillResponse(success=True, validation=validation.model_dump())


@router.post("/skills/{skill_id}/confirm", response_model=BaseAPIResponse)
async def confirm_learned_skill(
    skill_id: int, current_user: CurrentUserOptional = None
):
    """User confirms a synthesized skill. Updates status from pending_review to verified."""
    async with session_scope() as db:
        try:
            skill = await confirm_skill(db, skill_id, _member_id(current_user))
        except SkillNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except SkillConflictError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if skill.macro_id:
            await confirm_macro(skill.macro_id, db=db)

        logger.info(f"Skill {skill.id} ({skill.name}) confirmed by user.")

    await publish_skill_mutated(skill_id=skill_id, action="update")

    return BaseAPIResponse(
        success=True, message=f"Skill '{skill.name}' confirmed and activated."
    )


# ============ YAML Macro Support ============


@router.post("/skills/from-yaml", response_model=CreateSkillFromYamlResponse)
async def create_skill_from_yaml(
    body: CreateSkillFromYamlRequest,
    bg_tasks: BackgroundTasks,  # noqa: ARG001
    current_user: CurrentUserOptional = None,
):
    """Create a new skill from YAML macro definition."""
    try:
        is_valid, errors = validate_macro_yaml(body.yaml_content)
        if not is_valid:
            raise HTTPException(
                status_code=400, detail=f"Invalid YAML format: {'; '.join(errors)}"
            )

        macro_steps = macro_from_yaml(body.yaml_content)
        derived_params = derive_parameters_from_macro(body.yaml_content)

        async with session_scope() as db:
            unique_name = await deduplicate_name(
                db, body.name, _member_id(current_user)
            )
            skill = await create_from_synthesis(
                db,
                member_id=_member_id(current_user),
                name=body.name,
                description=body.description
                or f"Created from YAML ({len(macro_steps)} steps)",
                namespace=body.namespace,
                trigger_patterns=[unique_name.lower().replace(" ", "_")],
                parameters=derived_params,
                tools_used=[],
            )
            macro = await MacroService.create_for_skill(
                db,
                skill,
                body.yaml_content,
                project_id=body.project_id,
                member_id=_member_id(current_user),
            )

        await publish_skill_mutated(skill_id=skill.id, action="create")
        await publish_macro_mutated(macro.id, action="create")

        return CreateSkillFromYamlResponse(
            success=True,
            skill_id=skill.id,
            skill_name=skill.name,
            step_count=len(macro_steps),
        )
    except YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML error: {str(e)}")
    except Exception as e:
        logger.exception(f"Failed to create skill from YAML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create skill: {str(e)}")


@router.post("/skills/validate-yaml", response_model=ValidateYamlResponse)
async def validate_skill_yaml(
    body: ValidateYamlRequest,
    current_user: CurrentUserOptional = None,  # noqa: ARG001
):
    """Validate YAML macro format without creating a skill."""
    try:
        is_valid, errors = validate_macro_yaml(body.yaml_content)
        step_count = 0
        if is_valid:
            steps = macro_from_yaml(body.yaml_content)
            step_count = len(steps)

        return ValidateYamlResponse(
            valid=is_valid, errors=errors, step_count=step_count
        )
    except Exception as e:
        return ValidateYamlResponse(valid=False, errors=[str(e)], step_count=0)


@router.get("/skills/{skill_id}/yaml")
async def get_skill_yaml(skill_id: int, current_user: CurrentUserOptional = None):  # noqa: ARG001
    """Get skill macro as YAML format."""
    async with session_scope() as db:
        skill = await skill_repository.get_by_id(skill_id, db=db)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        if not skill.macro_id:
            return Response(
                content="# No macro script defined for this skill\n",
                media_type="text/yaml",
            )

        macro = await load_macro(skill.macro_id, db=db)
        if not macro or not macro.macro_script:
            return Response(
                content="# No macro script defined for this skill\n",
                media_type="text/yaml",
            )

        return Response(content=macro.macro_script, media_type="text/yaml")


@router.put("/skills/{skill_id}/yaml", response_model=UpdateSkillFromYamlResponse)
async def update_skill_yaml(
    skill_id: int,
    yaml_content: str = Body(..., media_type="text/yaml"),
    current_user: CurrentUserOptional = None,
):
    """Update skill macro from YAML content."""
    try:
        is_valid, errors = validate_macro_yaml(yaml_content)
        if not is_valid:
            raise HTTPException(
                status_code=400, detail=f"Invalid YAML: {'; '.join(errors)}"
            )

        async with session_scope() as db:
            skill = await skill_repository.get_by_id(skill_id, db=db)
            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")

            macro_id = await MacroService.reconcile_for_skill(
                db, skill, yaml_content, source_thread_id=skill.source_thread_id
            )

            await db.flush()

        await publish_skill_mutated(skill_id=skill_id, action="update")

        steps = macro_from_yaml(yaml_content)
        return UpdateSkillFromYamlResponse(
            success=True,
            message="Skill updated from YAML",
            step_count=len(steps),
        )
    except YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML parse error: {str(e)}")
    except Exception as e:
        logger.exception(f"Failed to update skill from YAML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update: {str(e)}")
    finally:
        await skill_discovery.reload()
