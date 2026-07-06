"""Skills sub-router — skill CRUD, validation, YAML import/export, execution."""
import json
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
from app.core.learning.skill_synthesizer import WorkflowSynthesizer
from app.core.learning.skill_validator import SkillValidator
from app.infrastructure.database import session_scope
from app.models import LearnedSkill
from app.utils.template import render_template
from app.utils.yaml import YAMLError, macro_from_yaml, validate_macro_yaml

from ._shared import _normalize_skill_params, execute_macro_with_fallback

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/skills/synthesize", response_model=SynthesizeSkillResponse, dependencies=[Depends(require_benefit("skill_learning"))])
async def synthesize_skill(body: SynthesizeRequest, current_user: CurrentUserOptional = None):
    """Synthesize a new skill from a trace sequence."""
    try:
        synthesizer = WorkflowSynthesizer(body.thread_id, body.session_id)
        skill = await synthesizer.synthesize(auto_optimize=body.auto_optimize)

        async with session_scope() as db:
            base_name = skill.name
            unique_name = base_name
            counter = 1

            while True:
                stmt = select(LearnedSkill).where(or_(LearnedSkill.member_id == 0, LearnedSkill.member_id == (current_user.id if current_user else 0))).where(LearnedSkill.name == unique_name)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if not existing:
                    break
                unique_name = f"{base_name}_{counter}"
                counter += 1

            if unique_name != base_name:
                logger.info(f"Skill name collision: {base_name} -> {unique_name}")

            db_skill = LearnedSkill(member_id=current_user.id if current_user else 0,
                name=unique_name,
                description=skill.description,
                trigger_patterns=json.dumps(skill.trigger_patterns),
                parameters=json.dumps([p.__dict__ for p in skill.parameters]),
                preconditions=json.dumps(skill.preconditions),
                tools_used=json.dumps(skill.tools_used),
                source_thread_id=skill.source_thread_id,
                source_session_id=skill.source_session_id,
                is_active=False,
                status="pending_review",
                instructions=skill.instructions,
                execution_mode=skill.execution_mode,
                macro_script=skill.macro_script,
            )
            db.add(db_skill)
            await db.flush()

        await publish_skill_mutated(skill_id=db_skill.id, action="create")

        return SynthesizeSkillResponse(
            success=True,
            skill_id=db_skill.id,
            skill_name=unique_name,
            skill_yaml=skill.to_yaml(),
        )

    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.exception(f"Skill synthesis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")
    finally:
        await skill_discovery.reload()


