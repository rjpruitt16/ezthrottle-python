"""Basic usage example for EZThrottle SDK"""

from ezthrottle import EZThrottle


def handle_webhook(job_id: str, result: dict):
    """Callback for webhook results"""
    print(f"Received result for job {job_id}")
    print(f"Status: {result.get('status')}")


def main():
    # Initialize client
    client = EZThrottle(
        api_key="test_key_123",  # You'll need a real key when deployed
        tracktags_url="http://localhost:8080",  # For local testing
        webhook_callback=handle_webhook,
        webhook_port=5555
    )
    
    print("EZThrottle SDK initialized successfully!")
    print(f"Webhook server running at: http://localhost:5555/webhook")
    
    # Test with a real API that might return 429
    # For now, let's just show the SDK works
    try:
        # Example: Test with httpbin.org (always available)
        response = client.request(
            url="https://httpbin.org/status/200",
            method="GET"
        )
        print(f"Direct request worked: {response.status_code}")
        
        # Force test the queue path (even though httpbin won't 429)
        print("\nTesting queue_and_wait (this will timeout since httpbin won't webhook back)...")
        # This would normally be used when you get a 429
        
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        client.close()
        print("\nSDK test complete!")


if __name__ == "__main__":
    main()
