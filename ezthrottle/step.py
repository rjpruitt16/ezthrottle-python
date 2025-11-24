"""Step builder pattern for EZThrottle workflows"""

from enum import Enum
from typing import Optional, Dict, Any, List
import uuid
import requests
from .exceptions import EZThrottleError, ForwardToEZThrottle


class StepType(Enum):
    """Step execution strategy"""
    FRUGAL = "frugal"  # Client executes first, queue on error
    PERFORMANCE = "performance"  # Server executes immediately


class IdempotentStrategy(Enum):
    """Idempotent key generation strategy"""
    HASH = "hash"  # Backend hashes (url, method, body) - prevents duplicates (DEFAULT)
    UNIQUE = "unique"  # SDK generates UUID - allows duplicates (polling, webhooks)


class Step:
    """
    Fluent builder for EZThrottle job steps

    Usage:
        step = (
            Step()
            .url("https://api.example.com")
            .method("POST")
            .type(StepType.FRUGAL)
            .fallback_on_error([429, 500])
            .on_success(success_step)
            .execute(client)
        )
    """

    def __init__(self, client=None):
        """Initialize step builder"""
        self.client = client
        self._step_type = StepType.PERFORMANCE  # Default to performance

        # Request configuration
        self._url: Optional[str] = None
        self._method: str = "GET"
        self._headers: Dict[str, str] = {}
        self._body: Optional[str] = None
        self._metadata: Dict[str, str] = {}

        # Webhooks configuration
        self._webhooks: List[Dict[str, Any]] = []
        self._webhook_quorum: int = 1

        # Multi-region configuration
        self._regions: Optional[List[str]] = None
        self._region_policy: str = "fallback"
        self._execution_mode: str = "race"

        # Retry configuration
        self._retry_policy: Optional[Dict[str, Any]] = None
        self._retry_at: Optional[int] = None

        # Deduplication
        self._idempotent_key: Optional[str] = None
        self._idempotent_strategy: IdempotentStrategy = IdempotentStrategy.HASH  # Default

        # Frugal-specific: error codes that trigger EZThrottle forwarding
        self._fallback_on_error: List[int] = [429, 500, 502, 503, 504]
        self._local_timeout: int = 30

        # Workflow chaining
        self._fallback_steps: List[tuple] = []  # [(step, trigger_config), ...]
        self._on_success_step: Optional['Step'] = None
        self._on_failure_step: Optional['Step'] = None
        self._on_failure_timeout_ms: Optional[int] = None

    def type(self, step_type: StepType) -> 'Step':
        """Set step type (FRUGAL or PERFORMANCE)"""
        self._step_type = step_type
        return self

    def url(self, url: str) -> 'Step':
        """Set target URL"""
        self._url = url
        return self

    def method(self, method: str) -> 'Step':
        """Set HTTP method"""
        self._method = method.upper()
        return self

    def headers(self, headers: Dict[str, str]) -> 'Step':
        """Set request headers"""
        self._headers = headers
        return self

    def body(self, body: str) -> 'Step':
        """Set request body"""
        self._body = body
        return self

    def metadata(self, metadata: Dict[str, str]) -> 'Step':
        """Set metadata"""
        self._metadata = metadata
        return self

    def webhooks(self, webhooks: List[Dict[str, Any]]) -> 'Step':
        """Set webhooks array"""
        self._webhooks = webhooks
        return self

    def webhook_quorum(self, quorum: int) -> 'Step':
        """Set minimum webhooks that must succeed"""
        self._webhook_quorum = quorum
        return self

    def regions(self, regions: List[str]) -> 'Step':
        """Set regions for multi-region execution"""
        self._regions = regions
        return self

    def region_policy(self, policy: str) -> 'Step':
        """Set region policy (fallback or strict)"""
        self._region_policy = policy
        return self

    def execution_mode(self, mode: str) -> 'Step':
        """Set execution mode (race or fanout)"""
        self._execution_mode = mode
        return self

    def retry_policy(self, policy: Dict[str, Any]) -> 'Step':
        """Set retry policy"""
        self._retry_policy = policy
        return self

    def retry_at(self, timestamp_ms: int) -> 'Step':
        """Set retry timestamp (milliseconds)"""
        self._retry_at = timestamp_ms
        return self

    def idempotent_key(self, key: str) -> 'Step':
        """Set custom idempotent key for deduplication"""
        self._idempotent_key = key
        return self

    def idempotent_strategy(self, strategy: IdempotentStrategy) -> 'Step':
        """
        Set idempotent key generation strategy

        HASH (default): Backend generates deterministic hash - prevents duplicates
        UNIQUE: SDK generates UUID per request - allows duplicates (polling, webhooks)
        """
        self._idempotent_strategy = strategy
        return self

    def fallback_on_error(self, codes: List[int]) -> 'Step':
        """
        (FRUGAL only) Set error codes that trigger EZThrottle forwarding
        Default: [429, 500, 502, 503, 504]
        """
        self._fallback_on_error = codes
        return self

    def local_timeout(self, timeout: int) -> 'Step':
        """
        (FRUGAL only) Set timeout for local execution
        Default: 30 seconds
        """
        self._local_timeout = timeout
        return self

    def fallback(
        self,
        step: 'Step',
        trigger_on_error: Optional[List[int]] = None,
        trigger_on_timeout: Optional[int] = None
    ) -> 'Step':
        """Add fallback step with trigger conditions"""
        trigger = {}
        if trigger_on_error:
            trigger = {"type": "on_error", "codes": trigger_on_error}
        elif trigger_on_timeout:
            trigger = {"type": "on_timeout", "timeout_ms": trigger_on_timeout}

        self._fallback_steps.append((step, trigger))
        return self

    def on_success(self, step: 'Step') -> 'Step':
        """Chain step to execute on success"""
        self._on_success_step = step
        return self

    def on_failure(self, step: 'Step', timeout_ms: Optional[int] = None) -> 'Step':
        """Chain step to execute on failure"""
        self._on_failure_step = step
        if timeout_ms:
            self._on_failure_timeout_ms = timeout_ms
        return self

    def _build_job_payload(self) -> Dict[str, Any]:
        """Build EZThrottle job payload from step configuration"""
        if not self._url:
            raise ValueError("URL is required")

        payload: Dict[str, Any] = {
            "url": self._url,
            "method": self._method,
        }

        # Add optional fields
        if self._headers:
            payload["headers"] = self._headers
        if self._body:
            payload["body"] = self._body
        if self._metadata:
            payload["metadata"] = self._metadata
        if self._webhooks:
            payload["webhooks"] = self._webhooks
        if self._webhook_quorum != 1:
            payload["webhook_quorum"] = self._webhook_quorum
        if self._regions:
            payload["regions"] = self._regions
        if self._region_policy != "fallback":
            payload["region_policy"] = self._region_policy
        if self._execution_mode != "race":
            payload["execution_mode"] = self._execution_mode
        if self._retry_policy:
            payload["retry_policy"] = self._retry_policy
        if self._retry_at is not None:
            payload["retry_at"] = self._retry_at

        # Handle idempotent key based on strategy
        if self._idempotent_key:
            # User provided custom key
            payload["idempotent_key"] = self._idempotent_key
        elif self._idempotent_strategy == IdempotentStrategy.UNIQUE:
            # Generate UUID for unique-per-request strategy
            payload["idempotent_key"] = str(uuid.uuid4())
        # else: HASH strategy - let backend generate deterministic hash

        # Add fallback chain
        if self._fallback_steps:
            payload["fallback_job"] = self._build_fallback_chain()

        # Add workflow chaining
        if self._on_success_step:
            payload["on_success"] = self._on_success_step._build_job_payload()
        if self._on_failure_step:
            payload["on_failure"] = self._on_failure_step._build_job_payload()
        if self._on_failure_timeout_ms is not None:
            payload["on_failure_timeout_ms"] = self._on_failure_timeout_ms

        return payload

    def _build_fallback_chain(self) -> Optional[Dict[str, Any]]:
        """Build recursive fallback chain"""
        if not self._fallback_steps:
            return None

        # Build chain recursively (first fallback → second fallback → ...)
        fallback_job = None
        for step, trigger in reversed(self._fallback_steps):
            current_fallback = step._build_job_payload()
            current_fallback["trigger"] = trigger

            # Attach nested fallback
            if fallback_job:
                current_fallback["fallback_job"] = fallback_job

            fallback_job = current_fallback

        return fallback_job

    def _execute_local(self) -> requests.Response:
        """Execute HTTP request locally (FRUGAL mode)"""
        if not self._url:
            raise ValueError("URL is required")

        req_method = getattr(requests, self._method.lower())

        return req_method(
            self._url,
            headers=self._headers,
            data=self._body,
            timeout=self._local_timeout
        )

    def _try_local_fallbacks(self, client, error_code: Optional[int]) -> Optional[Dict[str, Any]]:
        """
        Try all fallback steps locally

        Args:
            client: EZThrottle client
            error_code: Error code from primary step (None for network errors)

        Returns:
            Success result if any fallback succeeds, None if all fail
        """
        for fallback_step, trigger_config in self._fallback_steps:
            # Check if this fallback should be triggered
            should_trigger = False

            if trigger_config:
                trigger_type = trigger_config.get("type")
                if trigger_type == "on_error":
                    trigger_codes = trigger_config.get("codes", [])
                    if error_code and error_code in trigger_codes:
                        should_trigger = True
                elif trigger_type == "on_timeout":
                    # For timeout trigger, always try (we don't implement timeout tracking locally)
                    should_trigger = True
            else:
                # No trigger specified, always try
                should_trigger = True

            if not should_trigger:
                continue

            # Try this fallback locally
            try:
                # Only execute fallback if it's FRUGAL type
                if fallback_step._step_type == StepType.FRUGAL:
                    result = fallback_step.execute(client)
                    # If fallback succeeded, return immediately
                    if result.get("status") == "success":
                        return result
                else:
                    # PERFORMANCE fallback - can't execute locally, skip
                    continue

            except Exception as e:
                # Fallback failed, try next one
                continue

        # All fallbacks failed
        return None

    def execute(self, client=None) -> Dict[str, Any]:
        """
        Execute the step workflow

        For FRUGAL: Executes locally first, forwards to EZThrottle on error
        For PERFORMANCE: Submits to EZThrottle immediately
        """
        if client is None and self.client is None:
            raise ValueError("Client is required. Pass client to execute() or Step(client)")

        client = client or self.client

        if self._step_type == StepType.FRUGAL:
            return self._execute_frugal(client)
        else:
            return self._execute_performance(client)

    def _execute_frugal(self, client) -> Dict[str, Any]:
        """Execute FRUGAL workflow (local first, try fallbacks, then queue on error)"""
        # Try primary step locally
        try:
            response = self._execute_local()

            # Success! Execute on_success and return
            if 200 <= response.status_code < 300:
                # Execute on_success workflow if present
                if self._on_success_step:
                    self._on_success_step.execute(client)

                return {
                    "status": "success",
                    "executed_locally": True,
                    "status_code": response.status_code,
                    "response": response.text
                }

            # Error - try fallback chain locally
            if response.status_code in self._fallback_on_error:
                fallback_result = self._try_local_fallbacks(client, response.status_code)
                if fallback_result:
                    return fallback_result

                # All fallbacks failed → forward to EZThrottle
                return self._forward_to_ezthrottle(client)

            # Non-trigger error - don't forward, just return error
            return {
                "status": "failed",
                "executed_locally": True,
                "status_code": response.status_code,
                "error": f"Request failed: {response.status_code}"
            }

        except ForwardToEZThrottle as e:
            # User explicitly requested forwarding to EZThrottle
            # Use custom idempotent key and metadata from exception
            if e.idempotent_key:
                self._idempotent_key = e.idempotent_key
            if e.metadata:
                self._metadata.update(e.metadata)

            return self._forward_to_ezthrottle(client)

        except (requests.Timeout, requests.RequestException) as e:
            # Network error → try fallbacks, then forward to EZThrottle
            fallback_result = self._try_local_fallbacks(client, None)
            if fallback_result:
                return fallback_result

            return self._forward_to_ezthrottle(client)

    def _forward_to_ezthrottle(self, client) -> Dict[str, Any]:
        """Forward job to EZThrottle with fallback chain and register workflow continuation"""
        payload = self._build_job_payload()

        # If client has webhook server and we have workflows, add webhook and register
        if client.webhook_server and (self._on_success_step or self._on_failure_step):
            webhook_url = client.webhook_server.get_url()

            # Add webhook to payload if not already present
            if not payload.get("webhooks"):
                payload["webhooks"] = []
            payload["webhooks"].append({"url": webhook_url, "has_quorum_vote": True})

        # Submit job
        result = client.submit_job(**payload)
        job_id = result.get("job_id")

        # Register workflow continuation
        if client.webhook_server and job_id and (self._on_success_step or self._on_failure_step):
            client.webhook_server.register_workflow(
                job_id=job_id,
                on_success=self._on_success_step,
                on_failure=self._on_failure_step,
                client=client
            )

        return result

    def _execute_performance(self, client) -> Dict[str, Any]:
        """Execute PERFORMANCE workflow (submit to EZThrottle immediately)"""
        payload = self._build_job_payload()

        # If client has webhook server and we have workflows, add webhook and register
        if client.webhook_server and (self._on_success_step or self._on_failure_step):
            webhook_url = client.webhook_server.get_url()

            # Add webhook to payload if not already present
            if not payload.get("webhooks"):
                payload["webhooks"] = []
            payload["webhooks"].append({"url": webhook_url, "has_quorum_vote": True})

        # Submit job
        result = client.submit_job(**payload)
        job_id = result.get("job_id")

        # Register workflow continuation
        if client.webhook_server and job_id and (self._on_success_step or self._on_failure_step):
            client.webhook_server.register_workflow(
                job_id=job_id,
                on_success=self._on_success_step,
                on_failure=self._on_failure_step,
                client=client
            )

        return result
