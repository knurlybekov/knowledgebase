class ToolError(Exception):
    """Returned to the agent as a structured error payload; never leaks internals."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def payload(self) -> dict:
        return {"error": self.code, "message": self.message, "retryable": self.retryable}
