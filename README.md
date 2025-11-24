# EZThrottle Python SDK

The API Dam for rate-limited services. Queue and execute HTTP requests with smart retry logic, multi-region racing, and webhook delivery.

## Installation

```bash
pip install ezthrottle
```

## Quick Start

```python
from ezthrottle import EZThrottle, Step, StepType

client = EZThrottle(api_key="your_api_key")

# Simple job submission
result = (
    Step(client)
    .url("https://api.example.com/endpoint")
    .method("POST")
    .type(StepType.PERFORMANCE)
    .webhooks([{"url": "https://your-app.com/webhook"}])
    .execute()
)

print(f"Job ID: {result['job_id']}")
```

## Step Types

### StepType.PERFORMANCE (Server-side execution)
Submit jobs to EZThrottle for distributed execution with multi-region racing and webhook delivery.

```python
Step(client)
    .url("https://api.stripe.com/charges")
    .type(StepType.PERFORMANCE)
    .webhooks([{"url": "https://app.com/webhook"}])
    .regions(["iad", "lax", "ord"])  # Multi-region racing
    .execution_mode("race")  # First completion wins
    .execute()
```

### StepType.FRUGAL (Client-side first)
Execute locally first, only forward to EZThrottle on specific error codes. Saves money!

```python
Step(client)
    .url("https://api.example.com")
    .type(StepType.FRUGAL)
    .fallback_on_error([429, 500, 503])  # Forward to EZThrottle on these codes
    .execute()
```

## Idempotent Key Strategies

**Critical concept:** Idempotent keys prevent duplicate job execution. Choose the right strategy for your use case.

### IdempotentStrategy.HASH (Default)

Backend generates deterministic hash of (url, method, body, customer_id). **Prevents duplicates.**

