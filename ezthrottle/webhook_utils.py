"""
Webhook utilities for EZThrottle SDK.

Provides HMAC signature verification for secure webhook delivery.
"""

import hmac
import hashlib
import time
from typing import Tuple, Optional


class WebhookVerificationError(Exception):
    """Raised when webhook signature verification fails"""
    pass


def verify_webhook_signature(
    payload: bytes,
    signature_header: str,
    secret: str,
    tolerance: int = 300
) -> Tuple[bool, str]:
    """
    Verify HMAC-SHA256 signature from X-EZThrottle-Signature header.

    Args:
        payload: Raw webhook payload bytes (request body)
        signature_header: Value of X-EZThrottle-Signature header
        secret: Your webhook secret (primary or secondary)
        tolerance: Maximum age of timestamp in seconds (default: 300 = 5 minutes)

    Returns:
        Tuple of (verified: bool, reason: str)
        - (True, "valid") if signature is valid
        - (False, reason) if verification fails with explanation

    Example:
        ```python
        from flask import Flask, request
        from ezthrottle.webhook_utils import verify_webhook_signature

        app = Flask(__name__)
        WEBHOOK_SECRET = "your_webhook_secret"

        @app.route('/webhook', methods=['POST'])
        def webhook():
            payload = request.get_data()
            signature = request.headers.get('X-EZThrottle-Signature', '')

            verified, reason = verify_webhook_signature(
                payload, signature, WEBHOOK_SECRET
            )

            if not verified:
                return {'error': f'Invalid signature: {reason}'}, 401

            # Process webhook...
            data = request.json
            print(f"Job {data['job_id']} completed: {data['status']}")

            return {'ok': True}
        ```
    """
    if not signature_header:
        return False, "no_signature_header"

    try:
        # Parse "t=timestamp,v1=signature" format
        parts = {}
        for part in signature_header.split(','):
            if '=' in part:
                key, value = part.split('=', 1)
                parts[key] = value

        timestamp_str = parts.get('t', '0')
        signature = parts.get('v1', '')

        if not signature:
            return False, "missing_v1_signature"

        # Check timestamp tolerance
        now = int(time.time())
        sig_time = int(timestamp_str)
        time_diff = abs(now - sig_time)

        if time_diff > tolerance:
            return False, f"timestamp_expired (diff={time_diff}s, tolerance={tolerance}s)"

        # Compute expected signature
        signed_payload = f"{timestamp_str}.{payload.decode('utf-8')}"
        expected = hmac.new(
            secret.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # Constant-time comparison
        if hmac.compare_digest(signature, expected):
            return True, "valid"
        else:
            return False, "signature_mismatch"

    except Exception as e:
        return False, f"verification_error: {str(e)}"


def verify_webhook_signature_strict(
    payload: bytes,
    signature_header: str,
    secret: str,
    tolerance: int = 300
) -> None:
    """
    Verify webhook signature and raise exception if invalid.

    Args:
        payload: Raw webhook payload bytes
        signature_header: Value of X-EZThrottle-Signature header
        secret: Your webhook secret
        tolerance: Maximum age of timestamp in seconds (default: 300)

    Raises:
        WebhookVerificationError: If signature verification fails

    Example:
        ```python
        from flask import Flask, request
        from ezthrottle.webhook_utils import verify_webhook_signature_strict, WebhookVerificationError

        @app.route('/webhook', methods=['POST'])
        def webhook():
            try:
                verify_webhook_signature_strict(
                    request.get_data(),
                    request.headers.get('X-EZThrottle-Signature', ''),
                    WEBHOOK_SECRET
                )
            except WebhookVerificationError as e:
                return {'error': str(e)}, 401

            # Process webhook...
            return {'ok': True}
        ```
    """
    verified, reason = verify_webhook_signature(payload, signature_header, secret, tolerance)

    if not verified:
        raise WebhookVerificationError(f"Webhook signature verification failed: {reason}")


def try_verify_with_secrets(
    payload: bytes,
    signature_header: str,
    primary_secret: str,
    secondary_secret: Optional[str] = None,
    tolerance: int = 300
) -> Tuple[bool, str]:
    """
    Try verifying signature with primary secret, fall back to secondary if provided.

    Useful during secret rotation when you have both old and new secrets active.

    Args:
        payload: Raw webhook payload bytes
        signature_header: Value of X-EZThrottle-Signature header
        primary_secret: Your primary webhook secret
        secondary_secret: Your secondary webhook secret (optional)
        tolerance: Maximum age of timestamp in seconds

    Returns:
        Tuple of (verified: bool, reason: str)
        - (True, "valid_primary") if primary secret verified
        - (True, "valid_secondary") if secondary secret verified
        - (False, reason) if both secrets failed

    Example:
        ```python
        # During secret rotation
        verified, reason = try_verify_with_secrets(
            payload,
            signature_header,
            primary_secret="new_secret_after_rotation",
            secondary_secret="old_secret_before_rotation"
        )

        if verified:
            print(f"Signature verified with {reason}")
        ```
    """
    # Try primary secret first
    verified, reason = verify_webhook_signature(payload, signature_header, primary_secret, tolerance)

    if verified:
        return True, "valid_primary"

    # Try secondary secret if provided
    if secondary_secret:
        verified, reason = verify_webhook_signature(payload, signature_header, secondary_secret, tolerance)

        if verified:
            return True, "valid_secondary"

    return False, f"both_secrets_failed (primary: {reason})"
