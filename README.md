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

# Second call with same params ’ "duplicate" (not charged twice!)
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
    .webhooks([
        {"url": "https://app.com/webhook1", "regions": ["iad"]},
        {"url": "https://app.com/webhook2", "regions": ["lax"]}
    ])
    .webhook_quorum(2)  # Both webhooks must succeed
    .execute()
```

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
