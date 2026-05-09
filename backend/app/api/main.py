from fastapi import APIRouter

from app.api.routes import (
    account,
    agent,
    audio,
    auth_proxy,
    conversations,
    devices,
    files,
    knowledge,
    learning,
    mcp,
    member,
    memory,
    planning,
    project_modules,
    project_profiles,
    projects,
    resources,
    stream,
    subscription,
    subtasks,
    symbols,
    system,
    tasks,
    todos,
    tools,
    utils,
    wiki,
)

api_router = APIRouter()
# Account & Auth logic (Username, Mobile, WeChat, Logout)
api_router.include_router(account.router)


api_router.include_router(agent.router, tags=["agent"])  # agent.py defines /chat, /webhook
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(project_profiles.router, prefix="/projects", tags=["project-profiles"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(member.router, prefix="/member", tags=["member"])
api_router.include_router(subscription.router, prefix="/member")
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(planning.router, prefix="/planning", tags=["planning"])
api_router.include_router(symbols.router, tags=["symbols"])
api_router.include_router(tools.router, tags=["tools"])
api_router.include_router(system.router)
api_router.include_router(utils.router)
api_router.include_router(auth_proxy.router, prefix="/auth", tags=["auth"])
api_router.include_router(resources.router)

# Project Management Modules (Proxy)
api_router.include_router(tasks.router, prefix="/tasks")
api_router.include_router(todos.router, prefix="/todos", tags=["todos"])
api_router.include_router(subtasks.router, tags=["subtasks"])
api_router.include_router(project_modules.router, prefix="/project-modules", tags=["project-modules"])

# Learning & Human-in-Loop (Phase 0.2)
api_router.include_router(learning.router, prefix="/learning", tags=["learning"])

# SSE Streaming
api_router.include_router(stream.router, tags=["stream"])

# Wiki Generation
api_router.include_router(wiki.router, prefix="/wiki", tags=["wiki"])

# Audio Processing (Voice Messages)
api_router.include_router(audio.router, prefix="/audio", tags=["audio"])

# Knowledge Base (Phase 1)
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