**Use when:**
- Payment processing (don't charge twice!)
- Critical operations (create user, send notification)
- You want automatic deduplication

**Example:**
```python
from ezthrottle import IdempotentStrategy

# Prevents duplicate charges - same request = rejected as duplicate
Step(client)
    .url("https://api.stripe.com/charges")
    .body('{"amount": 1000, "currency": "usd"}')
    .idempotent_strategy(IdempotentStrategy.HASH)  # Default
    .execute()

# Second call with same params � "duplicate" (not charged twice!)
```

### IdempotentStrategy.UNIQUE

SDK generates unique UUID per request. **Allows duplicates.**

**Use when:**
- Polling endpoints (same URL, different data each time)
- Webhooks (want to send every time)
- Scheduled jobs (run every minute/hour)
- GET requests that return changing data

**Example:**
```python
# Poll API every minute - each request gets unique UUID
while True:
    Step(client)
        .url("https://api.example.com/status")
        .idempotent_strategy(IdempotentStrategy.UNIQUE)  # New UUID each time
        .execute()

    time.sleep(60)
```

**Without UNIQUE strategy, polling would fail:**
```python
# L BAD - Second request rejected as duplicate!
Step(client).url("https://api.com/status").execute()  # Works
Step(client).url("https://api.com/status").execute()  # Rejected! Same hash
```

### Custom Keys

Provide your own business logic keys.

**Use when:**
- You have existing ID system (order ID, transaction ID)
- Want custom deduplication logic

**Example:**
```python
# Custom key based on order ID
Step(client)
    .url("https://api.example.com/process")
    .idempotent_key(f"order-{order_id}")  # Dedup per order
    .execute()
```

## Workflow Chaining

Chain steps together with `.on_success()`, `.on_failure()`, and `.fallback()`:

```python
# Analytics step (cheap)
analytics = Step(client).url("https://analytics.com/track").type(StepType.FRUGAL)

# Notification (fast, distributed)
notification = (
    Step(client)
    .url("https://notify.com")
    .type(StepType.PERFORMANCE)
    .webhooks([{"url": "https://app.com/webhook"}])
    .regions(["iad", "lax"])
    .on_success(analytics)
)

# Primary API call (cheap local execution)
result = (
    Step(client)
    .url("https://api.example.com")
    .type(StepType.FRUGAL)
    .fallback_on_error([429, 500])
    .on_success(notification)
    .execute()
)
```

## Fallback Chains

Handle failures with automatic fallback execution:

```python
backup_api = Step(client).url("https://backup-api.com")

result = (
    Step(client)
    .url("https://primary-api.com")
    .fallback(backup_api, trigger_on_error=[500, 502, 503])
    .execute()
)
```

## Multi-Region Racing

Submit jobs to multiple regions, fastest wins:

```python
Step(client)
    .url("https://api.example.com")
    .regions(["iad", "lax", "ord"])  # Try all 3 regions
    .region_policy("fallback")  # Auto-route if region down
    .execution_mode("race")  # First completion wins
    .webhooks([{"url": "https://app.com/webhook"}])
    .execute()
```

## Webhook Fanout (Multiple Webhooks)

Deliver job results to multiple services simultaneously:

```python
Step(client)
    .url("https://api.stripe.com/charges")
    .method("POST")
    .webhooks([
        # Primary webhook (must succeed)
        {"url": "https://app.com/payment-complete", "has_quorum_vote": True},

        # Analytics webhook (optional)
        {"url": "https://analytics.com/track", "has_quorum_vote": False},

        # Notification service (must succeed)
        {"url": "https://notify.com/alert", "has_quorum_vote": True},

        # Multi-region webhook racing
        {"url": "https://backup.com/webhook", "regions": ["iad", "lax"], "has_quorum_vote": True}
    ])
    .webhook_quorum(2)  # At least 2 webhooks with has_quorum_vote=true must succeed
    .execute()
```

**Webhook Options:**
- `url` - Webhook endpoint URL
- `regions` - (Optional) Deliver webhook from specific regions
- `has_quorum_vote` - (Optional) Counts toward quorum (default: true)

**Use Cases:**
- Notify multiple services (payment processor + analytics + CRM)
- Redundancy (multiple backup webhooks)
- Multi-region delivery (low latency globally)

## Retry Policies

Customize retry behavior:

```python
Step(client)
    .url("https://api.example.com")
    .retry_policy({
        "max_retries": 5,
        "max_reroutes": 3,
        "retry_codes": [429, 503],  # Retry in same region
        "reroute_codes": [500, 502, 504]  # Try different region
    })
    .execute()
```

## @auto_forward Decorator (Legacy Code Integration)

**The killer feature:** Integrate EZThrottle into existing code without rewriting error handling!

```python
from ezthrottle import auto_forward, ForwardToEZThrottle

@auto_forward(client)
def process_payment(order_id):
    """
    Legacy payment processing code.
    Just raise ForwardToEZThrottle on errors - decorator handles the rest!
    """
    try:
        response = requests.post(
            "https://api.stripe.com/charges",
            headers={"Authorization": "Bearer sk_live_..."},
            json={"amount": 1000, "currency": "usd"}
        )

        if response.status_code == 429:
            # Decorator catches this and auto-forwards to EZThrottle!
            raise ForwardToEZThrottle(
                url="https://api.stripe.com/charges",
                method="POST",
                headers={"Authorization": "Bearer sk_live_..."},
                body='{"amount": 1000, "currency": "usd"}',
                idempotent_key=f"order_{order_id}",
                metadata={"order_id": order_id, "customer_id": "cust_123"},
                webhooks=[{"url": "https://app.com/payment-complete"}]
            )

        return response.json()

    except requests.RequestException as e:
        # Network errors also auto-forwarded
        raise ForwardToEZThrottle(
            url="https://api.stripe.com/charges",
            method="POST",
            idempotent_key=f"order_{order_id}",
            metadata={"error": str(e)}
        )

# Call your legacy function - works exactly the same!
result = process_payment("order_12345")
# Returns: {"job_id": "...", "status": "queued"}
```

**Why this is amazing:**
- ✅ No code refactoring required
- ✅ Drop-in replacement for existing error handling
- ✅ Keep your existing function signatures
- ✅ Gradual migration path
- ✅ Works with any HTTP library (requests, httpx, urllib)

## Production Ready ✅

This SDK is production-ready with comprehensive integration tests running on every push.

### Integration Test Suite

The `test-app/` directory contains a **full integration test suite** deployed to Fly.io that validates:
- Multi-region racing with fallback
- Webhook delivery and polling
- Idempotent key strategies (HASH vs UNIQUE)
- Fallback chains (OnError, OnTimeout)
- On-success/on-failure workflows
- Auto-forward decorator

**Run tests locally:**
```bash
cd test-app
make integration
```

**Test flow:**
1. Deploys FastAPI test app to Fly.io
2. Runs 7 Hurl integration tests
3. Validates webhook delivery
4. Tears down deployment

**CI/CD:**
- ✅ GitHub Actions runs full integration suite on every push
- ✅ Tests against live EZThrottle backend
- ✅ 100% test coverage of SDK features

### Test App as Reference Implementation

See `test-app/app.py` for **production-ready examples** of:
- Performance vs Frugal workflows
- Multi-region racing
- Idempotent key strategies
- Webhook handling
- Auto-forward decorator

**This is the same code we use to validate production deployments!**

## Legacy API (Deprecated)

For backward compatibility, the old `queue_request()` method is still available:

```python
client.queue_request(
    url="https://api.example.com",
    webhook_url="https://your-app.com/webhook",  # Note: singular
    method="POST"
)
```

**Prefer the new `Step` builder API for all new code!**

## Environment Variables

```bash
EZTHROTTLE_API_KEY=your_api_key_here
```

## License

MIT
