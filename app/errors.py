"""Errors that map cleanly onto HTTP responses."""


class ApiError(Exception):
    status = 400

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status


class NotFound(ApiError):
    status = 404


class Conflict(ApiError):
    status = 409


class LLMError(ApiError):
    """The language model could not produce a usable answer."""
    status = 502


class LLMRateLimitError(LLMError):
    status = 429


class LLMAuthError(LLMError):
    """The server's API key is missing or rejected (a configuration problem, not the user's)."""
    status = 503