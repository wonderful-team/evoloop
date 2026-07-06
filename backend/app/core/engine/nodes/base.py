import logging
from abc import ABC, abstractmethod
from typing import Any

from app.core.engine import get_default_engine
from app.core.engine.nodes.utils import resolve_is_subtask
from app.core.engine.routers import RoutingTarget
from app.core.engine.schemas import EngineResult
from app.core.engine.signals import signal_manager
from app.core.engine.state import AgentState, StateUpdate, ensure_state

logger = logging.getLogger(__name__)


class BaseNode(ABC):
    """
    Fundamental node interface for all engine execution nodes.
    """

    def __init__(self, node_name: str):
        self.node_name = node_name

    @abstractmethod
    async def __call__(self, state: AgentState, config: dict) -> StateUpdate:
        """Node entry point. Subclasses must implement."""
        pass

    async def handle_error(self, state: AgentState, error: Exception, config: dict = None) -> StateUpdate:
        """Handle execution errors."""
        if config:
            handler = config.get("configurable", {}).get("message_handler")
            if handler:
                try:
                    await handler.handle_error(error)
                except (RuntimeError, OSError, ValueError) as report_err:
                    logger.error(f"[{self.node_name}] Failed to report error via handler: {report_err}")

        logger.error(f"[{self.node_name}] 🛑 Execution failed: {error}")
        raise error


class BaseAgentNode(BaseNode, ABC):
    """
    Abstract base class for LLM-powered Agent Nodes.

    Standardizes the execution lifecycle:
    1. Pre-computation (Hydration, Parallel checks)
    2. Prompt Generation (Strict separation of Static System vs Dynamic UX)
    3. Engine Execution
    4. Outcome Handling & Signal Dispatching
    """

    def __init__(self, node_name: str, max_steps: int = 5, temperature: float = 0.7):
        super().__init__(node_name=node_name)
        self.max_steps = max_steps
        self.temperature = temperature

    async def __call__(self, state: AgentState, config: dict) -> StateUpdate:
        try:
            state = ensure_state(state)
            state.next_node = None

            # 1. State Preparation & Environment Hydration
            state_update = await self.prepare_state(state, config)
            if state_update and state_update.next_node:
                return state_update

            # 2. Build Prompts
            static_system_prompt, dynamic_ticket_text = await self.build_prompt_pair(state, config)
            logger.debug(
                "[%s] STATIC SYSTEM PROMPT (%d chars):\n%s",
                self.node_name.upper(),
                len(static_system_prompt),
                static_system_prompt,
            )
            logger.debug(
                "[%s] DYNAMIC TICKET TEXT (%d chars):\n%s",
                self.node_name.upper(),
                len(dynamic_ticket_text),
                dynamic_ticket_text,
            )
            if dynamic_ticket_text:
                logger.info(
                    f"[{self.node_name}] Dynamic ticket injected ({len(dynamic_ticket_text)} chars) | "
                    f"preview: {dynamic_ticket_text[:200].replace(chr(10), ' ')}..."
                )
            tools = await self.get_tools(state)

            # Insert Context Ticket just before the LAST human message (role="user")
            if dynamic_ticket_text:
                ticket_msg = {"role": "user", "content": dynamic_ticket_text, "name": "context_ticket"}
                last_human_idx = -1
                for idx in range(len(state.messages) - 1, -1, -1):
                    if state.messages[idx].get("role") == "user":
                        last_human_idx = idx
                        break
                if last_human_idx >= 0:
                    state.messages.insert(last_human_idx, ticket_msg)
                else:
                    state.messages.append(ticket_msg)

            # 3. Engine Execution
            engine = get_default_engine()
            is_subtask = resolve_is_subtask(state)
            model = config.get("configurable", {}).get("model")

            logger.info(
                f"[{self.node_name}] 🚀 Engine.run_node | model={model} | is_subtask={is_subtask} | "
                f"max_steps={1 if is_subtask else self.max_steps}"
            )

            engine_result = await engine.run_node(
                state=state,
                config=config,
                system_prompt=static_system_prompt,
                tools=tools,
                max_steps=1 if is_subtask else self.max_steps,
                name=self.node_name,
                temperature=self.temperature,
                node_source=self.node_name.lower(),
                is_subtask=is_subtask,
                model=model,
            )

            logger.info(
                f"[{self.node_name}] 📥 EngineResult received | messages={len(engine_result.messages or [])} | "
                f"signal={type(engine_result.signal).__name__ if engine_result.signal else 'None'}"
            )

            # 4. Handle Outcome & Signal Dispatching
            outcome = await self.handle_outcome(state, engine_result, config)
            logger.info(
                f"[{self.node_name}] 📤 Outcome RETURN | messages={len(outcome.messages or [])} | "
                f"next_node={outcome.next_node}"
            )
            return outcome

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[{self.node_name}] Execution failed: {e}")
            return await self.handle_error(state, e, config=config)

    async def prepare_state(self, state: AgentState, config: dict) -> StateUpdate | None:
        return None

    async def build_prompt_pair(self, state: AgentState, config: dict) -> tuple[str, str]:
        return "", ""

    async def get_tools(self, state: AgentState) -> list[Any]:
        return []

    async def handle_outcome(self, original_state: AgentState, engine_result: EngineResult, config: dict) -> StateUpdate:
        if engine_result.signal:
            dispatch_result = await signal_manager.dispatch(original_state, engine_result.signal, config)
            if dispatch_result is not None:
                if engine_result.queued_signals:
                    def _serialize_signal(s):
                        if hasattr(s, "model_dump"):
                            d = s.model_dump()
                            d["_type"] = type(s).__name__
                            return d
                        return s

                    serialized_signals = [
                        _serialize_signal(s)
                        for s in engine_result.queued_signals
                    ]
                    dispatch_result.pending_signals = serialized_signals
                    dispatch_result.signal_queue_total = len(serialized_signals)

                customized = await self._customize_dispatch_result(dispatch_result, original_state, engine_result, config)
                return customized

        fallback = await self._build_fallback_outcome(original_state, engine_result, config)
        return fallback

    async def _customize_dispatch_result(
        self,
        dispatch_result: StateUpdate,
        original_state: AgentState,
        engine_result: EngineResult,
        config: dict,
    ) -> StateUpdate:
        return dispatch_result

    async def _build_fallback_outcome(
        self,
        original_state: AgentState,
        engine_result: EngineResult,
        config: dict,
    ) -> StateUpdate:
        new_messages = [
            m for m in (engine_result.messages or [])
            if m.get("name") != "context_ticket"
        ]
        return StateUpdate(
            messages=new_messages,
            next_node=RoutingTarget.FINISH,
        )
