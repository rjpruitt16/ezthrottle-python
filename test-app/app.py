"""
EZThrottle Python SDK Integration Test App

Single FastAPI server with:
- Test endpoints (submit jobs, return immediately with job_id)
- Webhook endpoint (receive results from EZThrottle)
- Query endpoints (hurl tests poll for webhooks)

Flow:
1. POST /test/xxx → Submit job → Return job_id immediately
2. EZThrottle executes job → Sends webhook to /webhook
3. Hurl test polls GET /webhooks/{job_id} until webhook arrives

Deploy: fly launch --name ezthrottle-sdk-py
Test: hurl tests/*.hurl --test
"""

import os
import sys
import uuid
import time
import json
from threading import Lock
from typing import Dict, Any, Optional
from datetime import datetime

# Add parent directory to path for local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

from ezthrottle import (
    EZThrottle, Step, StepType, IdempotentStrategy,
    ForwardToEZThrottle, auto_forward
)

app = FastAPI(
    title="EZThrottle Python SDK Test App",
    version="1.1.0",
    description="Integration tests for EZThrottle Python SDK"
)

# Configuration
API_KEY = os.getenv("EZTHROTTLE_API_KEY", "")
EZTHROTTLE_URL = os.getenv("EZTHROTTLE_URL", "https://ezthrottle.fly.dev")
APP_URL = os.getenv("APP_URL", "https://ezthrottle-sdk-py.fly.dev")

# Initialize EZThrottle client
client = EZThrottle(api_key=API_KEY, ezthrottle_url=EZTHROTTLE_URL)

# In-memory webhook store (thread-safe)
webhook_store: Dict[str, Dict[str, Any]] = {}
webhook_lock = Lock()

print(f"🚀 EZThrottle SDK Test App")
print(f"   EZThrottle: {EZTHROTTLE_URL}")
print(f"   App URL: {APP_URL}")
print(f"   Webhook URL: {APP_URL}/webhook")


# =============================================================================
# WEBHOOK RECEIVER
# =============================================================================

class WebhookData(BaseModel):
    job_id: str
    status: str
    response: Optional[Dict[str, Any]] = None
    idempotent_key: Optional[str] = None


@app.post("/webhook")
def receive_webhook(data: WebhookData):
    """Receive webhooks from EZThrottle backend"""
    job_id = data.job_id
    idempotent_key = data.idempotent_key

    # Store webhook data
    with webhook_lock:
        webhook_store[job_id] = {
            "received_at": datetime.utcnow().isoformat(),
            "data": data.dict()
        }

    print(f"✅ Webhook: {job_id} | key: {idempotent_key} | status: {data.status}")
    return {"status": "received", "job_id": job_id}


@app.get("/webhooks/{job_id}")
def get_webhook(job_id: str):
    """Query webhook result (hurl tests poll this endpoint)"""
    with webhook_lock:
        webhook_data = webhook_store.get(job_id)

    if webhook_data:
        return {
            "found": True,
            "job_id": job_id,
            "webhook": webhook_data
        }
    else:
        raise HTTPException(status_code=404, detail="Webhook not found")


@app.get("/webhooks")
def list_webhooks():
    """List all received webhooks"""
    with webhook_lock:
        webhooks = dict(webhook_store)

    return {
        "count": len(webhooks),
        "webhooks": webhooks
    }


@app.post("/webhooks/reset")
def reset_webhooks():
    """Clear all stored webhooks"""
    with webhook_lock:
        webhook_store.clear()

    print("🧹 Webhook store cleared")
    return {"status": "cleared"}


# =============================================================================
# TEST ENDPOINTS (Return job_id immediately, don't wait for webhooks)
# =============================================================================

