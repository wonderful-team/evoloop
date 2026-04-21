"""
API routes for project profile discovery.

Discovery is Agent-driven: the API creates an Agent Mission that lets
the Agent explore, initialize, and document the project itself.
"""
import logging
import os
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.deps import TokenDepOptional
from app.api.responses import BaseAPIResponse
from app.core.engine.background_agent import run_agent_background
from app.core.engine.dispatch import dispatch_agent_run
from app.core.evocloud import evocloud_manager
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils import file as file_utils

logger = logging.getLogger(__name__)

router = APIRouter(tags=["project-profiles"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class DiscoverRequest(DynamicBaseModel):
    record_secrets: bool = False


class DiscoverResponse(BaseAPIResponse):
    status: str
    project_id: int
    thread_id: str


class ProfileContentResponse(BaseAPIResponse):
    content: str | None = None
    exists: bool = False


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _resolve_project_path(project_id: int) -> str:
    """
    Resolve local project path from project_id.

    Resolution order:
    1. Cloud API (evocloud_manager.get_project_by_id) → project.path
    2. Local DB (Repository table) → repo.local_path
    """
    # 1. Try Cloud API
    try:
        project = await evocloud_manager.get_project_by_id(project_id)
        if project and project.path and os.path.isdir(project.path):
            return project.path
    except Exception as e:
        logger.debug(f"[ProjectProfiles] Cloud lookup failed for {project_id}: {e}")

    # 2. Try local DB
    try:
        from sqlalchemy import select
        from app.infrastructure.database.sql.database import AsyncSessionLocal
        from app.models.codebase import Repository

        async with AsyncSessionLocal() as session:
            stmt = select(Repository).where(Repository.project_id == project_id)
            result = await session.execute(stmt)
            repo = result.scalar_one_or_none()
            if repo and repo.local_path and os.path.isdir(repo.local_path):
                return repo.local_path
    except Exception as e:
        logger.debug(f"[ProjectProfiles] DB lookup failed for {project_id}: {e}")

    return ""


def _build_discovery_message(path: str, record_secrets: bool) -> str:
    """Build the mission message for the Agent to explore and document the project."""
    return f"""Please explore and initialize this project at `{path}`.

Your tasks:
1. **Explore** the project structure using `list_directory` and `read_file`
2. **Identify** the project type, tech stack, and dependencies
3. **Set up** the development environment by running appropriate install commands via `execute_command` (e.g. npm install, pip install, poetry install, docker-compose up -d, etc.)
4. **Generate** a PROJECT.md file at the project root using `write_file` with the following sections:

```markdown
# Project Name

## Overview
Brief project description (2-3 sentences).

## Technology Stack
- Languages:
- Frameworks:
- Runtime:
- Package Manager:

## Project Structure
Key directories and their purposes.

## Development Setup
### Prerequisites
### Installation
### Running Locally

## Conventions & Guidelines
- Coding style
- Naming conventions
- Branch strategy
- Commit message format

## Infrastructure Dependencies
- Services required (DB, Redis, Message Queue, etc.)
- Port assignments
- Docker Compose services (if applicable)

## Environment Variables
{'List of required env vars with their actual values (user opted to record secrets).' if record_secrets else 'List of required env vars (names and descriptions only — no values).'}

## Testing
How to run tests.

## Build & Deploy
- Build commands
- Deployment process
```

Rules:
- {'Include actual secret values from .env files because the user opted to record secrets.' if record_secrets else 'NEVER include secret values. Only list variable names.'}
- Be specific about commands: exact npm/poetry/docker commands where known.
- Focus on agent-relevant info: what does the AI need to know to edit/build/run this project?
- Write in the same language as the project's README (default to English).
"""


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/{project_id}/profile/discover", response_model=DiscoverResponse)
async def discover_profile(
    project_id: int,
    req: DiscoverRequest,
    bg_tasks: BackgroundTasks,
    _token: TokenDepOptional = None,
):
    """
    Trigger Agent-driven project discovery.

    Dispatches an Agent Mission to explore the project, set up the environment,
    and generate PROJECT.md. Returns a thread_id for SSE streaming.
    """
    path = await _resolve_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")
    if not os.path.isdir(path):
        raise HTTPException(400, f"Project path does not exist: {path}")

    thread_id = f"discovery-{project_id}-{int(time.time())}"
    message = _build_discovery_message(path, req.record_secrets)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        goal_prefix="[Project Discovery] ",
    )

    if result.status == "failed":
        raise HTTPException(500, detail=result.error)

    bg_tasks.add_task(run_agent_background, thread_id, result.inputs)

    logger.info(
        f"[ProjectProfilesAPI] Dispatched discovery mission for project {project_id} "
        f"(thread_id={thread_id})"
    )

    return DiscoverResponse(
        status="queued",
        project_id=project_id,
        thread_id=thread_id,
    )


@router.get("/{project_id}/profile", response_model=ProfileContentResponse)
async def get_profile(
    project_id: int,
    _token: TokenDepOptional = None,
):
    """Get the current PROJECT.md content for a project."""
    path = await _resolve_project_path(project_id)
    if not path:
        raise HTTPException(404, "Project not found or has no local path")

    file_path = os.path.join(path, "PROJECT.md")
    content = None
    if os.path.isfile(file_path):
        try:
            content = file_utils.read_file(file_path)
        except Exception as e:
            logger.warning(f"Failed to read PROJECT.md: {e}")

    return ProfileContentResponse(
        content=content,
        exists=content is not None,
    )
