"""EZThrottle - The API Dam for rate-limited services"""

from .client import EZThrottle, auto_forward
from .exceptions import EZThrottleError, TimeoutError, AuthenticationError, ForwardToEZThrottle
from .step import Step, StepType, IdempotentStrategy

__version__ = "1.1.0"
__all__ = [
    "EZThrottle",
    "auto_forward",
    "EZThrottleError",
    "TimeoutError",
    "AuthenticationError",
    "ForwardToEZThrottle",
    "Step",
    "StepType",
    "IdempotentStrategy",
]