@app.post("/test/performance/basic")
def test_performance_basic():
    """
    Test 1: PERFORMANCE - Basic webhook delivery

    Returns immediately with job_id. Hurl test polls /webhooks/{job_id}
    """
    test_key = f"performance_basic_{uuid.uuid4()}"

    result = (
        Step(client)
        .url("https://httpbin.org/status/200?test=performance_basic")
        .method("GET")
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}])
        .idempotent_key(test_key)
        .execute()
    )

    return {
        "test": "performance_basic",
        "idempotent_key": test_key,
        "result": result
    }


@app.post("/test/performance/racing")
def test_performance_racing():
    """
    Test 2: PERFORMANCE - Multi-region racing

    Races across 3 regions. Returns job_id immediately.
    """
    test_key = f"performance_racing_{uuid.uuid4()}"

    result = (
        Step(client)
        .url("https://httpbin.org/delay/1?test=performance_racing")
        .method("GET")
        .type(StepType.PERFORMANCE)
        .regions(["iad", "lax", "ord"])
        .execution_mode("race")
        .region_policy("fallback")
        .webhooks([{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}])
        .idempotent_key(test_key)
        .execute()
    )

    return {
        "test": "performance_racing",
        "idempotent_key": test_key,
        "result": result
    }


@app.post("/test/performance/fallback-chain")
def test_performance_fallback_chain():
    """
    Test 3: PERFORMANCE - Fallback chain (OnError → OnTimeout)

    Primary fails (500) → Fallback1 → Fallback2 succeeds
    """
    test_key = f"fallback_chain_{uuid.uuid4()}"

    result = (
        Step(client)
        .url("https://httpbin.org/status/500?test=fallback_primary")
        .method("GET")
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}])
        .fallback(
            Step()
            .url("https://httpbin.org/delay/2?test=fallback_1")
            .method("GET"),
            trigger_on_error=[500, 502, 503]
        )
        .fallback(
            Step()
            .url("https://httpbin.org/status/200?test=fallback_2")
            .method("GET"),
            trigger_on_timeout=500
        )
        .idempotent_key(test_key)
        .execute()
    )

    return {
        "test": "performance_fallback_chain",
        "idempotent_key": test_key,
        "result": result
    }


@app.post("/test/workflow/on-success")
def test_workflow_on_success():
    """
    Test 4: PERFORMANCE - on_success workflow

    Parent completes → Child job spawned (2 webhooks expected)
    """
    parent_key = f"on_success_parent_{uuid.uuid4()}"
    child_key = f"on_success_child_{uuid.uuid4()}"

    result = (
        Step(client)
        .url("https://httpbin.org/status/200?test=on_success_parent")
        .method("GET")
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}])
        .on_success(
            Step(client)
            .url("https://httpbin.org/delay/1?test=on_success_child")
            .method("GET")
            .type(StepType.PERFORMANCE)
            .webhooks([{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}])
            .idempotent_key(child_key)
        )
        .idempotent_key(parent_key)
        .execute()
    )

    return {
        "test": "workflow_on_success",
        "parent_key": parent_key,
        "child_key": child_key,
        "result": result
    }


@app.post("/test/idempotent/hash")
def test_idempotent_hash():
    """
    Test 5: Idempotent Key - HASH strategy (dedupe)

    Backend generates same hash for identical requests
    """
    # Add timestamp to make each test run unique (avoid stale jobs from previous runs)
    import time
    run_id = int(time.time())

    # No custom key - backend generates hash from (url, method, body)
    result1 = (
        Step(client)
        .url(f"https://httpbin.org/get?test=idempotent_hash&run={run_id}")
        .method("GET")
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}])
        .idempotent_strategy(IdempotentStrategy.HASH)
        .execute()
    )

    result2 = (
        Step(client)
        .url(f"https://httpbin.org/get?test=idempotent_hash&run={run_id}")
        .method("GET")
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}])
        .idempotent_strategy(IdempotentStrategy.HASH)
        .execute()
    )

    return {
        "test": "idempotent_hash",
        "result1": result1,
        "result2": result2,
        "expected": "Same job_id (deduped)",
        "deduped": result1.get("job_id") == result2.get("job_id")
    }


