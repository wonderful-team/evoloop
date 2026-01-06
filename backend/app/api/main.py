from fastapi import APIRouter
from app.api.routes import login, users, utils, agent, projects, mcp, files, conversations, member, memory, planning, symbols, system, devices, tools, stream, learning, resources, auth_proxy
from app.core.config import settings
from app.api.routes import tasks, project_modules

api_router = APIRouter()
# Login handled by member center (proxied)
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(auth_proxy.router, prefix="/auth", tags=["auth"])


api_router.include_router(agent.router, tags=["agent"]) # agent.py defines /chat, /webhook
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(member.router, prefix="/member", tags=["member"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(planning.router, prefix="/planning", tags=["planning"])
api_router.include_router(symbols.router, tags=["symbols"])
api_router.include_router(tools.router, tags=["tools"])
api_router.include_router(system.router)
api_router.include_router(resources.router)

# Project Management Modules (Proxy)
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(project_modules.router, prefix="/project-modules", tags=["project-modules"])

# Learning & Human-in-Loop (Phase 0.2)
api_router.include_router(learning.router, prefix="/learning", tags=["learning"])

# SSE Streaming
api_router.include_router(stream.router, tags=["stream"])

