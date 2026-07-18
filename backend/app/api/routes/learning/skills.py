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
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUserOptional, require_benefit
from app.api.responses import BaseAPIResponse
from app.constants import DEFAULT_PROJECT_ID
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.events.publishers import publish_skill_mutated
from app.core.execution.macro.compiler import MacroScriptCompiler
from app.core.execution.macro.lifecycle import create_macro_from_synthesis
from app.core.execution.macro.runner import (
    WEB_POLICY,
    MacroGateError,
    preflight,
    run_deterministic,
)
from app.core.learning.discovery import skill_discovery
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
from app.core.learning.skill_importer import SkillImporter
from app.core.learning.skill_lifecycle import (
    create_from_synthesis,
    deduplicate_name,
)
from app.core.learning.skill_validator import SkillValidator
from app.core.learning.skill_visibility import visible_filter
from app.core.learning.trace_parser import TraceParser
from app.core.learning.workflow_synthesizer import WorkflowSynthesizer
from app.infrastructure.database import session_scope
from app.models import LearnedSkill
from app.utils.parameters import (
    derive_parameters_from_macro,
    missing_required_params,
    normalize_parameters,
)
from app.utils.template import render_template
from app.utils.yaml import YAMLError, macro_from_yaml, validate_macro_yaml

from ._shared import _member_id, _normalize_json_list, _normalize_skill_params

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/skills/synthesize",
    response_model=SynthesizeSkillResponse,
    dependencies=[Depends(require_benefit("skill_learning"))],
)
async def synthesize_skill(
    body: SynthesizeRequest, current_user: CurrentUserOptional = None
):
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
            new_macro = await create_macro_from_synthesis(
                db,
                name=db_skill.name,
                description=db_skill.description,
                trigger_patterns=db_skill.trigger_patterns,
                parameters=normalize_parameters(db_skill.parameters),
                macro_script=macro_script,
                fallback_skill_id=db_skill.id,
                source_thread_id=skill.source_thread_id,
                project_id=body.project_id,
                member_id=_member_id(current_user),
            )
            db_skill.macro_id = new_macro.id

        await publish_skill_mutated(skill_id=db_skill.id, action="create")

        return SynthesizeSkillResponse(
            success=True,
            skill_id=db_skill.id,
            skill_name=db_skill.name,
            skill_yaml=skill.to_yaml(),
        )

    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
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
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
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
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.warning(f"Background skill sync failed during list: {e}")

    async with session_scope() as db:
        stmt = select(LearnedSkill).where(
            or_(
                LearnedSkill.member_id == 0,
                LearnedSkill.member_id == (_member_id(current_user)),
            )
        )
        if active_only:
            stmt = stmt.where(visible_filter())

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(LearnedSkill.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        skills = result.scalars().all()

        return PaginatedSkillsResponse(
            data=[
                SkillDTO(
                    id=s.id,
                    name=s.name,
                    description=s.description,
                    namespace=s.namespace,
                    trigger_patterns=_normalize_json_list(s.trigger_patterns),
                    parameters=_normalize_skill_params(s.parameters),
                    tools_used=_normalize_json_list(s.tools_used),
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
    async with session_scope() as db:
        stmt = (
            select(LearnedSkill)
            .where(
                or_(
                    LearnedSkill.member_id == 0,
                    LearnedSkill.member_id == (_member_id(current_user)),
                )
            )
            .where(LearnedSkill.id == skill_id)
        )
        result = await db.execute(stmt)
        skill = result.scalar_one_or_none()

        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        macro = None
        if skill.macro_id:
            from app.models.macro import Macro

            macro = await db.get(Macro, skill.macro_id)

        return SkillDetailResponse(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            namespace=skill.namespace,
            trigger_patterns=_normalize_json_list(skill.trigger_patterns),
            parameters=_normalize_skill_params(skill.parameters),
            preconditions=_normalize_json_list(skill.preconditions),
            tools_used=_normalize_json_list(skill.tools_used),
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
    import shutil

    try:
        async with session_scope() as db:
            stmt = (
                select(LearnedSkill)
                .where(
                    LearnedSkill.member_id == (_member_id(current_user))
                )
                .where(LearnedSkill.id == skill_id)
            )
            result = await db.execute(stmt)
            skill = result.scalar_one_or_none()

            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")

            if skill.resource_path:
                try:
                    path = Path(skill.resource_path)
                    if path.exists() and path.is_dir():
                        shutil.rmtree(path)
                        logger.info(f"Deleted skill resources at: {path}")
                except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
                    logger.error(
                        f"Failed to delete skill resources at {skill.resource_path}: {e}"
                    )

            await db.delete(skill)
            await db.flush()

            _deleted_namespace = skill.namespace
            _deleted_name = skill.name

        await publish_skill_mutated(
            skill_id=skill_id,
            action="delete",
            namespace=_deleted_namespace,
            name=_deleted_name,
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
            stmt = (
                select(LearnedSkill)
                .where(
                    LearnedSkill.member_id == (_member_id(current_user))
                )
                .where(LearnedSkill.id == skill_id)
            )
            result = await db.execute(stmt)
            skill = result.scalar_one_or_none()

            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")

            if body.name:
                if body.name != skill.name:
                    stmt_check = (
                        select(LearnedSkill)
                        .where(
                            or_(
                                LearnedSkill.member_id == 0,
                                LearnedSkill.member_id
                                == (_member_id(current_user)),
                            )
                        )
                        .where(LearnedSkill.name == body.name)
                    )
                    existing = (await db.execute(stmt_check)).scalar_one_or_none()
                    if existing:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Skill name '{body.name}' already exists",
                        )
                skill.name = body.name

            if body.description:
                skill.description = body.description
            if body.namespace:
                skill.namespace = body.namespace
            if body.instructions is not None:
                skill.instructions = body.instructions
            if body.trigger_patterns is not None:
                skill.trigger_patterns = body.trigger_patterns
            if body.parameters is not None:
                skill.parameters = body.parameters
            if body.preconditions is not None:
                skill.preconditions = body.preconditions

            await db.flush()

        await publish_skill_mutated(skill_id=skill_id, action="update")

        macro = None
        if skill.macro_id:
            from app.models.macro import Macro

            async with session_scope() as db:
                macro = await db.get(Macro, skill.macro_id)

        return UpdateSkillResponse(
            success=True,
            message=f"Skill {skill_id} updated",
            skill=SkillDetailResponse(
                id=skill.id,
                name=skill.name,
                description=skill.description,
                namespace=skill.namespace,
                trigger_patterns=_normalize_json_list(skill.trigger_patterns),
                parameters=_normalize_skill_params(skill.parameters),
                preconditions=_normalize_json_list(skill.preconditions),
                tools_used=_normalize_json_list(skill.tools_used),
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
async def execute_skill(
    skill_id: int,
    body: ExecuteSkillRequest,
    bg_tasks: BackgroundTasks,
    current_user: CurrentUserOptional = None,  # noqa: ARG001
):
    """Execute a skill by injecting a directive into the agent's conversation."""
    async with session_scope() as db:
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        macro = None
        if skill.macro_id:
            from app.models.macro import Macro

            macro = await db.get(Macro, skill.macro_id)

    params = body.params.model_dump()
    if macro is not None:
        try:
            script = preflight(macro, params)
        except MacroGateError as e:
            status = {"not_routable": 403, "missing_params": 400, "bad_macro": 500}.get(
                e.code, 400
            )
            raise HTTPException(status_code=status, detail=e.message) from e

        outcome = await run_deterministic(
            macro,
            thread_id=body.thread_id,
            params=params,
            project_id=body.project_id
            if body.project_id is not None
            else DEFAULT_PROJECT_ID,
            script=script,
            policy=WEB_POLICY,
            skill_name=skill.name,
        )
        if outcome.fell_back:
            return ExecuteSkillResponse(
                success=True,
                message=outcome.message
                or f"Macro failed; self-healing queued for '{skill.name}'",
                execution_mode="deterministic",
            )
        if not outcome.ok:
            raise HTTPException(status_code=500, detail=outcome.message)
        return ExecuteSkillResponse(
            success=True,
            message=outcome.message or f"Executed '{skill.name}'",
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

    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.error)
    if result.inputs is None:
        raise HTTPException(status_code=500, detail="Failed to prepare agent inputs")

    bg_tasks.add_task(run_agent_background, body.thread_id, result.inputs)

    return ExecuteSkillResponse(
        success=True,
        message=f"Agentic execution queued for '{skill_name}'",
        execution_mode="agentic",
    )


@router.get("/skills/{skill_id}/validate", response_model=ValidateSkillResponse)
async def validate_skill(skill_id: int, current_user: CurrentUserOptional = None):  # noqa: ARG001
    """Run the validator on a skill and return its health status."""
    async with session_scope() as db:
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        if not skill.resource_path:
            return ValidateSkillResponse(
                success=False, error="Skill has no resource path (cannot validate)"
            )

        validation = SkillValidator.validate_folder(Path(skill.resource_path))
        skill.validation_report = validation.model_dump()
        skill.status = "verified" if validation.status == "healthy" else "candidate"
        skill.is_active = True

        return ValidateSkillResponse(success=True, validation=validation.model_dump())


@router.post("/skills/{skill_id}/confirm", response_model=BaseAPIResponse)
async def confirm_learned_skill(
    skill_id: int, current_user: CurrentUserOptional = None
):
    """User confirms a synthesized skill. Updates status from pending_review to verified."""
    async with session_scope() as db:
        stmt = (
            select(LearnedSkill)
            .where(LearnedSkill.member_id == (_member_id(current_user)))
            .where(LearnedSkill.id == skill_id)
        )
        skill = (await db.execute(stmt)).scalar_one_or_none()

        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        if skill.status != "pending_review":
            raise HTTPException(
                status_code=400,
                detail=f"Skill is not in pending_review status (current: {skill.status})",
            )

        skill.status = "verified"
        skill.is_active = True

        if skill.macro_id:
            from app.models.macro import Macro

            macro = await db.get(Macro, skill.macro_id)
            if macro is not None:
                macro.status = "verified"
                macro.is_active = True

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
            macro = await create_macro_from_synthesis(
                db,
                name=skill.name,
                description=skill.description,
                trigger_patterns=skill.trigger_patterns,
                parameters=normalize_parameters(skill.parameters),
                macro_script=body.yaml_content,
                fallback_skill_id=skill.id,
                project_id=body.project_id,
                member_id=_member_id(current_user),
            )
            skill.macro_id = macro.id

        await publish_skill_mutated(skill_id=skill.id, action="create")

        return CreateSkillFromYamlResponse(
            success=True,
            skill_id=skill.id,
            skill_name=skill.name,
            step_count=len(macro_steps),
        )
    except YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML error: {str(e)}")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.exception(f"Failed to create skill from YAML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create skill: {str(e)}")


@router.post("/skills/validate-yaml", response_model=ValidateYamlResponse)
async def validate_skill_yaml(
    body: ValidateYamlRequest, current_user: CurrentUserOptional = None  # noqa: ARG001
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
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        return ValidateYamlResponse(valid=False, errors=[str(e)], step_count=0)


@router.get("/skills/{skill_id}/yaml")
async def get_skill_yaml(skill_id: int, current_user: CurrentUserOptional = None):  # noqa: ARG001
    """Get skill macro as YAML format."""
    async with session_scope() as db:
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        if not skill.macro_id:
            return Response(
                content="# No macro script defined for this skill\n",
                media_type="text/yaml",
            )

        from app.models.macro import Macro

        macro = await db.get(Macro, skill.macro_id)
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
            skill = await db.get(LearnedSkill, skill_id)
            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")

            from app.models.macro import Macro

            if skill.macro_id:
                macro = await db.get(Macro, skill.macro_id)
                if macro is not None:
                    macro.macro_script = yaml_content
            else:
                macro = await create_macro_from_synthesis(
                    db,
                    name=skill.name,
                    description=skill.description,
                    trigger_patterns=skill.trigger_patterns,
                    parameters=normalize_parameters(skill.parameters),
                    macro_script=yaml_content,
                    fallback_skill_id=skill.id,
                    member_id=_member_id(current_user),
                )
                skill.macro_id = macro.id

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
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.exception(f"Failed to update skill from YAML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update: {str(e)}")
    finally:
        await skill_discovery.reload()
