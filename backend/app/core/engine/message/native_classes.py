"""
Native, SDK-free message class definitions providing native message classes.
"""

from typing import Any, Union

from pydantic import BaseModel, Field


class RunnableConfig(dict):
    """Mock RunnableConfig class providing a native RunnableConfig."""
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema
        return core_schema.dict_schema()


class BaseMessage(BaseModel):
    """Base class for native messages."""
    content: Union[str, list[Any]]
    id: str | None = None
    additional_kwargs: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

    model_config = {
        "arbitrary_types_allowed": True,
        "extra": "allow"
    }

    def __init__(self, content: Any, id: str = None, additional_kwargs: dict = None, metadata: dict = None, **kwargs: Any):
        super().__init__(
            content=content,
            id=id,
            additional_kwargs=additional_kwargs or {},
            metadata=metadata or {},
            **kwargs
        )
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(content={self.content!r}, id={self.id!r})"


class SystemMessage(BaseMessage):
    type: str = "system"


class HumanMessage(BaseMessage):
    type: str = "human"
    name: str | None = None

    def __init__(self, content: Any, name: str = None, id: str = None, additional_kwargs: dict = None, metadata: dict = None, **kwargs: Any):
        super().__init__(content, id, additional_kwargs, metadata, name=name, **kwargs)
        self.name = name


class AIMessage(BaseMessage):
    type: str = "ai"
    tool_calls: list = Field(default_factory=list)
    response_metadata: dict = Field(default_factory=dict)

    def __init__(self, content: Any, id: str = None, tool_calls: list = None, additional_kwargs: dict = None, response_metadata: dict = None, metadata: dict = None, **kwargs: Any):
        super().__init__(content, id, additional_kwargs, metadata, tool_calls=tool_calls or [], response_metadata=response_metadata or {}, **kwargs)
        self.tool_calls = tool_calls or []
        self.response_metadata = response_metadata or {}


class ToolMessage(BaseMessage):
    type: str = "tool"
    tool_call_id: str
    name: str | None = None

    def __init__(self, content: Any, tool_call_id: str, name: str = None, id: str = None, additional_kwargs: dict = None, metadata: dict = None, **kwargs: Any):
        super().__init__(content, id, additional_kwargs, metadata, tool_call_id=tool_call_id, name=name, **kwargs)
        self.tool_call_id = tool_call_id
        self.name = name


class RemoveMessage(BaseMessage):
    type: str = "remove"


class AIMessageChunk(AIMessage):
    """Chunk representing streamed AI response delta."""

    def __add__(self, other: Any) -> "AIMessageChunk":
        if not isinstance(other, AIMessageChunk):
            return self

        merged_tool_calls = []
        tc_map = {tc.get("index", 0): dict(tc) for tc in self.tool_calls}

        for otc in other.tool_calls:
            idx = otc.get("index", 0)
            if idx in tc_map:
                tc = tc_map[idx]
                if "id" in otc and otc["id"]:
                    tc["id"] = (tc.get("id") or "") + otc["id"]
                if "name" in otc and otc["name"]:
                    tc["name"] = (tc.get("name") or "") + otc["name"]
                if "args" in otc and otc["args"]:
                    tc["args"] = (tc.get("args") or "") + otc["args"]
            else:
                tc_map[idx] = dict(otc)

        merged_tool_calls = list(tc_map.values())

        return AIMessageChunk(
            content=self.content + other.content,
            id=self.id or other.id,
            tool_calls=merged_tool_calls,
            additional_kwargs={**self.additional_kwargs, **other.additional_kwargs},
            response_metadata={**self.response_metadata, **other.response_metadata},
            metadata={**self.metadata, **other.metadata}
        )