@router.post("/skills/import", response_model=ImportSkillsResponse, dependencies=[Depends(require_benefit("skill_learning"))])
async def import_skills(body: ImportSkillsRequest):
    """Bulk import skills from a local directory."""
    try:
        results = await SkillImporter.import_from_directory(body.directory)
        return ImportSkillsResponse(success=True, results=results.model_dump())
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.exception(f"Skill import failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    finally:
        await skill_discovery.reload()


@router.get("/skills", response_model=PaginatedSkillsResponse)
async def list_skills(
    active_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: CurrentUserOptional = None):
    """List all learned skills with pagination."""
    try:
        await skill_discovery._sync_system_skills()
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Background skill sync failed during list: {e}")

    async with session_scope() as db:
        stmt = select(LearnedSkill).where(or_(LearnedSkill.member_id == 0, LearnedSkill.member_id == (current_user.id if current_user else 0)))
        if active_only:
            stmt = stmt.where(LearnedSkill.is_active == True)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(LearnedSkill.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        skills = result.scalars().all()

        total_pages = math.ceil(total / page_size) if page_size > 0 else 0

        return PaginatedSkillsResponse(
            data=[
                SkillDTO(
                    id=s.id,
                    name=s.name,
                    description=s.description,
                    namespace=s.namespace,
                    trigger_patterns=json.loads(s.trigger_patterns) if s.trigger_patterns else [],
                    parameters=_normalize_skill_params(s.parameters),
                    tools_used=json.loads(s.tools_used) if s.tools_used else [],
                    success_count=s.success_count,
                    failure_count=s.failure_count,
                    is_active=s.is_active,
                    status=s.status,
                    execution_mode=s.execution_mode,
                    macro_script=s.macro_script or "",
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
            total_pages=total_pages,
        )


@router.get("/skills/{skill_id}", response_model=SkillDetailResponse)
async def get_skill(skill_id: int, current_user: CurrentUserOptional = None):
    """Get full details of a specific skill."""
    async with session_scope() as db:
        stmt = select(LearnedSkill).where(or_(LearnedSkill.member_id == 0, LearnedSkill.member_id == (current_user.id if current_user else 0))).where(LearnedSkill.id == skill_id)
        result = await db.execute(stmt)
        skill = result.scalar_one_or_none()

        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        return SkillDetailResponse(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            namespace=skill.namespace,
            trigger_patterns=json.loads(skill.trigger_patterns) if skill.trigger_patterns else [],
            parameters=_normalize_skill_params(skill.parameters),
            preconditions=json.loads(skill.preconditions) if skill.preconditions else [],
            tools_used=json.loads(skill.tools_used) if skill.tools_used else [],
            source_thread_id=skill.source_thread_id,
            source_session_id=skill.source_session_id,
            success_count=skill.success_count,
            failure_count=skill.failure_count,
            is_active=skill.is_active,
            status=skill.status,
            execution_mode=skill.execution_mode,
            macro_script=skill.macro_script or "",
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
            stmt = select(LearnedSkill).where(LearnedSkill.member_id == (current_user.id if current_user else 0)).where(LearnedSkill.id == skill_id)
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
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.error(f"Failed to delete skill resources at {skill.resource_path}: {e}")

            await db.delete(skill)
            await db.flush()

            _deleted_namespace = skill.namespace
            _deleted_name = skill.name

        await publish_skill_mutated(
            skill_id=skill_id, action="delete",
            namespace=_deleted_namespace, name=_deleted_name,
        )

        return BaseAPIResponse(success=True, message=f"Skill {skill_id} physically deleted")
    finally:
        await skill_discovery.reload()


@router.put("/skills/{skill_id}", response_model=UpdateSkillResponse)
async def update_skill(skill_id: int, body: UpdateSkillRequest, current_user: CurrentUserOptional = None):
    """Update a learned skill."""
    try:
        async with session_scope() as db:
            stmt = select(LearnedSkill).where(LearnedSkill.member_id == (current_user.id if current_user else 0)).where(LearnedSkill.id == skill_id)
            result = await db.execute(stmt)
            skill = result.scalar_one_or_none()

            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")

            if body.name:
                if body.name != skill.name:
                    stmt_check = select(LearnedSkill).where(or_(LearnedSkill.member_id == 0, LearnedSkill.member_id == (current_user.id if current_user else 0))).where(LearnedSkill.name == body.name)
                    existing = (await db.execute(stmt_check)).scalar_one_or_none()
                    if existing:
                        raise HTTPException(status_code=400, detail=f"Skill name '{body.name}' already exists")
                skill.name = body.name

            if body.description:
                skill.description = body.description
            if body.namespace:
                skill.namespace = body.namespace
            if body.instructions is not None:
                skill.instructions = body.instructions
            if body.trigger_patterns is not None:
                skill.trigger_patterns = json.dumps(body.trigger_patterns)
            if body.parameters is not None:
                skill.parameters = json.dumps(body.parameters)
            if body.preconditions is not None:
                skill.preconditions = json.dumps(body.preconditions)
            if body.execution_mode is not None:
                skill.execution_mode = body.execution_mode
            if body.macro_script is not None:
                try:
                    macro_from_yaml(body.macro_script)
                    skill.macro_script = body.macro_script
                except YAMLError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

            await db.flush()

        await publish_skill_mutated(skill_id=skill_id, action="update")

        return UpdateSkillResponse(
            success=True,
            message=f"Skill {skill_id} updated",
            skill=SkillDetailResponse(
                id=skill.id,
                name=skill.name,
                description=skill.description,
                namespace=skill.namespace,
                trigger_patterns=json.loads(skill.trigger_patterns) if skill.trigger_patterns else [],
                parameters=json.loads(skill.parameters) if skill.parameters else [],
                preconditions=json.loads(skill.preconditions) if skill.preconditions else [],
                tools_used=json.loads(skill.tools_used) if skill.tools_used else [],
                source_thread_id=skill.source_thread_id,
                source_session_id=skill.source_session_id,
                success_count=skill.success_count,
                failure_count=skill.failure_count,
                is_active=skill.is_active,
                status=skill.status,
                execution_mode=skill.execution_mode,
                macro_script=skill.macro_script or "",
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
    skill_id: int, body: ExecuteSkillRequest, bg_tasks: BackgroundTasks, current_user: CurrentUserOptional = None):
    """Execute a skill by injecting a directive into the agent's conversation."""
    async with session_scope() as db:
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        skill_name = skill.name
        params_str = json.dumps(body.params.model_dump(), indent=2)
        directive = render_template(
            "core/learning/skill_directive.prompt.j2",
            skill_name=skill_name,
            parameters=body.params.model_dump(),
        )

    execution_mode = body.execution_mode or skill.execution_mode

    if execution_mode == "deterministic" and skill.macro_script:
        import copy
        try:
            macro_steps = macro_from_yaml(skill.macro_script)
        except YAMLError as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse macro YAML: {e}")

        macro_payload = copy.deepcopy(macro_steps)
        bg_tasks.add_task(
            execute_macro_with_fallback,
            thread_id=body.thread_id,
            project_id=body.project_id if body.project_id is not None else DEFAULT_PROJECT_ID,
            skill=skill,
            macro_payload=macro_payload,
            params=body.params
        )
        return ExecuteSkillResponse(success=True, message=f"Deterministic Macro execution queued for '{skill_name}'", execution_mode=execution_mode)
    else:
        result = await dispatch_agent_run(
            thread_id=body.thread_id,
            message_content=directive,
            project_id=body.project_id if body.project_id is not None else DEFAULT_PROJECT_ID,
            metadata={"goal_prefix": f"[Skill: {skill_name}] "},
        )

        if result.status == "failed":
            raise HTTPException(status_code=500, detail=result.error)

        bg_tasks.add_task(run_agent_background, body.thread_id, result.inputs)

        return ExecuteSkillResponse(success=True, message=f"Agentic execution queued for '{skill_name}'", execution_mode=execution_mode)


@router.get("/skills/{skill_id}/validate", response_model=ValidateSkillResponse)
async def validate_skill(skill_id: int, current_user: CurrentUserOptional = None):
    """Run the validator on a skill and return its health status."""
    async with session_scope() as db:
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        if not skill.resource_path:
            return ValidateSkillResponse(success=False, error="Skill has no resource path (cannot validate)")

        validation = SkillValidator.validate_folder(Path(skill.resource_path))
        skill.validation_report = validation.model_dump()
        skill.status = "verified" if validation.status == "healthy" else "candidate"

        return ValidateSkillResponse(success=True, validation=validation.model_dump())


@router.post("/skills/{skill_id}/confirm", response_model=BaseAPIResponse)
async def confirm_learned_skill(skill_id: int, current_user: CurrentUserOptional = None):
    """User confirms a synthesized skill. Updates status from pending_review to verified."""
    async with session_scope() as db:
        stmt = select(LearnedSkill).where(LearnedSkill.member_id == (current_user.id if current_user else 0)).where(LearnedSkill.id == skill_id)
        skill = (await db.execute(stmt)).scalar_one_or_none()

        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        if skill.status != "pending_review":
            raise HTTPException(
                status_code=400,
                detail=f"Skill is not in pending_review status (current: {skill.status})"
            )

        skill.status = "verified"
        skill.is_active = True

        logger.info(f"Skill {skill.id} ({skill.name}) confirmed by user.")

    await publish_skill_mutated(skill_id=skill_id, action="update")

    return BaseAPIResponse(
        success=True,
        message=f"Skill '{skill.name}' confirmed and activated."
    )


# ============ YAML Macro Support ============

@router.post("/skills/from-yaml", response_model=CreateSkillFromYamlResponse)
async def create_skill_from_yaml(
    body: CreateSkillFromYamlRequest,
    bg_tasks: BackgroundTasks, current_user: CurrentUserOptional = None):
    """Create a new skill from YAML macro definition."""
    try:
        is_valid, errors = validate_macro_yaml(body.yaml_content)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid YAML format: {'; '.join(errors)}")

        macro_script = macro_from_yaml(body.yaml_content)

        async with session_scope() as db:
            base_name = body.name
            unique_name = base_name
            counter = 1

            while True:
                stmt = select(LearnedSkill).where(or_(LearnedSkill.member_id == 0, LearnedSkill.member_id == (current_user.id if current_user else 0))).where(LearnedSkill.name == unique_name)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if not existing:
                    break
                unique_name = f"{base_name}_{counter}"
                counter += 1

            skill = LearnedSkill(member_id=current_user.id if current_user else 0,
                name=unique_name,
                description=body.description or f"Created from YAML ({len(macro_script)} steps)",
                namespace=body.namespace,
                macro_script=macro_script,
                execution_mode="deterministic",
                is_active=False,
                status="pending_review",
                trigger_patterns=json.dumps([unique_name.lower().replace(" ", "_")]),
                parameters=json.dumps([]),
                tools_used=json.dumps([]),
            )
            db.add(skill)
            await db.flush()

        await publish_skill_mutated(skill_id=skill.id, action="create")

        return CreateSkillFromYamlResponse(
            success=True,
            skill_id=skill.id,
            skill_name=unique_name,
            step_count=len(macro_script),
        )
    except YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML error: {str(e)}")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.exception(f"Failed to create skill from YAML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create skill: {str(e)}")


@router.post("/skills/validate-yaml", response_model=ValidateYamlResponse)
async def validate_skill_yaml(body: ValidateYamlRequest, current_user: CurrentUserOptional = None):
    """Validate YAML macro format without creating a skill."""
    try:
        is_valid, errors = validate_macro_yaml(body.yaml_content)
        step_count = 0
        if is_valid:
            steps = macro_from_yaml(body.yaml_content)
            step_count = len(steps)

        return ValidateYamlResponse(valid=is_valid, errors=errors, step_count=step_count)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        return ValidateYamlResponse(valid=False, errors=[str(e)], step_count=0)


@router.get("/skills/{skill_id}/yaml")
async def get_skill_yaml(skill_id: int, current_user: CurrentUserOptional = None):
    """Get skill macro as YAML format."""
    async with session_scope() as db:
        skill = await db.get(LearnedSkill, skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        if not skill.macro_script:
            return Response(content="# No macro script defined for this skill\n", media_type="text/yaml")

        return Response(content=skill.macro_script, media_type="text/yaml")


@router.put("/skills/{skill_id}/yaml", response_model=UpdateSkillFromYamlResponse)
async def update_skill_yaml(
    skill_id: int,
    yaml_content: str = Body(..., media_type="text/yaml"),
    current_user: CurrentUserOptional = None):
    """Update skill macro from YAML content."""
    try:
        is_valid, errors = validate_macro_yaml(yaml_content)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid YAML: {'; '.join(errors)}")

        async with session_scope() as db:
            skill = await db.get(LearnedSkill, skill_id)
            if not skill:
                raise HTTPException(status_code=404, detail="Skill not found")

            skill.macro_script = yaml_content
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
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.exception(f"Failed to update skill from YAML: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update: {str(e)}")
    finally:
        await skill_discovery.reload()


# Need math import for list_skills
import math  # noqa: E402
