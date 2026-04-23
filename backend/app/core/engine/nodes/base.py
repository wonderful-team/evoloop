import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine import get_default_engine
from app.core.engine.engine import EngineResult
from app.core.engine.nodes.utils import log_msg_trace, resolve_is_subtask, dispatch_signal_if_present
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate, ensure_state

logger = logging.getLogger(__name__)


class BaseNode(ABC):
    """
    Fundamental node interface for all LangGraph nodes.

    Every node in the graph must inherit from BaseNode and implement
    ``__call__(state, config) -> StateUpdate``.

    This is the minimal contract. Nodes that do NOT require LLM execution
    (e.g. AggregatorNode, FinishNode) should inherit directly from BaseNode.
    Nodes that DO require LLM execution should inherit from BaseAgentNode.
    """

    def __init__(self, node_name: str):
        self.node_name = node_name

    @abstractmethod
    async def __call__(self, state: AgentState, config: RunnableConfig) -> StateUpdate:
        """Node entry point. Subclasses must implement."""
        pass

    async def handle_error(self, state: AgentState, error: Exception, config: RunnableConfig = None) -> StateUpdate:
        """Handle execution errors. Shared by all node types."""
        # 1. Report error to the unified message handler if available
        if config:
            handler = config.get("configurable", {}).get("message_handler")
            if handler:
                try:
                    await handler.handle_error(error)
                except Exception as report_err:
                    logger.error(f"[{self.node_name}] Failed to report error via handler: {report_err}")

        # 2. Determine if this is a terminal error that should trigger circuit breakers
        from app.core.engine.error_handler import LLMErrorHandler
        classification = LLMErrorHandler.classify_exception(error)

        # Terminal errors must propagate to trigger proper end_run handling in background_agent.py
        if classification.is_terminal:
            logger.warning(f"[{self.node_name}] 🛑 Terminal error detected. Propagating to outer handler.")
            raise error

        # 3. Non-terminal error: return error message and route to FINISH
        #    (routing back to SUPERVISOR causes infinite retry loops)
        error_msg = AIMessage(
            content=f"Node '{self.node_name}' failed: {error}",
            metadata={
                "is_error": True,
                "error_type": classification.error_type or "node_execution",
                "is_terminal": False
            }
        )
        return StateUpdate(
            messages=[error_msg],
            next_node=RoutingTarget.FINISH
        )


