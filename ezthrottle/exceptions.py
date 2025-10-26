"""EZThrottle exceptions"""
from typing import Optional

class EZThrottleError(Exception):
    """Base exception for EZThrottle errors"""
    def __init__(self, message: str, retry_at: Optional[int] = None):
        super().__init__(message)
        self.retry_at = retry_at  



class AuthenticationError(EZThrottleError):
    """Raised when API key is invalid or missing"""
    pass


class TimeoutError(EZThrottleError):
    """Raised when webhook doesn't arrive within timeout"""
    pass


class QuotaExceededError(EZThrottleError):
    """Raised when request quota is exceeded"""
    pass

