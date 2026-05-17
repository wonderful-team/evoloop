"""
EvoLoop Message Converter Utility
=================================

Provides centralized logic for converting messages between different formats:
- Raw API Dicts (Pydantic models)
- LangChain BaseMessage objects
- Database SQLModels

Also owns the authoritative ``repair()`` implementation for structurally
correcting LangChain message histories before sending them to strict LLM APIs
(Anthropic, GLM, etc.).  ``ContextTrimmer`` delegates its repair stage to this
method rather than maintaining a private copy.
"""

import logging
from typing import Any, List, Union

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
    ChatMessage,
)

logger = logging.getLogger(__name__)


class EvoMessageConverter:
    """
    Unified converter for system-wide message normalization.
    """

    @staticmethod
    def to_langchain(messages: list[Any]) -> List[BaseMessage]:
        """
        Convert raw dictionaries or existing message objects to LangChain BaseMessage.
        
        Args:
            messages: List of message objects (dicts or objects with role/content)
            
        Returns:
            List of LangChain BaseMessage instances
        """
        deserialized = []
        for m in messages:
            if isinstance(m, BaseMessage):
                deserialized.append(m)
                continue
                
            if not isinstance(m, dict):
                # Try to access attributes if it's an object (e.g. SQLModel)
                try:
                    role = getattr(m, "role", "human")
                    content = getattr(m, "content", "")
                    additional_kwargs = getattr(m, "additional_kwargs", {}) or {}
                except AttributeError:
                    logger.warning(f"[Converter] Skipping non-dict/non-object message: {type(m)}")
                    continue
            else:
                # Handle dictionary input
                role = m.get("role") or m.get("type", "human")
                content = m.get("content", "")
                additional_kwargs = m.get("additional_kwargs", {}) or {}

            # Preserve references in additional_kwargs for LangChain
            references = m.get("references") if isinstance(m, dict) else getattr(m, "references", None)
            if references:
                additional_kwargs = additional_kwargs.copy()
                additional_kwargs["references"] = [
                    ref.model_dump() if hasattr(ref, "model_dump") else ref 
                    for ref in references
                ]

            # Mapping roles
            if role in ["human", "user"]:
                deserialized.append(HumanMessage(content=content, additional_kwargs=additional_kwargs))
            elif role in ["ai", "assistant"]:
                deserialized.append(AIMessage(content=content, additional_kwargs=additional_kwargs))
            elif role == "system":
                deserialized.append(SystemMessage(content=content, additional_kwargs=additional_kwargs))
            elif role == "tool":
                tool_call_id = m.get("tool_call_id") if isinstance(m, dict) else getattr(m, "tool_call_id", None)
                deserialized.append(ToolMessage(content=content, tool_call_id=tool_call_id or "unknown"))
            else:
                deserialized.append(ChatMessage(role=role, content=content))
                
        return deserialized

    @staticmethod
    def from_langchain(messages: List[BaseMessage]) -> List[dict]:
        """Convert LangChain messages to standard EvoLoop serializable dicts."""
        serialized = []
        for m in messages:
            msg_dict = {
                "role": m.type,
                "content": m.content,
                "additional_kwargs": m.additional_kwargs,
            }
            if isinstance(m, ToolMessage):
                msg_dict["tool_call_id"] = m.tool_call_id
            serialized.append(msg_dict)
        return serialized

    @staticmethod
    def repair(messages: List[BaseMessage]) -> List[BaseMessage]:
        """
        Ensure the message history is structurally valid for strict LLM APIs
        (Anthropic, GLM, etc.).

        Rules enforced:
        1. No orphaned ToolMessages — must have a preceding AIMessage with tool_calls.
        2. No dangling ToolCalls — AIMessage.tool_calls must be followed by ToolMessages.
        3. No consecutive same-role messages (Human→Human, AI→AI) — merged instead.
        4. No empty-content messages (excluding ToolMessage / AIMessage with tool_calls).
        5. History must not start with an AIMessage after any SystemMessages.

        This is the **single authoritative** repair implementation for the entire system.
        ``ContextTrimmer`` delegates to this method for its "repair" stage.
        """
        from app.i18n.service import i18n

        _DEFAULTS = {
            "orphaned_tool": "[Tool execution context missing]",
            "interrupted_tool_response": "[Tool execution was interrupted]",
            "conversation_continuation": "[Conversation continues]",
        }

        def _t(key: str) -> str:
            try:
                result = i18n.get(f"core_utils.{key}", default=_DEFAULTS[key])
                return result if isinstance(result, str) else _DEFAULTS[key]
            except Exception:
                return _DEFAULTS[key]

        # ------------------------------------------------------------------
        # Phase 1: Basic cleanup & orphaned ToolMessage repair
        # ------------------------------------------------------------------
        stage1: List[BaseMessage] = []
        for msg in messages:
            # Drop contentless messages (AI/Tool may legitimately have no text content)
            if not msg.content and not isinstance(msg, (ToolMessage, AIMessage)):
                continue
            if isinstance(msg, AIMessage) and not msg.content and not msg.tool_calls:
                continue

            if isinstance(msg, ToolMessage):
                is_orphaned = True
                if stage1:
                    last = stage1[-1]
                    if isinstance(last, AIMessage) and last.tool_calls:
                        ids = [
                            tc["id"] if isinstance(tc, dict) else tc.id
                            for tc in last.tool_calls
                        ]
                        if msg.tool_call_id in ids:
                            is_orphaned = False
                if is_orphaned:
                    stage1.append(AIMessage(
                        content=_t("orphaned_tool"),
                        tool_calls=[{
                            "id": str(msg.tool_call_id),
                            "name": str(msg.name) if msg.name else "unknown_tool",
                            "args": {},
                        }],
                    ))
                stage1.append(msg)
                continue

            # Merge consecutive same-role messages
            if stage1:
                last = stage1[-1]
                if isinstance(last, type(msg)) and isinstance(msg, (HumanMessage, AIMessage)):
                    if isinstance(last, AIMessage) and last.tool_calls:
                        stage1.append(msg)
                        continue
                    if last.name == "context_ticket" or msg.name == "context_ticket":
                        stage1.append(msg)
                        continue
                    # Model-copy to avoid mutating shared LangGraph state refs
                    stage1[-1] = last.model_copy(
                        update={"content": f"{last.content}\n\n{msg.content}"}
                    )
                    continue

            stage1.append(msg)

        # ------------------------------------------------------------------
        # Phase 2: Dangling ToolCall repair
        # ------------------------------------------------------------------
        final_repaired: List[BaseMessage] = []
        open_tool_calls: dict[str, str] = {}  # id -> name

        for msg in stage1:
            if isinstance(msg, (HumanMessage, AIMessage)) and open_tool_calls:
                for tcid, tname in list(open_tool_calls.items()):
                    final_repaired.append(ToolMessage(
                        content=_t("interrupted_tool_response"),
                        tool_call_id=tcid,
                        name=tname,
                    ))
                open_tool_calls = {}

            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    tcid = tc["id"] if isinstance(tc, dict) else tc.id
                    tname = tc["name"] if isinstance(tc, dict) else tc.name
                    open_tool_calls[tcid] = tname

            if isinstance(msg, ToolMessage) and msg.tool_call_id in open_tool_calls:
                del open_tool_calls[msg.tool_call_id]

            final_repaired.append(msg)

        # Close trailing dangling tool calls
        if open_tool_calls and final_repaired:
            logger.warning("🔧 [Repair] History ends with dangling tool calls. Injecting dummy responses.")
            for tcid, tname in list(open_tool_calls.items()):
                final_repaired.append(ToolMessage(
                    content=_t("interrupted_tool_response"),
                    tool_call_id=tcid,
                    name=tname,
                ))

        # ------------------------------------------------------------------
        # Phase 3: Ensure history starts with HumanMessage (after SystemMessages)
        # ------------------------------------------------------------------
        non_system = [i for i, m in enumerate(final_repaired) if not isinstance(m, SystemMessage)]
        if non_system:
            first = non_system[0]
            if isinstance(final_repaired[first], AIMessage):
                final_repaired.insert(first, HumanMessage(content=_t("conversation_continuation")))
        elif not final_repaired:
            final_repaired.append(HumanMessage(content=_t("conversation_continuation")))

        return final_repaired
