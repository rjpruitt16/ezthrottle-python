"""EZThrottle client implementation via TracktTags proxy"""
import time
import json
from typing import Optional, Dict, Any, List
import requests
from .exceptions import EZThrottleError, TimeoutError

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
