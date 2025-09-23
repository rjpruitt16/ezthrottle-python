"""EZThrottle - The API Dam for rate-limited services"""

from .client import EZThrottle
from .exceptions import EZThrottleError, TimeoutError, AuthenticationError

__version__ = "0.1.0"
__all__ = ["EZThrottle", "EZThrottleError", "TimeoutError", "AuthenticationError"]
