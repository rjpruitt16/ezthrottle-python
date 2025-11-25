"""EZThrottle - The API Dam for rate-limited services"""

from .client import EZThrottle, auto_forward
from .exceptions import EZThrottleError, TimeoutError, AuthenticationError, ForwardToEZThrottle
from .step import Step, StepType, IdempotentStrategy
from .webhook_utils import (
    verify_webhook_signature,
    verify_webhook_signature_strict,
    try_verify_with_secrets,
    WebhookVerificationError
)

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
    "verify_webhook_signature",
    "verify_webhook_signature_strict",
    "try_verify_with_secrets",
    "WebhookVerificationError",
]
