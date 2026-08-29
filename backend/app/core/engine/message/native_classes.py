"""
Native, SDK-free message class definitions providing native message classes.
"""

from typing import Any

from pydantic import BaseModel, Field


class RunnableConfig(dict):
    """Mock RunnableConfig class providing a native RunnableConfig."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema

        return core_schema.dict_schema()


class BaseMessage(BaseModel):
    """Base class for native messages."""

    content: str | list[Any]
    id: str | None = None
    additional_kwargs: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    name: str | None = None
    tool_calls: list = Field(default_factory=list)
    tool_call_id: str | None = None
    type: str = ""

    model_config = {
        "arbitrary_types_allowed": True,
        "extra": "allow"
    }

    _TYPE_TO_ROLE = {
        "human": "user",
        "ai": "assistant",
        "system": "system",
        "tool": "tool",
        "remove": "remove",
    }

    def __init__(
        self,
        content: Any,
        id: str = None,
        additional_kwargs: dict = None,
        metadata: dict = None,
        **kwargs: Any,
    ):
        super().__init__(
            content=content,
            id=id,
            additional_kwargs=additional_kwargs or {},
            metadata=metadata or {},
            **kwargs,
        )
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def role(self) -> str:
        return self._TYPE_TO_ROLE.get(self.type, "user")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(content={self.content!r}, id={self.id!r})"


class SystemMessage(BaseMessage):
    type: str = "system"


class HumanMessage(BaseMessage):
    type: str = "human"

    def __init__(
        self,
        content: Any,
        name: str = None,
        id: str = None,
        additional_kwargs: dict = None,
        metadata: dict = None,
        **kwargs: Any,
    ):
        super().__init__(content, id, additional_kwargs, metadata, name=name, **kwargs)


class AIMessage(BaseMessage):
    type: str = "ai"
    response_metadata: dict = Field(default_factory=dict)

    def __init__(
        self,
        content: Any,
        id: str = None,
        tool_calls: list = None,
        additional_kwargs: dict = None,
        response_metadata: dict = None,
        metadata: dict = None,
        **kwargs: Any,
    ):
        super().__init__(
            content,
            id,
            additional_kwargs,
            metadata,
            tool_calls=tool_calls or [],
            response_metadata=response_metadata or {},
            **kwargs,
        )
        self.response_metadata = response_metadata or {}


class ToolMessage(BaseMessage):
    type: str = "tool"

    def __init__(
        self,
        content: Any,
        tool_call_id: str,
        name: str = None,
        id: str = None,
        additional_kwargs: dict = None,
        metadata: dict = None,
        **kwargs: Any,
    ):
        super().__init__(
            content,
            id,
            additional_kwargs,
            metadata,
            tool_call_id=tool_call_id,
            name=name,
            **kwargs,
        )


class AIMessageChunk(AIMessage):
    """Chunk representing streamed AI response delta."""

    def __add__(self, other: Any) -> "AIMessageChunk":
        if not isinstance(other, AIMessageChunk):
            return self

        def _g(tc, key, default=0):
            return tc.get(key, default)

        def _d(tc: dict) -> dict:
            return dict(tc)

        merged_tool_calls = []
        tc_map = {_g(tc, "index", 0): _d(tc) for tc in self.tool_calls}

        for otc in other.tool_calls:
            idx = _g(otc, "index", 0)
            if idx in tc_map:
                tc = tc_map[idx]
                otc_id = _g(otc, "id", "")
                if otc_id:
                    tc["id"] = (tc.get("id") or "") + otc_id
                otc_name = _g(otc, "name", "")
                if otc_name:
                    tc["name"] = (tc.get("name") or "") + otc_name
                otc_args = _g(otc, "args", "")
                if otc_args:
                    tc["args"] = (tc.get("args") or "") + otc_args
            else:
                tc_map[idx] = _d(otc)

        merged_tool_calls = list(tc_map.values())

        return AIMessageChunk(
            content=self.content + other.content,
            id=self.id or other.id,
            tool_calls=merged_tool_calls,
            additional_kwargs={**self.additional_kwargs, **other.additional_kwargs},
            response_metadata={**self.response_metadata, **other.response_metadata},
            metadata={**self.metadata, **other.metadata},
        )
