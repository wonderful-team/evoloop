import asyncio
import logging
import os
import sys
import uuid
from rich.console import Console

# Add backend path to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.engine.dispatch import dispatch_agent_run
from app.core.engine.background_agent import run_agent_background
from app.infrastructure.database.resource_manager import db_resource_manager
from app.core.engine.graph_builder import GraphBuilder
from app.core.globals import set_graph
from app.core.events.discovery import auto_discover_handlers
from app.core.memory.lifespan import MemoryLifespanManager

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("audit-validator")
console = Console()

async def run_audit_validation():
    # 1. Initialize Persistence Layer
    await db_resource_manager.initialize()
    checkpointer = db_resource_manager.checkpointer
    
    # 2. Initialize Memory System (registers extraction subscribers)
    await MemoryLifespanManager.ainitialize()
    
    # 3. Initialize Graph and Discovery
    auto_discover_handlers()
    builder = GraphBuilder()
    
    # Correct path to agent_main.yaml
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "app/core/engine/config/agent_main.yaml")
    
    # IMPORTANT: Pass the checkpointer to maintain history!
    graph = builder.build(config_path=config_path, checkpointer=checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=checkpointer)
    
    # Generate a unique thread_id for this audit session
    thread_id = f"audit-val-{uuid.uuid4().hex[:8]}"
    project_id = 43
    
    # We include a 'Strategic Delta' - information not in code/README
    questions = [
        "你好，请简要介绍一下 evoloop-backend 项目的目录结构。",
        "这是一个非常重要的技术决策：对于本项目的数据库 Schema，我们必须严格遵守：所有 JSON 字段必须使用 'meta_data' 而不是 'metadata'，因为 SQLAlchemy 的 Declarative API 会保留 'metadata' 关键字。请务必记住这一点，并在未来的开发中严格执行。",
        "刚才提到的关于 meta_data 的命名规范，为什么我们要这么做？",
        "结束本次对话。请反思并总结我们讨论的技术决策，特别是关于数据库命名的核心规范，并将其作为长期记忆沉淀下来。"
    ]
    
    console.print(f"\n[bold green]🚀 Starting Persistent Strategic Audit Validation (Thread: {thread_id})[/bold green]\n")
    
    for i, q in enumerate(questions):
        console.print(f"[bold blue]Turn {i+1}: {q}[/bold blue]")
        
        # Dispatch
        result = await dispatch_agent_run(
            thread_id=thread_id,
            project_id=project_id,
            message_content=q,
            model="kimi-k2-thinking-turbo"
        )
        
        # Run background
        await run_agent_background(
            thread_id=thread_id,
            inputs=result.inputs
        )
        
        console.print(f"✅ Turn {i+1} completed.\n")

    # Give enough time for background extraction (Thinking models are SLOW)
    # 120s is safer for thinking models
    console.print("\n[bold yellow]⏳ Waiting for background tasks (memory extraction) to complete (120s)...[/bold yellow]")
    await asyncio.sleep(120)

    console.print("\n[bold green]✨ All turns completed. Now running deep audit...[/bold green]\n")
    
    # Run the audit script directly
    from audit_deep_dive import audit_database
    await audit_database()
    
    await MemoryLifespanManager.shutdown()
    await db_resource_manager.shutdown()

if __name__ == "__main__":
    asyncio.run(run_audit_validation())