@app.post("/test/idempotent/unique")
def test_idempotent_unique():
    """
    Test 6: Idempotent Key - UNIQUE strategy (allow duplicates)

    Different keys allow duplicate requests
    """
    key1 = f"idempotent_unique_1_{uuid.uuid4()}"
    key2 = f"idempotent_unique_2_{uuid.uuid4()}"

    result1 = (
        Step(client)
        .url("https://httpbin.org/get?test=idempotent_unique")
        .method("GET")
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}])
        .idempotent_key(key1)
        .execute()
    )

    result2 = (
        Step(client)
        .url("https://httpbin.org/get?test=idempotent_unique")
        .method("GET")
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}])
        .idempotent_key(key2)
        .execute()
    )

    return {
        "test": "idempotent_unique",
        "key1": key1,
        "key2": key2,
        "result1": result1,
        "result2": result2,
        "expected": "Different job_ids",
        "different": result1.get("job_id") != result2.get("job_id")
    }


@app.post("/test/decorator/auto-forward")
def test_decorator_auto_forward():
    """
    Test 7: @auto_forward Decorator - Legacy code integration

    Exception auto-forwarded to EZThrottle (killer feature!)
    """
    test_key = f"decorator_forward_{uuid.uuid4()}"

    @auto_forward(client)
    def legacy_payment_processor(order_id: str, idempotent_key: str):
        """Legacy code with auto-forwarding on rate limit"""
        try:
            response = requests.post(
                "https://httpbin.org/status/429",
                headers={"Authorization": "Bearer sk_test_..."},
                json={"amount": 1000, "currency": "usd"},
                timeout=5
            )

            if response.status_code == 429:
                # Decorator catches this and auto-forwards!
                raise ForwardToEZThrottle(
                    url="https://httpbin.org/status/200",
                    method="POST",
                    headers={"Authorization": "Bearer sk_test_..."},
                    body=json.dumps({"amount": 1000, "currency": "usd"}),
                    idempotent_key=idempotent_key,
                    metadata={"order_id": order_id},
                    webhooks=[{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}]
                )

            return response.json()

        except requests.RequestException as e:
            raise ForwardToEZThrottle(
                url="https://httpbin.org/status/200",
                method="POST",
                idempotent_key=idempotent_key,
                metadata={"order_id": order_id, "error": str(e)},
                webhooks=[{"url": f"{APP_URL}/webhook", "has_quorum_vote": True}]
            )

    result = legacy_payment_processor("order_12345", test_key)

    return {
        "test": "decorator_auto_forward",
        "idempotent_key": test_key,
        "result": result,
        "message": "Auto-forwarded!"
    }


# =============================================================================
# HEALTH & INFO
# =============================================================================

@app.get("/")
def index():
    """API information"""
    return {
        "service": "EZThrottle Python SDK Test App",
        "version": "1.1.0",
        "endpoints": {
            "tests": [
                "POST /test/performance/basic",
                "POST /test/performance/racing",
                "POST /test/performance/fallback-chain",
                "POST /test/workflow/on-success",
                "POST /test/idempotent/hash",
                "POST /test/idempotent/unique",
                "POST /test/decorator/auto-forward"
            ],
            "webhooks": [
                "POST /webhook",
                "GET /webhooks/{job_id}",
                "GET /webhooks",
                "POST /webhooks/reset"
            ]
        },
        "config": {
            "ezthrottle_url": EZTHROTTLE_URL,
            "app_url": APP_URL,
            "webhook_url": f"{APP_URL}/webhook",
            "api_key_configured": bool(API_KEY)
        },
        "flow": {
            "1": "POST /test/xxx → Submit job → Return job_id",
            "2": "EZThrottle executes → Sends webhook to /webhook",
            "3": "Hurl polls GET /webhooks/{job_id} until webhook arrives"
        }
    }


@app.get("/health")
def health():
    """Health check"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
