from abc import ABC, abstractmethod
from typing import TypeVar, Generic

from langchain_core.runnables import RunnableConfig

from app.core.engine.signals.schema import AgentSignal
from app.core.engine.state import AgentState, StateUpdate

S = TypeVar("S", bound=AgentSignal)


class SignalHandler(ABC, Generic[S]):
    """Protocol for handling a specific type of AgentSignal."""

    @abstractmethod
    async def handle(
        self, state: AgentState, signal: S, config: RunnableConfig
    ) -> StateUpdate:
        """
        Process the signal and return a StateUpdate.
        """
        pass
