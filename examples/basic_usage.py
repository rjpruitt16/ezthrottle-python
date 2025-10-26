import time
from ezthrottle import EZThrottle, EZThrottleError

client = EZThrottle(api_key="your_key")

try:
    response = client.queue_request(
        url="https://api.example.com/data",
        webhook_url="https://your-webhook.com"
    )
except EZThrottleError as e:
    if e.retry_at:
        # Wait until retry_at before retrying
        wait_ms = e.retry_at - int(time.time() * 1000)
        print(f"Rate limited, retry in {wait_ms}ms")
        
        # Retry with the suggested timestamp
        time.sleep(wait_ms / 1000)
        response = client.queue_request(
            url="https://api.example.com/data",
            webhook_url="https://your-webhook.com",
            retry_at=e.retry_at  # ✅ Tell EZThrottle when to retry
        )
