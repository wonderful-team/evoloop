from fastapi import APIRouter
from app.api.routes import login, users, utils, agent, projects, mcp, files, history, member, memory, planning
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)


api_router.include_router(agent.router, tags=["agent"]) # agent.py defines /chat, /webhook
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(history.router, prefix="/history", tags=["history"])
api_router.include_router(member.router, prefix="/member", tags=["member"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(planning.router, prefix="/planning", tags=["planning"])
