"""EZThrottle exceptions"""


class EZThrottleError(Exception):
    """Base exception for EZThrottle SDK"""
    pass


class AuthenticationError(EZThrottleError):
    """Raised when API key is invalid or missing"""
    pass


class TimeoutError(EZThrottleError):
    """Raised when webhook doesn't arrive within timeout"""
    pass


class QuotaExceededError(EZThrottleError):
    """Raised when request quota is exceeded"""
    pass
