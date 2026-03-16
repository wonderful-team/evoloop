from fastapi import APIRouter

from app.api.routes import (
    agent,
    auth_proxy,
    brain,
    conversations,
    devices,
    files,
    learning,
    library,
    login,
    mcp,
    member,
    memory,
    planning,
    project_modules,
    project_requirements,
    projects,
    resources,
    stream,
    symbols,
    system,
    tasks,
    todos,
    tools,
    users,
    utils,
    wechat_auth,
    wiki,
)

api_router = APIRouter()
# Login handled by member center (proxied)
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(auth_proxy.router, prefix="/auth", tags=["auth"])
api_router.include_router(wechat_auth.router, tags=["wechat-auth"])


api_router.include_router(agent.router, tags=["agent"])  # agent.py defines /chat, /webhook
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(project_requirements.router, tags=["project-requirements"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(member.router, prefix="/member", tags=["member"])
api_router.include_router(library.router, prefix="/library", tags=["library"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(planning.router, prefix="/planning", tags=["planning"])
api_router.include_router(symbols.router, tags=["symbols"])
api_router.include_router(tools.router, tags=["tools"])
api_router.include_router(system.router)
api_router.include_router(resources.router)

# Project Management Modules (Proxy)
api_router.include_router(tasks.router, prefix="/tasks")
api_router.include_router(todos.router, prefix="/todos", tags=["todos"])
api_router.include_router(project_modules.router, prefix="/project-modules", tags=["project-modules"])

# Learning & Human-in-Loop (Phase 0.2)
api_router.include_router(learning.router, prefix="/learning", tags=["learning"])

# SSE Streaming
api_router.include_router(stream.router, tags=["stream"])

# Wiki Generation
api_router.include_router(wiki.router, prefix="/wiki", tags=["wiki"])

# Cognitive Brain (Flash Mode)
api_router.include_router(brain.router, prefix="/brain", tags=["brain"])
