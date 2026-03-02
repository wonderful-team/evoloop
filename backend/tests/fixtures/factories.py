"""
Test Data Factories

Factories for creating test data objects with sensible defaults.
Uses factory pattern for flexible object creation.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage


class EvoContextFactory:
    """Factory for creating EvoContext instances."""

    @staticmethod
    def create(
        request_id: str = "test-request-001",
        user_id: Optional[str] = "test-user-001",
        project_id: Optional[int] = 1,
        thread_id: Optional[str] = "test-thread-001",
        working_directory: Optional[str] = "/tmp/test",
        language: str = "en",
        **kwargs
    ):
        from app.core.context.manager import EvoContext

        return EvoContext(
            request_id=request_id,
            user_id=user_id,
            project_id=project_id,
            thread_id=thread_id,
            working_directory=working_directory,
            language=language,
            **kwargs
        )


class AgentStateFactory:
    """Factory for creating AgentState dictionaries."""

    @staticmethod
    def create(
        messages: Optional[List[BaseMessage]] = None,
        project_id: int = 1,
        current_plan: Optional[str] = None,
        iteration_count: int = 0,
        scratchpad: Optional[Dict] = None,
        execution_ticket: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        return {
            "messages": messages or [HumanMessage(content="Test message")],
            "project_id": project_id,
            "current_plan": current_plan,
            "iteration_count": iteration_count,
            "scratchpad": scratchpad or {},
            "execution_ticket": execution_ticket,
            **kwargs
        }

    @staticmethod
    def with_human_message(content: str, **kwargs) -> Dict[str, Any]:
        """Create state with a human message."""
        return AgentStateFactory.create(
            messages=[HumanMessage(content=content)],
            **kwargs
        )

    @staticmethod
    def with_conversation(history: List[tuple], **kwargs) -> Dict[str, Any]:
        """
        Create state with conversation history.

        Args:
            history: List of (role, content) tuples
                   roles: 'human', 'ai', 'system', 'tool'
        """
        messages = []
        for role, content in history:
            if role == "human":
                messages.append(HumanMessage(content=content))
            elif role == "ai":
                messages.append(AIMessage(content=content))
            elif role == "system":
                messages.append(SystemMessage(content=content))
            elif role == "tool":
                messages.append(ToolMessage(content=content, tool_call_id="test"))

        return AgentStateFactory.create(messages=messages, **kwargs)


class ExecutionTicketFactory:
    """Factory for creating ExecutionTicket dictionaries."""

    @staticmethod
    def create(
        ticket_type: str = "test_task",
        priority: str = "normal",
        acceptance_criteria: Optional[List[str]] = None,
        focus_paths: Optional[List[str]] = None,
        topic: Optional[str] = "Test topic",
        parameters: Optional[Dict] = None,
        constraints: Optional[List[str]] = None,
        expected_outcomes: Optional[List[str]] = None,
        agent_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        return {
            "ticket_type": ticket_type,
            "priority": priority,
            "acceptance_criteria": acceptance_criteria or ["Complete successfully"],
            "focus_paths": focus_paths or [],
            "topic": topic,
            "parameters": parameters or {},
            "constraints": constraints or [],
            "expected_outcomes": expected_outcomes or ["Success"],
            "agent_config": agent_config,
        }

    @staticmethod
    def for_developer(
        focus_paths: List[str],
        acceptance_criteria: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Create ticket for developer node."""
        return ExecutionTicketFactory.create(
            ticket_type="development",
            focus_paths=focus_paths,
            acceptance_criteria=acceptance_criteria,
            **kwargs
        )

    @staticmethod
    def for_researcher(
        topic: str,
        expected_outcomes: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Create ticket for researcher node."""
        return ExecutionTicketFactory.create(
            ticket_type="research",
            topic=topic,
            expected_outcomes=expected_outcomes,
            **kwargs
        )

    @staticmethod
    def for_dynamic_specialist(
        role_name: str,
        system_instructions: str,
        tools: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Create ticket for dynamic specialist."""
        return ExecutionTicketFactory.create(
            ticket_type="dynamic_task",
            agent_config={
                "role_name": role_name,
                "system_instructions": system_instructions,
                "tools": tools,
                "model_override": None,
            },
            **kwargs
        )


class LearnedSkillFactory:
    """Factory for creating mock LearnedSkill objects."""

    @staticmethod
    def create(
        id: int = 1,
        name: str = "test_skill",
        namespace: str = "test/namespace",
        instructions: str = "Test skill instructions",
        trigger_patterns: Optional[List[str]] = None,
        confidence_threshold: float = 0.7,
        version: int = 1,
        **kwargs
    ):
        skill = MagicMock()
        skill.id = id
        skill.name = name
        skill.namespace = namespace
        skill.instructions = instructions
        skill.trigger_patterns = trigger_patterns or ["test pattern"]
        skill.confidence_threshold = confidence_threshold
        skill.version = version
        skill.created_at = datetime.now()
        skill.updated_at = datetime.now()

        for key, value in kwargs.items():
            setattr(skill, key, value)

        return skill


class MessageFactory:
    """Factory for creating LangChain messages."""

    @staticmethod
    def human(content: str, **kwargs) -> HumanMessage:
        return HumanMessage(content=content, **kwargs)

    @staticmethod
    def ai(content: str, tool_calls: Optional[List[Dict]] = None, **kwargs) -> AIMessage:
        msg = AIMessage(content=content, **kwargs)
        if tool_calls:
            msg.tool_calls = tool_calls
        return msg

    @staticmethod
    def system(content: str, **kwargs) -> SystemMessage:
        return SystemMessage(content=content, **kwargs)

    @staticmethod
    def tool(content: str, tool_call_id: str = "test", **kwargs) -> ToolMessage:
        return ToolMessage(content=content, tool_call_id=tool_call_id, **kwargs)

    @staticmethod
    def conversation(*turns: str) -> List[BaseMessage]:
        """
        Create alternating human/AI conversation.

        Args:
            turns: Alternating human and AI messages
        """
        messages = []
        for i, content in enumerate(turns):
            if i % 2 == 0:
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        return messages


class ProjectFactory:
    """Factory for creating test project data."""

    @staticmethod
    def create(
        id: int = 1,
        name: str = "Test Project",
        path: str = "/tmp/test_project",
        description: str = "A test project",
        **kwargs
    ):
        return {
            "id": id,
            "name": name,
            "path": path,
            "description": description,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            **kwargs
        }


class EventFactory:
    """Factory for creating test events."""

    @staticmethod
    def create(
        event_type: str = "test.event",
        source: str = "test",
        data: Optional[Dict] = None,
        **kwargs
    ):
        from app.core.events.base import BaseEvent

        return BaseEvent(
            event_type=event_type,
            source=source,
            data=data or {},
            **kwargs
        )


class ToolCallFactory:
    """Factory for creating tool call objects."""

    @staticmethod
    def create(
        name: str = "test_tool",
        args: Optional[Dict] = None,
        tool_call_id: str = "call_test_001",
    ) -> Dict[str, Any]:
        return {
            "name": name,
            "args": args or {},
            "id": tool_call_id,
        }

    @staticmethod
    def route_to(target: str, reason: str = "", context: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a route_to tool call."""
        return ToolCallFactory.create(
            name="route_to",
            args={
                "target": target,
                "reason": reason,
                "context": context or {},
            }
        )
