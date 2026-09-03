class ServiceError(Exception):
    """Domain failure shared by the AI pipeline and web/storage adapters."""

    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable
