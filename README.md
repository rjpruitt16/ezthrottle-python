# EZThrottle Python SDK

The API Dam for rate-limited services. Queue and execute HTTP requests with smart retry logic, multi-region racing, and webhook delivery.

## Get Your API Key

👉 **[Get started at ezthrottle.network](https://www.ezthrottle.network/)**

**Pay for delivery through outages and rate limiting. Unlimited free concurrency.**

No need to manage Lambda functions, SQS queues, DynamoDB, or complex retry logic. EZThrottle handles webhook fanout, distributed queuing, and multi-region orchestration for you. Just grab an API key and start shipping reliable API calls.

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

## Rate Limiting & Tuning

EZThrottle intelligently manages rate limits for your API calls. By default, requests are throttled at **2 RPS (requests per second)** to smooth rate limiting across distributed workers and prevent API overload.

### Dynamic Rate Limiting via Response Headers

Your API can communicate rate limits back to EZThrottle using response headers:

```python
# Your API responds with these headers:
X-EZTHROTTLE-RPS: 5  # Allow 5 requests per second
X-EZTHROTTLE-MAX-CONCURRENT: 10  # Allow 10 concurrent requests
```

**Header Details:**
- `X-EZTHROTTLE-RPS`: Requests per second (e.g., `0.5` = 1 request per 2 seconds, `5` = 5 requests per second)
- `X-EZTHROTTLE-MAX-CONCURRENT`: Maximum concurrent requests (default: 2 per machine)

EZThrottle automatically adjusts its rate limiting based on these headers, ensuring optimal throughput without overwhelming your APIs.

**Performance Note:** Server-side retry handling is significantly faster and more performant than client-side retry loops. EZThrottle's distributed architecture eliminates connection overhead and retry latency. *Benchmarks coming soon.*

### Requesting Custom Defaults

Need different default rate limits for your account? Submit a configuration request:

👉 **[Request custom defaults at github.com/rjpruitt16/ezconfig](https://github.com/rjpruitt16/ezconfig)**

## Webhook Payload

When EZThrottle completes your job, it sends a POST request to your webhook URL with the following JSON payload:

```json
{
  "job_id": "job_1763674210055_853341",
  "idempotent_key": "custom_key_or_generated_hash",
  "status": "success",
  "response": {
    "status_code": 200,
    "headers": {
      "content-type": "application/json"
    },
    "body": "{\"result\": \"data\"}"
  },
  "metadata": {}
}
```

**Fields:**
- `job_id` - Unique identifier for this job
- `idempotent_key` - Your custom key or auto-generated hash
- `status` - `"success"` or `"failed"`
- `response.status_code` - HTTP status code from the target API
- `response.headers` - Response headers from the target API
- `response.body` - Response body from the target API (as string)
- `metadata` - Custom metadata you provided during job submission

**Example webhook handler (Flask):**
```python
from flask import Flask, request

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    payload = request.json

    job_id = payload['job_id']
    status = payload['status']

    if status == 'success':
        response_body = payload['response']['body']
        # Process successful result
        print(f"Job {job_id} succeeded: {response_body}")
    else:
        # Handle failure
        print(f"Job {job_id} failed")

    return {'ok': True}
```

## Mixed Workflow Chains (FRUGAL ↔ PERFORMANCE)

Mix FRUGAL and PERFORMANCE steps in the same workflow to optimize for both cost and speed:

### Example 1: FRUGAL → PERFORMANCE (Save money, then fast delivery)

```python
# Primary API call is cheap (local execution)
# But notification needs speed (multi-region racing)
result = (
    Step(client)
    .url("https://api.openai.com/v1/chat/completions")
    .type(StepType.FRUGAL)  # Execute locally first
    .fallback_on_error([429, 500])
    .on_success(
        # Chain to PERFORMANCE for fast webhook delivery
        Step(client)
        .url("https://api.sendgrid.com/send")
        .type(StepType.PERFORMANCE)  # Distributed execution
        .webhooks([{"url": "https://app.com/email-sent"}])
        .regions(["iad", "lax", "ord"])
    )
    .execute()
)
```

### Example 2: PERFORMANCE → FRUGAL (Fast payment, then cheap analytics)

```python
# Critical payment needs speed (racing)
# But analytics is cheap (local execution when webhook arrives)
payment = (
    Step(client)
    .url("https://api.stripe.com/charges")
    .type(StepType.PERFORMANCE)  # Fast distributed execution
    .webhooks([{"url": "https://app.com/payment-complete"}])
    .regions(["iad", "lax"])
    .on_success(
        # Analytics doesn't need speed - save money!
        Step(client)
        .url("https://analytics.com/track")
        .type(StepType.FRUGAL)  # Client executes when webhook arrives
    )
    .execute()
)
```

### Example 3: Complex Mixed Workflow

```python
# Optimize every step for its requirements
workflow = (
    Step(client)
    .url("https://cheap-api.com")
    .type(StepType.FRUGAL)  # Try locally first
    .fallback_on_error([429, 500])
    .fallback(
        Step().url("https://backup-api.com"),  # Still FRUGAL
        trigger_on_error=[500]
    )
    .on_success(
        # Critical notification needs PERFORMANCE
        Step(client)
        .url("https://critical-webhook.com")
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": "https://app.com/webhook"}])
        .regions(["iad", "lax", "ord"])
        .on_success(
            # Analytics is cheap again
            Step(client)
            .url("https://analytics.com/track")
            .type(StepType.FRUGAL)
        )
    )
    .on_failure(
        # Simple Slack alert doesn't need PERFORMANCE
        Step(client)
        .url("https://hooks.slack.com/webhook")
        .type(StepType.FRUGAL)
    )
    .execute()
)
```

**Why mix workflows?**
- ✅ **Cost optimization** - Only pay for what needs speed
- ✅ **Performance where it matters** - Critical paths get multi-region racing
- ✅ **Flexibility** - Every step optimized for its specific requirements

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

This SDK is production-ready with **working examples validated in CI on every push**.

### Reference Implementation: test-app/

The `test-app/` directory contains **real, working code** you can learn from. Not toy examples - this is production code we run in automated tests against live EZThrottle backend.

**Multi-Region Racing** ([test-app/app.py:134-145](test-app/app.py#L134-L145))
```python
Step(client)
    .url("https://httpbin.org/delay/1")
    .type(StepType.PERFORMANCE)
    .webhooks([{"url": f"{APP_URL}/webhook"}])
    .regions(["iad", "lax", "ord"])  # Race across 3 regions
    .execution_mode("race")  # First completion wins
    .execute()
```

**Idempotent HASH (Deduplication)** ([test-app/app.py:274-281](test-app/app.py#L274-L281))
```python
# Same request twice = same job_id (deduplicated)
Step(client)
    .url(f"https://httpbin.org/get?run={run_id}")
    .idempotent_strategy(IdempotentStrategy.HASH)
    .execute()
```

**Fallback Chain** ([test-app/app.py:168-182](test-app/app.py#L168-L182))
```python
Step(client)
    .url("https://httpbin.org/status/500")
    .fallback(
        Step().url("https://httpbin.org/status/200"),
        trigger_on_error=[500, 502, 503]
    )
    .execute()
```

**On-Success Workflow** ([test-app/app.py:198-213](test-app/app.py#L198-L213))
```python
Step(client)
    .url("https://httpbin.org/status/200")
    .on_success(
        Step().url("https://httpbin.org/delay/1")
    )
    .execute()
```

**Auto-Forward Decorator** ([test-app/app.py:246-256](test-app/app.py#L246-L256))
```python
@auto_forward(client, fallback_on_error=[429, 500])
def legacy_api_call():
    response = requests.get("https://httpbin.org/status/429")
    response.raise_for_status()  # Raises on 429
    return response.json()
# Automatically forwards to EZThrottle on error!
```

**Validated in CI:**
- ✅ GitHub Actions runs these examples against live backend on every push
- ✅ 7 integration tests covering all SDK features
- ✅ Proves the code actually works, not just documentation

## Asyncio Streaming (Non-Blocking Webhook Waiting)

Wait for webhook results asynchronously using Python's asyncio. Perfect for workflows that need to continue processing while waiting for EZThrottle to complete jobs.

### Basic Asyncio Example

```python
import asyncio
from ezthrottle import EZThrottle, Step, StepType

client = EZThrottle(api_key="your_api_key")

async def process_with_webhook():
    # Submit job to EZThrottle
    result = (
        Step(client)
        .url("https://api.example.com/endpoint")
        .method("POST")
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": "https://app.com/webhook", "has_quorum_vote": True}])
        .idempotent_key("async_job_123")
        .execute()
    )

    print(f"Job submitted: {result['job_id']}")

    # Continue processing while EZThrottle executes the job
    # Your webhook endpoint will receive the result asynchronously

# Run async function
asyncio.run(process_with_webhook())
```

### Concurrent Job Submission with asyncio.gather

Submit multiple jobs concurrently and process results as they arrive:

```python
import asyncio
from ezthrottle import EZThrottle, Step, StepType

client = EZThrottle(api_key="your_api_key")

async def submit_job(order):
    """Submit a single job asynchronously"""
    result = (
        Step(client)
        .url("https://api.example.com/process")
        .method("POST")
        .body(str(order))
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": "https://app.com/webhook", "has_quorum_vote": True}])
        .idempotent_key(f"order_{order['id']}")
        .execute()
    )

    return {
        "order_id": order["id"],
        "job_id": result["job_id"],
        "idempotent_key": result.get("idempotent_key")
    }

async def process_batch_concurrently(orders):
    # Submit all jobs concurrently
    tasks = [submit_job(order) for order in orders]
    submissions = await asyncio.gather(*tasks)

    print(f"Submitted {len(submissions)} jobs concurrently")
    for s in submissions:
        print(f"Order {s['order_id']} → Job {s['job_id']}")

    # Webhook results will arrive asynchronously at https://app.com/webhook
    return submissions

# Example usage
orders = [
    {"id": "order_1", "amount": 1000},
    {"id": "order_2", "amount": 2000},
    {"id": "order_3", "amount": 3000}
]

asyncio.run(process_batch_concurrently(orders))
```

### Fault-Tolerant Batch Processing

Handle failures gracefully with asyncio exception handling:

```python
import asyncio
from ezthrottle import EZThrottle, Step, StepType

client = EZThrottle(api_key="your_api_key")

async def submit_job_with_error_handling(order):
    """Submit job with exception handling"""
    try:
        result = (
            Step(client)
            .url("https://api.example.com/process")
            .method("POST")
            .body(str(order))
            .type(StepType.PERFORMANCE)
            .webhooks([{"url": "https://app.com/webhook"}])
            .idempotent_key(f"order_{order['id']}")
            .execute()
        )
        return {"order_id": order["id"], "job_id": result["job_id"], "success": True}
    except Exception as e:
        return {"order_id": order["id"], "error": str(e), "success": False}

async def process_batch_with_error_handling(orders):
    tasks = [submit_job_with_error_handling(order) for order in orders]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    succeeded = [r for r in results if isinstance(r, dict) and r.get("success")]
    failed = [r for r in results if isinstance(r, dict) and not r.get("success")] + \
             [r for r in results if isinstance(r, Exception)]

    print(f"Succeeded: {len(succeeded)}, Failed: {len(failed)}")

    return {"succeeded": succeeded, "failed": failed}

# Example usage
orders = [
    {"id": "order_1", "amount": 1000},
    {"id": "order_2", "amount": 2000},
    {"id": "order_3", "amount": 3000}
]

asyncio.run(process_batch_with_error_handling(orders))
```

### Integration with FastAPI Webhook Handler

```python
from fastapi import FastAPI, Request
from ezthrottle import EZThrottle, Step, StepType
import asyncio

app = FastAPI()
client = EZThrottle(api_key="your_api_key")

# In-memory store for webhook results (use Redis/DB in production)
webhook_results = {}

@app.post("/webhook")
async def webhook_receiver(request: Request):
    """Receive webhooks from EZThrottle"""
    data = await request.json()

    job_id = data.get("job_id")
    idempotent_key = data.get("idempotent_key")
    status = data.get("status")
    response = data.get("response")

    # Store result
    webhook_results[idempotent_key] = {
        "job_id": job_id,
        "status": status,
        "response": response,
        "received_at": datetime.now()
    }

    print(f"Webhook received for {idempotent_key}: {status}")

    return {"ok": True}

@app.post("/submit")
async def submit_job():
    """Submit job and return immediately"""
    idempotent_key = f"job_{int(time.time() * 1000)}"

    result = (
        Step(client)
        .url("https://api.example.com/endpoint")
        .method("POST")
        .type(StepType.PERFORMANCE)
        .webhooks([{"url": "https://app.com/webhook", "has_quorum_vote": True}])
        .idempotent_key(idempotent_key)
        .execute()
    )

    # Return immediately, don't wait for webhook
    return {
        "job_id": result["job_id"],
        "idempotent_key": idempotent_key,
        "message": "Job submitted, webhook will arrive asynchronously"
    }

@app.get("/result/{idempotent_key}")
async def get_result(idempotent_key: str):
    """Poll for webhook result"""
    result = webhook_results.get(idempotent_key)

    if result:
        return {"found": True, "result": result}
    else:
        return {"found": False, "message": "Webhook not yet received"}
```

### Background Task Processing with asyncio

Process multiple jobs in the background while serving requests:

```python
import asyncio
from ezthrottle import EZThrottle, Step, StepType

client = EZThrottle(api_key="your_api_key")

async def background_job_processor(queue):
    """Process jobs from a queue in the background"""
    while True:
        if queue.empty():
            await asyncio.sleep(1)
            continue

        order = await queue.get()

        try:
            result = (
                Step(client)
                .url("https://api.example.com/process")
                .method("POST")
                .body(str(order))
                .type(StepType.PERFORMANCE)
                .webhooks([{"url": "https://app.com/webhook"}])
                .idempotent_key(f"order_{order['id']}")
                .execute()
            )
            print(f"Submitted job {result['job_id']} for order {order['id']}")
        except Exception as e:
            print(f"Failed to submit order {order['id']}: {e}")
        finally:
            queue.task_done()

async def main():
    queue = asyncio.Queue()

    # Start background processor
    processor = asyncio.create_task(background_job_processor(queue))

    # Add jobs to queue
    orders = [
        {"id": "order_1", "amount": 1000},
        {"id": "order_2", "amount": 2000},
        {"id": "order_3", "amount": 3000}
    ]

    for order in orders:
        await queue.put(order)

    # Wait for all jobs to be processed
    await queue.join()

    # Cancel background processor
    processor.cancel()
    try:
        await processor
    except asyncio.CancelledError:
        pass

    print("All jobs processed!")

asyncio.run(main())
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
