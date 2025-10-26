# test_integration.py
import requests
import time
import sys

def test_ezthrottle(webhook_url):
    print(f"Testing with webhook URL: {webhook_url}")
    
    # Submit a few test jobs
    for i in range(3):
        payload = {
            "url": f"https://httpbin.org/get?test={i}",
            "webhook_url": webhook_url,
            "customer_id": "test",
            "method": "GET",
            "headers": {"X-Test": str(i)},
            "body": None
        }
        
        # Try local first, then staging
        for base_url in ["http://localhost:8080", "https://ezthrottle-staging.fly.dev"]:
            try:
                resp = requests.post(f"{base_url}/api/v1/jobs", json=payload, timeout=5)
                if resp.status_code == 200:
                    print(f"✓ Job {i} submitted to {base_url}: {resp.json().get('job_id', 'unknown')}")
                    break
            except:
                continue
    
    print("\nWaiting 10 seconds for webhooks...")
    time.sleep(10)
    print("Check your terminal for webhook receipts!")

if __name__ == "__main__":
    webhook_url = sys.argv[1] if len(sys.argv) > 1 else "https://webhook.site/test"
    test_ezthrottle(webhook_url)
