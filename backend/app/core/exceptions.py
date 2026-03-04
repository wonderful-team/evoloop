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


class GlobalModeError(Exception):
    """
    Raised when a tool/operation requires a specific project but the current
    context is in global mode (project_id=0 or None).

    This is a normal Exception (not BaseException) as it's expected to be
    caught by tools and converted to a user-friendly message.
    """

    def __init__(self, message: str = "This operation requires a specific project and is not available in global mode"):
        super().__init__(message)
