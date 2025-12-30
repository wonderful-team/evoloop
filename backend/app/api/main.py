from fastapi import APIRouter
from app.api.routes import login, users, utils, agent, projects, mcp, files, history, member, memory, planning, symbols, system, devices
from app.core.config import settings
from app.api.routes import tasks, project_modules

api_router = APIRouter()
# Login handled by member center (proxied)
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)


api_router.include_router(agent.router, tags=["agent"]) # agent.py defines /chat, /webhook
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(history.router, prefix="/history", tags=["history"])
api_router.include_router(member.router, prefix="/member", tags=["member"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(planning.router, prefix="/planning", tags=["planning"])
api_router.include_router(symbols.router, tags=["symbols"])
api_router.include_router(system.router)

# Project Management Modules (Proxy)
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(project_modules.router, prefix="/project-modules", tags=["project-modules"])
