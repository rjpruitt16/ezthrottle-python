"""EZThrottle - The API Dam for rate-limited services"""

from .client import EZThrottle
from .exceptions import EZThrottleError, TimeoutError, AuthenticationError
from .step import Step, StepType, IdempotentStrategy

__version__ = "0.1.0"
__all__ = [
    "EZThrottle",
    "EZThrottleError",
    "TimeoutError",
    "AuthenticationError",
    "Step",
    "StepType",
    "IdempotentStrategy",
]
