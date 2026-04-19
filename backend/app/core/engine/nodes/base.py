import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine import get_default_engine
from app.core.engine.engine import EngineResult
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate, ensure_state

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
        try:
            state = ensure_state(state)
            # Clear potential routing instructions from previous nodes to prevent accidental short-circuits
            state.next_node = None

            # [MSG-TRACE] ENTER: Log state.messages as received from LangGraph
            _msgs = state.messages or []
            logger.info(f"[MSG-TRACE][{self.node_name}] ENTER state.messages: {len(_msgs)} msgs | types={[type(m).__name__ for m in _msgs]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in _msgs]} | contents={[str(getattr(m,'content',''))[:60] for m in _msgs]}")

            # 1. State Preparation & Environment Hydration
            # Includes early-exit checks (e.g., Aggregator routing)
            state_update = await self.prepare_state(state, config)
            if state_update and state_update.next_node:
                # [MSG-TRACE] SHORT-CIRCUIT
                _out_msgs = getattr(state_update, 'messages', None) or []
                logger.info(f"[MSG-TRACE][{self.node_name}] SHORT-CIRCUIT StateUpdate.messages: {len(_out_msgs)} msgs | types={[type(m).__name__ for m in _out_msgs]}")
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

            # [MSG-TRACE] EXECUTION: Log execution_state.messages after ticket injection
            _exec_msgs = execution_state.messages or []
            logger.info(f"[MSG-TRACE][{self.node_name}] EXECUTION execution_state.messages: {len(_exec_msgs)} msgs | types={[type(m).__name__ for m in _exec_msgs]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in _exec_msgs]} | ticket_at={next((i for i,m in enumerate(_exec_msgs) if getattr(m,'name',None)=='context_ticket'),'N/A')}")

            # 3. Engine Execution
            model = config.get("configurable", {}).get("model")
            engine = get_default_engine()

            # Robust access to is_subtask for both AgentState objects and raw dicts
            is_subtask = False
            blackboard = getattr(state, "blackboard", None) or (state.get("blackboard") if isinstance(state, dict) else None)
            if blackboard:
                ticket = getattr(blackboard, "ticket", None) or (blackboard.get("ticket") if isinstance(blackboard, dict) else None)
                if ticket:
                    # ticket might be dict or ExecutionTicket
                    agent_config = getattr(ticket, "agent_config", None) or (ticket.get("agent_config") if isinstance(ticket, dict) else None)
                    if agent_config:
                        is_subtask = getattr(agent_config, "is_subtask", False) or (agent_config.get("is_subtask", False) if isinstance(agent_config, dict) else False)

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
            outcome = await self.handle_outcome(state, engine_result, config)
            # [MSG-TRACE] EXIT: Log returned StateUpdate.messages
            _out_msgs = getattr(outcome, 'messages', None) or []
            logger.info(f"[MSG-TRACE][{self.node_name}] EXIT StateUpdate.messages: {len(_out_msgs)} msgs | types={[type(m).__name__ for m in _out_msgs]} | ids={[getattr(m,'id','N/A')[:8] if getattr(m,'id',None) else 'N/A' for m in _out_msgs]} | contents={[str(getattr(m,'content',''))[:60] for m in _out_msgs]} | next_node={getattr(outcome,'next_node','N/A')}")
            return outcome

        except Exception as e:
            logger.error(f"[{self.node_name}] Execution failed: {e}")
            return await self.handle_error(state, e, config=config)

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
        _in_msgs = engine_result.messages or []
        logger.info(f"[MSG-TRACE][base] handle_outcome ENTER: engine_result.messages={len(_in_msgs)} msgs | original_state.messages={len(original_state.messages)} msgs | signal={type(signal).__name__ if signal else 'None'}")

        if signal:
            from app.core.engine.signals import SignalDispatcher
            dispatch_result = await SignalDispatcher.dispatch(original_state, signal, config)
            _out_msgs = getattr(dispatch_result, 'messages', None) or []
            logger.info(f"[MSG-TRACE][base] handle_outcome SIGNAL_PATH: return {len(_out_msgs)} msgs | next_node={getattr(dispatch_result,'next_node','N/A')}")
            return dispatch_result

        # Engine Contract: engine_result.messages contains ONLY new messages produced
        # in this ReAct loop (AIMessage + ToolMessage sequences). It does NOT contain
        # historical messages. The context_ticket we injected is also not included
        # in Engine output, but we defensively filter it just in case.
        new_messages = [
            m for m in (engine_result.messages or [])
            if getattr(m, "name", None) != "context_ticket"
        ]
        logger.info(f"[MSG-TRACE][base] handle_outcome RETURN: {len(new_messages)} msgs | types={[type(m).__name__ for m in new_messages]}")
        return StateUpdate(
            messages=new_messages,
            next_node=engine_result.routing_target or RoutingTarget.FINISH,
            blackboard=engine_result.blackboard or original_state.blackboard,
        )

    async def handle_error(self, state: AgentState, error: Exception, config: RunnableConfig = None) -> StateUpdate:
        """Handle execution bubbling errors."""
        # 1. Report error to the unified message handler if available
        if config:
            handler = config.get("configurable", {}).get("message_handler")
            if handler:
                try:
                    # Note: AgentEngine might have already reported this if it was an LLM error.
                    # MessageHandler will handle deduplication using internal cache logic if implemented.
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

        # 3. Non-terminal error: return error message for retry
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
            next_node=RoutingTarget.SUPERVISOR
        )
