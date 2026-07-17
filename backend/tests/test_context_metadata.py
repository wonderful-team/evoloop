import asyncio
from app.core.context.manager import ContextManager, EvoContext
from app.core.context.schemas import ContextMetadata

async def test():
    ctx = EvoContext(request_id="test")
    ContextManager.set(ctx)
    ctx.metadata.node_source = "supervisor"
    print("Before:", ctx.metadata.node_source)
    
    # simulate engine.run_node
    c2 = ContextManager.current()
    c2.metadata.node_source = "finish"
    
    print("After:", ctx.metadata.node_source)
    print("After c2:", c2.metadata.node_source)

asyncio.run(test())
