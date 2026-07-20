from fastapi import APIRouter

from app.api.routes import (
    account,
    agent,
    atlas,
    auth_proxy,
    conversations,
    devices,
    files,
    learning,
    macros,
    mcp,
    member,
    memory,
    planning,
    projects,
    resources,
    route,
    stream,
    subscription,
    subtasks,
    symbols,
    system,
    tasks,
    todos,
    tools,
    utils,
    vault,
    models,
    voice_ws,
    wiki,
)

api_router = APIRouter()
# Account & Auth logic (Username, Mobile, WeChat, Logout)
api_router.include_router(account.router)


api_router.include_router(agent.router, tags=["agent"])  # agent.py defines /chat, /webhook
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
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
api_router.include_router(vault.router)

# Project Management Modules (Proxy)
api_router.include_router(tasks.router, prefix="/tasks")
api_router.include_router(todos.router, prefix="/todos", tags=["todos"])
api_router.include_router(subtasks.router, tags=["subtasks"])
api_router.include_router(projects.modules_router, prefix="/project-modules", tags=["project-modules"])

# Code Module Graph (Leiden)
from app.api.routes.modules import router as code_modules_router
api_router.include_router(code_modules_router, prefix="/api/v1", tags=["code-modules"])

# Learning & Human-in-Loop (Phase 0.2)
api_router.include_router(learning.router, prefix="/learning", tags=["learning"])

# SSE Streaming
api_router.include_router(stream.router, tags=["stream"])

# Wiki Generation
api_router.include_router(wiki.router, prefix="/wiki", tags=["wiki"])

# Voice assistant (thin-client VLA): WebSocket + Init Spec / diagnostics
api_router.include_router(voice_ws.router)
api_router.include_router(models.router)
api_router.include_router(route.router, prefix="/route", tags=["route"])

# Atlas AppMap + Macro library
api_router.include_router(atlas.router, prefix="/atlas", tags=["atlas"])
api_router.include_router(macros.router, prefix="/macros", tags=["macros"])
