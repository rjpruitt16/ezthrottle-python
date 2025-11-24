"""EZThrottle exceptions"""
from typing import Optional, Dict, Any

class EZThrottleError(Exception):
    """Base exception for EZThrottle errors"""
    def __init__(self, message: str, retry_at: Optional[int] = None):
        super().__init__(message)
        self.retry_at = retry_at


class ForwardToEZThrottle(EZThrottleError):
    """
    Raised by user code to force forwarding to EZThrottle.

    Use with @auto_forward decorator for automatic forwarding in legacy code.

    Example with decorator:
        @ezthrottle.auto_forward(client)
        def process_order(order_id):
            response = requests.post("https://api.openai.com/chat", ...)
            if response.status_code == 429:
                raise ForwardToEZThrottle(
                    url="https://api.openai.com/chat",
                    method="POST",
                    headers={"Authorization": "Bearer sk-..."},
                    body='{"model": "gpt-4", ...}',
                    idempotent_key=f"order_{order_id}",
                    metadata={"order_id": order_id}
                )
            return response.json()
    """
    def __init__(
        self,
        message: str = "Forwarding to EZThrottle",
        url: Optional[str] = None,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        idempotent_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        webhooks: Optional[list] = None,
        regions: Optional[list] = None,
        fallback_on_error: Optional[list] = None
    ):
        super().__init__(message)
        self.url = url
        self.method = method
        self.headers = headers or {}
        self.body = body
        self.idempotent_key = idempotent_key
        self.metadata = metadata or {}
        self.webhooks = webhooks or []
        self.regions = regions
        self.fallback_on_error = fallback_on_error or [429, 500, 502, 503, 504]


class AuthenticationError(EZThrottleError):
    """Raised when API key is invalid or missing"""
    pass


class TimeoutError(EZThrottleError):
    """Raised when webhook doesn't arrive within timeout"""
    pass


class QuotaExceededError(EZThrottleError):
    """Raised when request quota is exceeded"""
    pass

