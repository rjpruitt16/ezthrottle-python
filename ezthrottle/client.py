"""EZThrottle client implementation via TracktTags proxy"""
import time
import json
from typing import Optional, Dict, Any
import requests
from .exceptions import EZThrottleError, TimeoutError

class EZThrottle:
    def __init__(
        self, 
        api_key: str,
        tracktags_url: str = "https://tracktags.fly.dev",
        ezthrottle_url: str = "https://ezthrottle.fly.dev"
    ):
        """
        Initialize EZThrottle client
        
        Args:
            api_key: TracktTags customer API key (ck_live_cust_XXX_YYY)
            tracktags_url: TracktTags proxy URL
            ezthrottle_url: EZThrottle target URL (used internally by proxy)
        """
        self.api_key = api_key
        self.tracktags_url = tracktags_url
        self.ezthrottle_url = ezthrottle_url
    
    def queue_request(
        self,
        url: str,
        webhook_url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        retry_at: Optional[int] = None,  # ✅ NEW: timestamp in milliseconds
    ) -> Dict[str, Any]:
        """
        Queue a request through TracktTags proxy → EZThrottle
        
        Args:
            url: Target URL to request
            webhook_url: Where to send the result
            method: HTTP method (GET, POST, etc)
            headers: Optional request headers
            body: Optional request body
            metadata: Optional metadata
            retry_at: Optional timestamp (milliseconds) when job can be retried
                     Use this if you want to control retry timing yourself
        
        The proxy will:
        1. Authenticate your API key
        2. Check your rate limits
        3. Inject customer_id securely
        4. Forward to EZThrottle
        """
        
        # Build the EZThrottle job payload
        job_payload: Dict[str, Any] = {
            "url": url,
            "webhook_url": webhook_url,
            "method": method.upper(),
        }
        
        if headers:
            job_payload["headers"] = headers
        if body:
            job_payload["body"] = body
        if metadata:
            job_payload["metadata"] = metadata
        if retry_at is not None:
            job_payload["retry_at"] = retry_at  # ✅ Pass retry_at to EZThrottle
        
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
        
        if forwarded.get("status_code") != 201:
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
        retry_at: Optional[int] = None,  # ✅ NEW
    ) -> Dict[str, Any]:
        """Queue a request and wait for the webhook response"""
        
        # Queue the request via proxy
        result = self.queue_request(
            url=url,
            webhook_url=webhook_url,
            method=method,
            headers=headers,
            body=body,
            metadata=metadata,
            retry_at=retry_at,  # ✅ Pass through
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
