"""
Mock/Stub base classes providing native callback base classes.
"""



class AsyncCallbackHandler:
    """Mock/Stub base class providing a native AsyncCallbackHandler."""

    async def on_llm_start(self, *args, **kwargs) -> None:
        pass

    async def on_llm_end(self, *args, **kwargs) -> None:
        pass

    async def on_llm_new_token(self, *args, **kwargs) -> None:
        pass

    async def on_tool_start(self, *args, **kwargs) -> None:
        pass

    async def on_tool_end(self, *args, **kwargs) -> None:
        pass

    async def on_tool_error(self, *args, **kwargs) -> None:
        pass

    async def on_chain_start(self, *args, **kwargs) -> None:
        pass

    async def on_chain_end(self, *args, **kwargs) -> None:
        pass

    async def on_chain_error(self, *args, **kwargs) -> None:
        pass


class LLMResult:
    """Mock/Stub class providing a native LLMResult."""

    def __init__(self, *args, **kwargs):
        pass
