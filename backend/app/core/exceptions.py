"""
Custom Exceptions for Agent Execution Control.
These exceptions inherit from BaseException to bypass standard error handling.
"""


class AgentCancelledException(BaseException):
    """
    Raised when the agent execution is cancelled by user.
    Inherits from BaseException (not Exception) to ensure it is NOT caught
    by generic `except Exception` handlers in LangChain/LangGraph.
    """
    pass


class AgentHumanInterruptException(BaseException):
    """
    Raised when the agent needs to pause for human input.
    Inherits from BaseException to ensure proper graph interruption.
    """
    def __init__(self, request_id: str, message: str = "Human input required"):
        self.request_id = request_id
        super().__init__(message)
