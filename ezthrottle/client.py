"""EZThrottle client implementation"""

import json
import time
from typing import Optional, Dict, Any, Callable

import requests

from .webhook import WebhookServer
from .exceptions import EZThrottleError, TimeoutError, AuthenticationError


class EZThrottle:
    """EZThrottle client for handling rate-limited API requests"""
    
    def __init__(
        self,
        api_key: str,
        tracktags_url: str = "https://tracktags.fly.dev",
        webhook_port: Optional[int] = None,
        webhook_callback: Optional[Callable] = None,
        queue_threshold: int = 30,  # Use EZThrottle for waits > 30s
        default_timeout: int = 120,  # 2 minutes default
    ):
        """
        Initialize EZThrottle client
        
        Args:
            api_key: Your TracktTags API key
            tracktags_url: TracktTags proxy URL
            webhook_port: Port for local webhook server (random if None)
            webhook_callback: Callback function for webhook results
            queue_threshold: Minimum retry-after seconds to use EZThrottle
            default_timeout: Default timeout for queued requests
        """
        self.api_key = api_key
        self.tracktags_url = tracktags_url.rstrip('/')
        self.queue_threshold = queue_threshold
        self.default_timeout = default_timeout
        
        # Start webhook server if callback provided
        self.webhook_server = None
        if webhook_callback:
            self.webhook_server = WebhookServer(
                callback=webhook_callback,
                port=webhook_port
            )
            self.webhook_server.start()
    
    def request(
        self,
        url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        """
        Smart request that handles 429s automatically
        
        Args:
            url: Target API URL
            method: HTTP method
            headers: Request headers
            json_data: JSON body (will be serialized)
            data: Raw string body
            timeout: Timeout in seconds
            
        Returns:
            Response from the API (either direct or via webhook)
        """
        # Try direct request first
        response = self._direct_request(url, method, headers, json_data, data)
        
        if response.status_code != 429:
            return response
        
        # Check Retry-After header
        retry_after = int(response.headers.get('Retry-After', 60))
        
        if retry_after <= self.queue_threshold:
            # Short wait - just sleep and retry
            time.sleep(retry_after)
            return self._direct_request(url, method, headers, json_data, data)
        
        # Long wait - use EZThrottle
        return self.queue_and_wait(
            url=url,
            method=method,
            headers=headers,
            json_data=json_data,
            data=data,
            timeout=timeout or self.default_timeout
        )
    
    def queue_and_wait(
        self,
        url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[str] = None,
        timeout: int = 120,
        webhook_url: Optional[str] = None,
    ) -> requests.Response:
        """
        Queue request through EZThrottle and wait for result
        
        Args:
            url: Target API URL
            method: HTTP method
            headers: Request headers
            json_data: JSON body
            data: Raw string body
            timeout: Timeout in seconds
            webhook_url: Custom webhook URL (uses local server if None)
            
        Returns:
            Response from webhook or timeout error
        """
        # Determine webhook URL
        if not webhook_url:
            if not self.webhook_server:
                raise EZThrottleError(
                    "No webhook URL provided and no webhook server running"
                )
            webhook_url = self.webhook_server.get_url()
        
        # Prepare body
        body = data
        if json_data:
            body = json.dumps(json_data)
        
        # Queue the job
        job_id = self._queue_job(
            url=url,
            webhook_url=webhook_url,
            method=method,
            headers=headers or {},
            body=body
        )
        
        # Wait for webhook with timeout
        start_time = time.time()
        
        if self.webhook_server:
            result = self.webhook_server.wait_for_result(job_id, timeout)
            if result:
                return self._create_response_from_webhook(result)
        
        # Timeout - try direct request one more time
        if time.time() - start_time >= timeout:
            response = self._direct_request(url, method, headers, json_data, data)
            if response.status_code != 429:
                return response
            raise TimeoutError(f"Request timed out after {timeout} seconds")
        
        raise TimeoutError(f"No webhook received for job {job_id}")
    
    def _queue_job(
        self,
        url: str,
        webhook_url: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[str],
    ) -> str:
        """Queue job through TracktTags proxy to EZThrottle"""
        
        # Extract customer_id from API key (format: "cust_xxxxx_keyxxxxx")
        customer_id = self.api_key.split('_')[1] if '_' in self.api_key else "unknown"
        
        proxy_payload = {
            "scope": "customer",
            "customer_id": customer_id,
            "metric_name": "ezthrottle_requests",
            "target_url": "https://ezthrottle.fly.dev/api/v1/jobs",
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            "body": json.dumps({
                "url": url,
                "webhook_url": webhook_url,
                "customer_id": customer_id,
                "method": method,
                "headers": headers,
                "body": body
            })
        }
        
        response = requests.post(
            f"{self.tracktags_url}/api/v1/proxy",
            json=proxy_payload,
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        
        if response.status_code == 401:
            raise AuthenticationError("Invalid API key")
        
        if response.status_code == 429:
            # TracktTags is rate limiting us (quota exceeded)
            raise EZThrottleError("Request quota exceeded")
        
        if response.status_code != 200:
            raise EZThrottleError(f"Failed to queue job: {response.text}")
        
        # Extract job_id from response
        result = response.json()
        return result.get("job_id", "unknown")
    
    def _direct_request(
        self,
        url: str,
        method: str,
        headers: Optional[Dict[str, str]],
        json_data: Optional[Dict[str, Any]],
        data: Optional[str],
    ) -> requests.Response:
        """Make direct request to target API"""
        kwargs = {
            "method": method,
            "url": url,
            "headers": headers or {}
        }
        
        if json_data:
            kwargs["json"] = json_data
        elif data:
            kwargs["data"] = data
        
        return requests.request(**kwargs)
    
    def _create_response_from_webhook(self, webhook_data: Dict) -> requests.Response:
        """Create a Response object from webhook data"""
        response = requests.Response()
        response.status_code = webhook_data.get("status", 200)
        response._content = webhook_data.get("response", "").encode('utf-8')
        response.headers = webhook_data.get("headers", {})
        return response
    
    def close(self):
        """Shutdown webhook server if running"""
        if self.webhook_server:
            self.webhook_server.stop()