class BaseAgentNode(BaseNode, ABC):
    """
    Abstract base class for LLM-powered Agent Nodes.

    Standardizes the execution lifecycle:
    1. Pre-computation (Hydration, Parallel checks)
    2. Prompt Generation (Strict separation of Static System vs Dynamic UX)
    3. Engine Execution
    4. Outcome Handling & Signal Dispatching

    This architecture enforces Prompt Caching by ensuring the System Prompt
    remains completely static across multiple dialog turns.
    """

    def __init__(self, node_name: str, max_steps: int = 5, temperature: float = 0.7):
        super().__init__(node_name=node_name)
        self.max_steps = max_steps
        self.temperature = temperature

    async def __call__(self, state: AgentState, config: RunnableConfig) -> StateUpdate:
        """The standard LangGraph node entry point."""
        try:
            state = ensure_state(state)
            # Clear potential routing instructions from previous nodes to prevent accidental short-circuits
            state.next_node = None

            # Centralized hydration: all nodes receive context via middleware
            from app.core.engine.context_hydrator import EvoContextMiddleware
            state = await EvoContextMiddleware.hydrate(state, config)
            logger.info(f"[{self.node_name}] Context Hydrated via Middleware")

            # [MSG-TRACE] ENTER
            log_msg_trace(self.node_name, "ENTER", state.messages)

            # 1. State Preparation & Environment Hydration
            # Includes early-exit checks (e.g., Aggregator routing)
            state_update = await self.prepare_state(state, config)
            if state_update and state_update.next_node:
                log_msg_trace(self.node_name, "SHORT-CIRCUIT", getattr(state_update, 'messages', None))
                return state_update

            # 2. Build Prompts (Enforcing Static/Dynamic Split)
            # static_prompt: Huge instructions + tools -> goes to generic SystemMessage
            # dynamic_ticket: Small turn-based telemetry -> injected as HumanMessage
            static_system_prompt, dynamic_ticket_text = await self.build_prompt_pair(state, config)
            tools = await self.get_tools(state)

            # Insert Context Ticket just before the LAST HumanMessage so that
            # the historical message prefix remains stable for Prompt Cache.
            # Previous behaviour (prepend to index 0) caused cache miss every turn.
            messages = list(state.messages)
            if dynamic_ticket_text:
                ticket_msg = HumanMessage(content=dynamic_ticket_text, name="context_ticket")
                last_human_idx = -1
                for idx in range(len(messages) - 1, -1, -1):
                    if isinstance(messages[idx], HumanMessage):
                        last_human_idx = idx
                        break
                if last_human_idx >= 0:
                    messages.insert(last_human_idx, ticket_msg)
                else:
                    # No human message found – append ticket at the end
                    messages.append(ticket_msg)

            execution_state = state.model_copy(update={"messages": messages})

            # [MSG-TRACE] EXECUTION
            ticket_at = next((i for i, m in enumerate(execution_state.messages) if getattr(m, "name", None) == "context_ticket"), "N/A")
            log_msg_trace(self.node_name, "EXECUTION", execution_state.messages, ticket_at=ticket_at)

            # 3. Engine Execution
            engine = get_default_engine()

            is_subtask = resolve_is_subtask(state)
            model = config.get("configurable", {}).get("model")
            if not model:
                from app.core.context.manager import ContextManager
                ctx = ContextManager.current()
                model = getattr(ctx, "active_model", None)
            if not model:
                from app.infrastructure.config.service import SystemConfigService
                model = SystemConfigService.get_value("LLM_MODEL")

            logger.info(
                f"[{self.node_name}] 🚀 Engine.run_node | model={model} | is_subtask={is_subtask} | "
                f"max_steps={1 if is_subtask else self.max_steps}"
            )

            engine_result = await engine.run_node(
                state=execution_state,
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
                f"types={[type(m).__name__ for m in (engine_result.messages or [])]} | "
                f"signal={type(engine_result.signal).__name__ if engine_result.signal else 'None'}"
            )

            # 4. Handle Outcome & Signal Dispatching
            outcome = await self.handle_outcome(state, engine_result, config)
            # [MSG-TRACE] EXIT
            log_msg_trace(self.node_name, "EXIT", getattr(outcome, 'messages', None), next_node=getattr(outcome, 'next_node', 'N/A'))
            logger.info(
                f"[{self.node_name}] 📤 Outcome RETURN | messages={len(getattr(outcome, 'messages', []) or [])} | "
                f"types={[type(m).__name__ for m in (getattr(outcome, 'messages', []) or [])]} | "
                f"next_node={getattr(outcome, 'next_node', 'N/A')}"
            )
            return outcome

        except Exception as e:
            logger.error(f"[{self.node_name}] Execution failed: {e}")
            return await self.handle_error(state, e, config=config)

    # ------------------------------------------------------------------
    # Lifecycle hooks — subclasses MAY override; default no-ops provided
    # so that non-LLM nodes (Finish, Aggregator) can inherit cleanly.
    # ------------------------------------------------------------------

    async def prepare_state(self, state: AgentState, config: RunnableConfig) -> StateUpdate | None:
        """
        Hook for pre-computation.
        Return a StateUpdate with "next_node" set to short-circuit, or None to continue.
        """
        return None

    async def build_prompt_pair(self, state: AgentState, config: RunnableConfig) -> tuple[str, str]:
        """
        Return (static_system_prompt, dynamic_context_ticket).
        - static_system_prompt: Must be cacheable (no changing tokens during a session).
        - dynamic_context_ticket: Changing state (telemetry, iteration counts) as string or empty.
        """
        return "", ""

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Return the list of LangChain tools available to this node."""
        return []

    # ------------------------------------------------------------------
    # Outcome handling — unified signal dispatch + customizable hooks
    # ------------------------------------------------------------------

    async def handle_outcome(self, original_state: AgentState, engine_result: EngineResult, config: RunnableConfig) -> StateUpdate:
        """
        Standard outcome handler. Processes SignalDispatching.
        Subclasses should typically NOT override this; instead customize
        `_customize_dispatch_result` or `_build_fallback_outcome`.
        """
        signal = engine_result.signal
        log_msg_trace(
            self.node_name, "handle_outcome ENTER",
            engine_result.messages,
            signal=type(signal).__name__ if signal else "None",
        )

        # 1. Signal dispatch path
        dispatch_result = await dispatch_signal_if_present(original_state, signal, config, self.node_name)
        if dispatch_result is not None:
            customized = await self._customize_dispatch_result(dispatch_result, original_state, engine_result, config)
            log_msg_trace(
                self.node_name, "handle_outcome SIGNAL_PATH",
                getattr(customized, 'messages', None),
                next_node=getattr(customized, 'next_node', 'N/A'),
            )
            return customized

        # 2. Non-signal fallback path
        fallback = await self._build_fallback_outcome(original_state, engine_result, config)
        log_msg_trace(
            self.node_name, "handle_outcome RETURN",
            getattr(fallback, 'messages', None),
            next_node=getattr(fallback, 'next_node', 'N/A'),
        )
        return fallback

    async def _customize_dispatch_result(
        self,
        dispatch_result: StateUpdate,
        original_state: AgentState,
        engine_result: EngineResult,
        config: RunnableConfig,
    ) -> StateUpdate:
        """
        Hook called after a signal is successfully dispatched.
        Subclasses may mutate dispatch_result (e.g. inject iteration_count).
        """
        return dispatch_result

    async def _build_fallback_outcome(
        self,
        original_state: AgentState,
        engine_result: EngineResult,
        config: RunnableConfig,
    ) -> StateUpdate:
        """
        Hook called when NO signal was present.
        Default: return messages + routing target.
        """
        new_messages = [
            m for m in (engine_result.messages or [])
            if getattr(m, "name", None) != "context_ticket"
        ]
        logger.info(
            f"[{self.node_name}] _build_fallback_outcome | "
            f"engine_result.messages={len(engine_result.messages or [])} | "
            f"after_filter={len(new_messages)} | "
            f"types={[type(m).__name__ for m in new_messages]}"
        )
        return StateUpdate(
            messages=new_messages,
            next_node=engine_result.routing_target or RoutingTarget.FINISH,
            blackboard=engine_result.blackboard or original_state.blackboard,
        )


