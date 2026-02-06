"""EZThrottle client implementation via TracktTags proxy"""
import time
import json
import uuid
from typing import Optional, Dict, Any, List, Callable
from functools import wraps
import requests
from .exceptions import EZThrottleError, TimeoutError, ForwardToEZThrottle

class EZThrottle:
    def __init__(
        self,
        api_key: str,
        tracktags_url: str = "https://tracktags.fly.dev",
        ezthrottle_url: str = "https://ezthrottle.fly.dev",
        webhook_server=None,
        start_webhook_server: bool = False,
        webhook_port: int = 5000
    ):
        """
        Initialize EZThrottle client

        Args:
            api_key: TracktTags customer API key (ck_live_cust_XXX_YYY)
            tracktags_url: TracktTags proxy URL
            ezthrottle_url: EZThrottle target URL (used internally by proxy)
            webhook_server: Optional WebhookServer instance
            start_webhook_server: Auto-start webhook server for workflow orchestration
            webhook_port: Port for webhook server (default: 5000)
        """
        self.api_key = api_key
        self.tracktags_url = tracktags_url
        self.ezthrottle_url = ezthrottle_url
        self.webhook_server = webhook_server

        # Auto-start webhook server if requested
        if start_webhook_server and not self.webhook_server:
            from .webhook import create_webhook_server
            self.webhook_server = create_webhook_server(port=webhook_port, backend="auto")
            self.webhook_server.start()
    
    def submit_job(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        webhooks: Optional[List[Dict[str, Any]]] = None,
        webhook_quorum: int = 1,
        regions: Optional[List[str]] = None,
        region_policy: str = "fallback",
        execution_mode: str = "race",
        retry_policy: Optional[Dict[str, Any]] = None,
        fallback_job: Optional[Dict[str, Any]] = None,
        on_success: Optional[Dict[str, Any]] = None,
        on_failure: Optional[Dict[str, Any]] = None,
        on_failure_timeout_ms: Optional[int] = None,
        idempotent_key: Optional[str] = None,
        retry_at: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Submit a job through TracktTags proxy → EZThrottle

        Args:
            url: Target URL to request
            method: HTTP method (GET, POST, etc)
            headers: Optional request headers
            body: Optional request body
            metadata: Optional metadata
            webhooks: Array of webhook configurations:
                     [{"url": "https://app.com/webhook", "regions": ["iad"], "has_quorum_vote": True}]
            webhook_quorum: Minimum webhooks with has_quorum_vote=true that must succeed (default: 1)
            regions: Regions to execute job in (e.g., ["iad", "lax", "ord"])
            region_policy: "fallback" (auto-route if region down) or "strict" (fail if region down)
            execution_mode: "race" (first completion wins) or "fanout" (all execute)
            retry_policy: Retry configuration:
                         {"max_retries": 3, "max_reroutes": 2, "retry_codes": [429, 503], "reroute_codes": [500, 502]}
            fallback_job: Recursive fallback configuration (see docs for structure)
            on_success: Job to spawn on successful completion
            on_failure: Job to spawn when all execution paths fail
            on_failure_timeout_ms: Timeout before triggering on_failure workflow (milliseconds)
            idempotent_key: Deduplication key (auto-generated if not provided)
            retry_at: Optional timestamp (milliseconds) when job can be retried

        The proxy will:
        1. Authenticate your API key
        2. Check your rate limits
        3. Inject customer_id securely
        4. Forward to EZThrottle
        """
        
        # Build the EZThrottle job payload
        job_payload: Dict[str, Any] = {
            "url": url,
            "method": method.upper(),
        }

        # Add optional parameters
        if headers:
            job_payload["headers"] = headers
        if body:
            job_payload["body"] = body
        if metadata:
            job_payload["metadata"] = metadata
        if webhooks:
            job_payload["webhooks"] = webhooks
        if webhook_quorum != 1:  # Only include if non-default
            job_payload["webhook_quorum"] = webhook_quorum
        if regions:
            job_payload["regions"] = regions
        if region_policy != "fallback":  # Only include if non-default
            job_payload["region_policy"] = region_policy
        if execution_mode != "race":  # Only include if non-default
            job_payload["execution_mode"] = execution_mode
        if retry_policy:
            job_payload["retry_policy"] = retry_policy
        if fallback_job:
            job_payload["fallback_job"] = fallback_job
        if on_success:
            job_payload["on_success"] = on_success
        if on_failure:
            job_payload["on_failure"] = on_failure
        if on_failure_timeout_ms is not None:
            job_payload["on_failure_timeout_ms"] = on_failure_timeout_ms
        if idempotent_key:
            job_payload["idempotent_key"] = idempotent_key
        if retry_at is not None:
            job_payload["retry_at"] = retry_at
        
        # Build proxy request
        proxy_payload = {
            "scope": "customer",
            "metric_name": "",  # Empty = check all plan limits
            "target_url": f"{self.ezthrottle_url}/api/v1/jobs",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(job_payload)
        }
        
        # Call TracktTags proxy (NOT EZThrottle directly)
        response = requests.post(
            f"{self.tracktags_url}/api/v1/proxy",  # ✅ Via proxy
            json=proxy_payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        # Handle proxy responses
        if response.status_code == 429:
            # Rate limited by TracktTags
            error_data = response.json()
            
            # ✅ Extract Retry-After header if present
            retry_after_seconds = response.headers.get("Retry-After")
            if retry_after_seconds:
                retry_after_ms = int(time.time() * 1000) + (int(retry_after_seconds) * 1000)
                error_data["retry_at"] = retry_after_ms  # Add calculated retry_at
            
            raise EZThrottleError(
                f"Rate limited: {error_data.get('error', 'Unknown error')}",
                retry_at=error_data.get("retry_at")
            )
        
        if response.status_code != 200:
            raise EZThrottleError(f"Proxy request failed: {response.text}")
        
        # Extract forwarded response from proxy
        proxy_response = response.json()
        
        if proxy_response.get("status") != "allowed":
            raise EZThrottleError(
                f"Request denied: {proxy_response.get('error', 'Unknown error')}"
            )
        
        # Get the actual EZThrottle response
        forwarded = proxy_response.get("forwarded_response", {})

        status_code = forwarded.get("status_code")
        if status_code < 200 or status_code >= 300:
            raise EZThrottleError(
                f"EZThrottle job creation failed: {forwarded.get('body', 'Unknown error')}"
            )
        
        # Parse EZThrottle response
        ezthrottle_response = json.loads(forwarded.get("body", "{}"))
        
        return ezthrottle_response
    
    def request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
    ) -> requests.Response:
        """Make a direct HTTP request (bypasses both TracktTags and EZThrottle)"""
        
        req_headers = headers or {}
        req_method = getattr(requests, method.lower())
        
        response = req_method(
            url,
            headers=req_headers,
            data=body,
            timeout=30
        )
        
        return response
    
    def queue_request(
        self,
        url: str,
        webhook_url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        retry_at: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        DEPRECATED: Use submit_job() instead.
        Legacy method for backward compatibility.
        """
        # Convert singular webhook_url to webhooks array
        webhooks = [{"url": webhook_url, "has_quorum_vote": True}] if webhook_url else None

        return self.submit_job(
            url=url,
            method=method,
            headers=headers,
            body=body,
            metadata=metadata,
            webhooks=webhooks,
            retry_at=retry_at,
        )

    def queue_and_wait(
        self,
        url: str,
        webhook_url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        timeout: int = 300,
        poll_interval: int = 2,
        metadata: Optional[Dict[str, str]] = None,
        retry_at: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Queue a request and wait for the webhook response"""

        # Queue the request via proxy (uses legacy method for backward compat)
        result = self.queue_request(
            url=url,
            webhook_url=webhook_url,
            method=method,
            headers=headers,
            body=body,
            metadata=metadata,
            retry_at=retry_at,
        )

        job_id = result.get("job_id")
        if not job_id:
            raise EZThrottleError("No job_id in response")

        # Poll webhook URL for result
        start_time = time.time()
        while time.time() - start_time < timeout:
            # User should implement their own webhook polling
            # This is just a placeholder
            time.sleep(poll_interval)

        raise TimeoutError(f"Timeout waiting for job {job_id}")

    # ============================================================================
    # WEBHOOK SECRETS MANAGEMENT
    # ============================================================================

    def create_webhook_secret(
        self,
        primary_secret: str,
        secondary_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create or update webhook HMAC secrets for signature verification.

        Args:
            primary_secret: Primary webhook secret (min 16 characters)
            secondary_secret: Optional secondary secret for rotation (min 16 characters)

        Returns:
            Response dict with status and message

        Raises:
            EZThrottleError: If secret creation fails

        Example:
            ```python
            # Create primary secret
            client.create_webhook_secret(
                primary_secret="your_secure_secret_here_min_16_chars"
            )

            # Create with rotation support (primary + secondary)
            client.create_webhook_secret(
                primary_secret="new_secret_after_rotation",
                secondary_secret="old_secret_before_rotation"
            )
            ```
        """
        if len(primary_secret) < 16:
            raise ValueError("primary_secret must be at least 16 characters")

        if secondary_secret and len(secondary_secret) < 16:
            raise ValueError("secondary_secret must be at least 16 characters")

        payload = {"primary_secret": primary_secret}
        if secondary_secret:
            payload["secondary_secret"] = secondary_secret

        # Build proxy request
        proxy_payload = {
            "scope": "customer",
            "metric_name": "",
            "target_url": f"{self.ezthrottle_url}/api/v1/webhook-secrets",
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload)
        }

        response = requests.post(
            f"{self.tracktags_url}/api/v1/proxy",
            json=proxy_payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        if response.status_code != 200:
            raise EZThrottleError(f"Failed to create webhook secret: {response.text}")

        proxy_response = response.json()
        if proxy_response.get("status") != "allowed":
            raise EZThrottleError(
                f"Request denied: {proxy_response.get('error', 'Unknown error')}"
            )

        forwarded = proxy_response.get("forwarded_response", {})
        return json.loads(forwarded.get("body", "{}"))

    def get_webhook_secret(self) -> Dict[str, Any]:
        """
        Get webhook secrets (masked for security).

        Returns:
            Dict with masked secrets:
            {
                "customer_id": "cust_XXX",
                "primary_secret": "abcd****efgh",
                "secondary_secret": "ijkl****mnop" or null,
                "has_secondary": true/false
            }

        Raises:
            EZThrottleError: If secrets not configured (404) or request fails

        Example:
            ```python
            secrets = client.get_webhook_secret()
            print(f"Primary: {secrets['primary_secret']}")  # abcd****efgh
            print(f"Has secondary: {secrets['has_secondary']}")  # True/False
            ```
        """
        proxy_payload = {
            "scope": "customer",
            "metric_name": "",
            "target_url": f"{self.ezthrottle_url}/api/v1/webhook-secrets",
            "method": "GET",
            "headers": {},
            "body": ""
        }

        response = requests.post(
            f"{self.tracktags_url}/api/v1/proxy",
            json=proxy_payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        if response.status_code != 200:
            raise EZThrottleError(f"Failed to get webhook secret: {response.text}")

        proxy_response = response.json()
        if proxy_response.get("status") != "allowed":
            raise EZThrottleError(
                f"Request denied: {proxy_response.get('error', 'Unknown error')}"
            )

        forwarded = proxy_response.get("forwarded_response", {})
        status_code = forwarded.get("status_code")

        if status_code == 404:
            raise EZThrottleError("No webhook secrets configured. Call create_webhook_secret() first.")

        if status_code < 200 or status_code >= 300:
            raise EZThrottleError(f"Failed to get webhook secrets: {forwarded.get('body')}")

        return json.loads(forwarded.get("body", "{}"))

    def delete_webhook_secret(self) -> Dict[str, Any]:
        """
        Delete webhook secrets.

        Returns:
            Response dict with status and message

        Raises:
            EZThrottleError: If deletion fails

        Example:
            ```python
            result = client.delete_webhook_secret()
            print(result)  # {"status": "ok", "message": "Webhook secrets deleted"}
            ```
        """
        proxy_payload = {
            "scope": "customer",
            "metric_name": "",
            "target_url": f"{self.ezthrottle_url}/api/v1/webhook-secrets",
            "method": "DELETE",
            "headers": {},
            "body": ""
        }

        response = requests.post(
            f"{self.tracktags_url}/api/v1/proxy",
            json=proxy_payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=30
        )

        if response.status_code != 200:
            raise EZThrottleError(f"Failed to delete webhook secret: {response.text}")

        proxy_response = response.json()
        if proxy_response.get("status") != "allowed":
            raise EZThrottleError(
                f"Request denied: {proxy_response.get('error', 'Unknown error')}"
            )

        forwarded = proxy_response.get("forwarded_response", {})
        return json.loads(forwarded.get("body", "{}"))

    def rotate_webhook_secret(self, new_secret: str) -> Dict[str, Any]:
        """
        Rotate webhook secret safely by promoting secondary to primary.

        This is a convenience method that handles secret rotation:
        1. Get current primary secret
        2. Set new secret as primary, old primary as secondary
        3. After verifying new secret works, call again with only new secret

        Args:
            new_secret: New webhook secret to set as primary

        Returns:
            Response dict with status and message

        Example:
            ```python
            # Step 1: Rotate (keeps old secret as backup)
            client.rotate_webhook_secret("new_secret_min_16_chars")

            # Step 2: After verifying webhooks work with new secret
            # Remove old secret by setting only new one
            client.create_webhook_secret("new_secret_min_16_chars")
            ```
        """
        if len(new_secret) < 16:
            raise ValueError("new_secret must be at least 16 characters")

        try:
            # Get current secret to use as secondary
            current = self.get_webhook_secret()
            old_primary = current.get("primary_secret", "")

            # If we have a masked secret, we can't use it as secondary
            # In this case, just set the new secret without secondary
            if "****" in old_primary:
                return self.create_webhook_secret(new_secret)

            # Set new as primary, old as secondary
            return self.create_webhook_secret(
                primary_secret=new_secret,
                secondary_secret=old_primary
            )

        except EZThrottleError as e:
            if "No webhook secrets configured" in str(e):
                # No existing secret, just create new one
                return self.create_webhook_secret(new_secret)
            raise

    def forward_or_fallback(
        self,
        fallback: Callable[[], Any],
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Try to forward request to EZThrottle, fall back to callback if EZThrottle is unreachable.

        This makes EZThrottle a reliability LAYER, not a single point of failure.
        If EZThrottle is down, you just lose the extra reliability features and
        fall back to your existing solution.

        Args:
            fallback: Callback function to execute if EZThrottle is unreachable.
                      Should return the same type of response you'd get from your
                      existing HTTP client (e.g., requests.Response).
            url: Target URL to request
            method: HTTP method (GET, POST, etc)
            headers: Optional request headers
            body: Optional request body
            **kwargs: Additional arguments passed to submit_job()

        Returns:
            Either EZThrottle job response or the fallback function's return value

        Example:
            ```python
            # If EZThrottle is down, fall back to direct HTTP call
            result = client.forward_or_fallback(
                fallback=lambda: requests.post(
                    "https://api.stripe.com/charges",
                    headers={"Authorization": "Bearer sk_live_..."},
                    json={"amount": 1000}
                ),
                url="https://api.stripe.com/charges",
                method="POST",
                headers={"Authorization": "Bearer sk_live_..."},
                body='{"amount": 1000}',
                webhooks=[{"url": "https://your-app.com/webhook"}]
            )
            ```

        Note:
            The fallback is ONLY called when EZThrottle itself is unreachable
            (connection errors, timeouts). It is NOT called for rate limiting
            or other EZThrottle errors - those indicate EZThrottle is working
            and you should handle them appropriately.
        """
        try:
            return self.submit_job(
                url=url,
                method=method,
                headers=headers,
                body=body,
                **kwargs
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            # EZThrottle is unreachable - use fallback
            return fallback()


def auto_forward(client: EZThrottle) -> Callable:
    """
    Decorator that automatically forwards ForwardToEZThrottle exceptions to EZThrottle.

    Perfect for integrating EZThrottle into legacy code without major refactoring.

    Usage:
        @ezthrottle.auto_forward(client)
        def process_payment(order_id):
            try:
                response = requests.post(
                    "https://api.stripe.com/charges",
                    headers={"Authorization": "Bearer sk_live_..."},
                    json={"amount": 1000, "currency": "usd"}
                )

                if response.status_code == 429:
                    # Auto-forwarded to EZThrottle
                    raise ForwardToEZThrottle(
                        url="https://api.stripe.com/charges",
                        method="POST",
                        headers={"Authorization": "Bearer sk_live_..."},
                        body='{"amount": 1000, "currency": "usd"}',
                        idempotent_key=f"order_{order_id}",
                        metadata={"order_id": order_id}
                    )

                return response.json()

            except requests.RequestException:
                # Network error - auto-forwarded to EZThrottle
                raise ForwardToEZThrottle(...)

        # Decorator catches exception and forwards to EZThrottle
        result = process_payment("12345")  # Returns {"job_id": "...", "status": "queued"}

    Args:
        client: EZThrottle client instance

    Returns:
        Decorated function that auto-forwards ForwardToEZThrottle exceptions
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ForwardToEZThrottle as e:
                # Validate required fields
                if not e.url:
                    raise ValueError("ForwardToEZThrottle requires 'url' field")

                # Generate idempotent key if not provided (UNIQUE strategy)
                if not e.idempotent_key:
                    e.idempotent_key = str(uuid.uuid4())

                # Auto-forward to EZThrottle
                result = client.submit_job(
                    url=e.url,
                    method=e.method,
                    headers=e.headers,
                    body=e.body,
                    idempotent_key=e.idempotent_key,
                    metadata=e.metadata,
                    webhooks=e.webhooks,
                    regions=e.regions
                )

                return result

        return wrapper
    return decorator
