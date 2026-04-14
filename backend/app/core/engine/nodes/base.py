import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine import get_default_engine
from app.core.engine.engine import EngineResult
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate

logger = logging.getLogger(__name__)


class BaseAgentNode(ABC):
    """
    Abstract base class for EvoLoop Agent Nodes.
    
    Standardizes the execution lifecycle:
    1. Pre-computation (Hydration, Parallel checks)
    2. Prompt Generation (Strict separation of Static System vs Dynamic UX)
    3. Engine Execution
    4. Outcome Handling & Signal Dispatching
    
    This architecture enforces Prompt Caching by ensuring the System Prompt 
    remains completely static across multiple dialog turns.
    """

    def __init__(self, node_name: str, max_steps: int = 5, temperature: float = 0.7):
        self.node_name = node_name
        self.max_steps = max_steps
        self.temperature = temperature

    async def __call__(self, state: AgentState, config: RunnableConfig) -> StateUpdate:
        """The standard LangGraph node entry point."""
        # LangGraph may pass a raw dict (e.g. from checkpoint resume or interrupt).
        # Normalize at the framework boundary so downstream code never sees a dict.
        if not isinstance(state, AgentState):
            state = AgentState.model_validate(state)

        # 1. State Preparation & Environment Hydration
        # Includes early-exit checks (e.g., Aggregator routing)
        state_update = await self.prepare_state(state, config)
        if state_update and state_update.next_node:
            return state_update

        # 2. Build Prompts (Enforcing Static/Dynamic Split)
        # static_prompt: Huge instructions + tools -> goes to generic SystemMessage
        # dynamic_ticket: Small turn-based telemetry -> prepended as HumanMessage
        static_system_prompt, dynamic_ticket_text = await self.build_prompt_pair(state, config)
        tools = await self.get_tools(state)

        # Prepend Context Ticket if provided
        messages = list(list(state.messages))
        if dynamic_ticket_text:
            ticket_msg = HumanMessage(content=dynamic_ticket_text, name="context_ticket")
            messages = [ticket_msg] + messages

        execution_state = state.model_copy(update={"messages": messages})

        # 3. Engine Execution
        model = config.get("configurable", {}).get("model")
        engine = get_default_engine()

        try:
            is_subtask = state.blackboard.ticket.agent_config.is_subtask if state.blackboard and state.blackboard.ticket and state.blackboard.ticket.agent_config else False
            engine_result = await engine.run_node(
                state=execution_state,
                config=config,
                system_prompt=static_system_prompt,
                tools=tools,
                model=model,
                max_steps=1 if is_subtask else self.max_steps,
                name=self.node_name,
                temperature=self.temperature,
                node_source=self.node_name.lower(),
                is_subtask=is_subtask,
            )

            # 4. Handle Outcome & Signal Dispatching
            return await self.handle_outcome(state, engine_result, config)

        except Exception as e:
            logger.error(f"[{self.node_name}] Execution failed: {e}")
            return await self.handle_error(state, e)

    @abstractmethod
    async def prepare_state(self, state: AgentState, config: RunnableConfig) -> StateUpdate | None:
        """
        Hook for pre-computation. 
        Return a dict with "next_node" to short-circuit, or a dict to update the state.
        By default, EvoContextMiddleware hydration should happen here.
        """
        pass

    @abstractmethod
    async def build_prompt_pair(self, state: AgentState, config: RunnableConfig) -> tuple[str, str]:
        """
        Return (static_system_prompt, dynamic_context_ticket).
        - static_system_prompt: Must be cacheable (no changing tokens during a session).
        - dynamic_context_ticket: Changing state (telemetry, iteration counts) as string or empty.
        """
        pass

    @abstractmethod
    async def get_tools(self, state: AgentState) -> list[Any]:
        """Return the list of LangChain tools available to this node."""
        pass

    async def handle_outcome(self, original_state: AgentState, engine_result: EngineResult, config: RunnableConfig) -> StateUpdate:
        """
        Standard outcome handler. Processes SignalDispatching.
        Subclasses should typically call `super().handle_outcome(...)` first.
        """
        signal = engine_result.signal
        if signal:
            from app.core.engine.dispatcher import SignalDispatcher
            dispatch_result = await SignalDispatcher.dispatch(original_state, signal, config)
            return dispatch_result

        # Provide a default fallback if the subclass doesn't implement advanced handling
        return StateUpdate(
            messages=engine_result.messages or [],
            next_node=engine_result.routing_target or RoutingTarget.FINISH,
            blackboard=engine_result.blackboard or original_state.blackboard,
        )

    async def handle_error(self, state: AgentState, error: Exception) -> StateUpdate:
        """Handle execution bubbling errors."""
        from langchain_core.messages import AIMessage
        error_msg = AIMessage(
            content=f"Node '{self.node_name}' failed: {error}",
            metadata={"is_error": True, "error_type": "node_execution"}
        )
        return StateUpdate(
            messages=[error_msg],
            next_node=RoutingTarget.SUPERVISOR
        )
