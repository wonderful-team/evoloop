from fastapi import APIRouter

from app.api.routes import items, login, private, users, utils, agent, projects, mcp, files, history, member
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)


api_router.include_router(items.router)
api_router.include_router(agent.router, prefix="/agent", tags=["agent"]) # or root? server.py had /chat at root. 
# Template uses /api/v1 prefix for api_router.
# If I want /chat to be at /api/v1/chat, I include it here.
api_router.include_router(agent.router, tags=["agent"]) # agent.py defines /chat, /webhook
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(history.router, prefix="/history", tags=["history"])
api_router.include_router(member.router, prefix="/member", tags=["member"])


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
