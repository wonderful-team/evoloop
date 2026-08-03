"""Capabilities sub-router — action registry export."""

from fastapi import APIRouter

from app.api.deps import CurrentUserOptional
from app.core.environment.capabilities.registry import ActionDef, ActionRegistry

router = APIRouter()


@router.get("/capabilities/actions", response_model=list[ActionDef])
async def get_action_registry(current_user: CurrentUserOptional = None):
    """Export the centralized action registry for frontend sync."""
    return ActionRegistry.list_actions()
