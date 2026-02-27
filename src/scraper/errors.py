"""Error hierarchy for scraping retry classification.

This hierarchy enables tenacity retry decorators to automatically classify
transient failures (should retry) vs permanent failures (should not retry).

Example usage with tenacity:
    @retry(retry=retry_if_exception_type(TransientError), stop=stop_after_attempt(3))
    async def scrape_student(student_id: str):
        ...
"""


class ScrapingError(Exception):
    """Base exception for all scraping errors."""

    pass


class TransientError(ScrapingError):
    """Temporary failure that may succeed on retry.

    Examples: network timeouts, 503 Service Unavailable, temporary DOM loading issues.
    """

    pass


class RateLimitError(TransientError):
    """Rate limit exceeded - needs longer backoff.

    Inherits from TransientError so tenacity will retry it, but allows
    custom backoff strategies for rate limiting.
    """

    pass


class PermanentError(ScrapingError):
    """Failure that won't succeed on retry.

    Examples: invalid CSS selector, missing required field, data validation failure.
    """

    pass


class AuthenticationError(PermanentError):
    """Session expired or invalid credentials - need re-authentication.

    Requires human intervention or session refresh, cannot be fixed by retry.
    """

    pass
