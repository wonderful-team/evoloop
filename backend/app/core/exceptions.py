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
    """

    def __init__(self, message: str = "This operation requires a specific project and is not available in global mode"):
        super().__init__(message)


class AgentTerminalException(Exception):
    """
    Raised when a terminal error (like quota exhausted) is detected.
    Used to trigger circuit breaking and stop all node execution permanently for the current run.
    """

    def __init__(self, message: str, error_type: str = "terminal_error"):
        self.error_type = error_type
        super().__init__(message)
