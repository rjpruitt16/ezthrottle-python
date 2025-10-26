"""EZThrottle Integration Test"""

import os
import time
import json
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

from ezthrottle import EZThrottle
from ezthrottle.exceptions import EZThrottleError

load_dotenv()

API_KEY = os.getenv("EZTHROTTLE_API_KEY", "")
CUSTOMER_ID = os.getenv("CUSTOMER_ID", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "")
TEST_TIMEOUT = int(os.getenv("TEST_TIMEOUT", "60"))


@dataclass
class TestResult:
    test_name: str
    passed: bool
    duration_ms: int
    details: str
    job_id: Optional[str] = None


class WebhookSiteClient:
    """Client for webhook.site API"""
    
    def __init__(self, token: str, webhook_url: str):
        self.token = token
        self.webhook_url = webhook_url
        print(f"🪝 Webhook URL: {self.webhook_url}")
    
    def clear_all_requests(self):
        """Clear all webhook requests"""
        # Fixed: use /request instead of /requests
        url = f"https://webhook.site/token/{self.token}/request"
        try:
            response = requests.delete(url)
            if response.status_code == 200:
                result = response.json()
                if result.get("status"):
                    print(f"  ✅ Cleared all webhooks")
                else:
                    print(f"  ⚠️  Failed to clear webhooks")
            else:
                print(f"  ⚠️  Failed to clear webhooks: HTTP {response.status_code}")
        except Exception as e:
            print(f"  ⚠️  Error clearing webhooks: {e}")  

    def wait_for_job(self, job_id: str, timeout: int = 30) -> Optional[Dict]:
        """Wait for specific job webhook"""
        print(f"  ⏳ Polling webhook.site for job: {job_id}")
        url = f"https://webhook.site/token/{self.token}/requests"
        
        start = time.time()
        attempts = 0
        while time.time() - start < timeout:
            attempts += 1
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    data = response.json()
                    
                    if attempts % 5 == 1:  # Log every 5th attempt
                        print(f"     Attempt {attempts}: checking {len(data.get('data', []))} webhooks...")
                    
                    for req in data.get("data", []):
                        content_str = req.get("content", "{}")
                        
                        try:
                            content = json.loads(content_str)
                            if content.get("job_id") == job_id:
                                print(f"  ✅ Found webhook for job: {job_id}")
                                return content
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                if attempts == 1:
                    print(f"  ⚠️  Error: {e}")
            
            time.sleep(2)
        
        print(f"  ❌ No webhook found for job: {job_id} after {attempts} attempts")
        return None


class SDKIntegrationTest:
    def __init__(self):
        self.webhook_client = WebhookSiteClient(WEBHOOK_TOKEN, WEBHOOK_URL)
        self.results: List[TestResult] = []
        
        print("🔧 Initializing EZThrottle SDK...")
        self.client = EZThrottle(api_key=API_KEY)
        print("✅ SDK initialized")
    
    def test_sdk_queue_request(self) -> TestResult:
        """Test 1: SDK queue_request method"""
        print("\n" + "="*70)
        print("TEST 1: SDK queue_request() - Direct Job Submission")
        print("="*70)
        
        start = time.time()
        
        try:
            print("  📤 Calling client.queue_request()...")
            result = self.client.queue_request(
                url="https://httpbin.org/status/200",
                webhook_url=WEBHOOK_URL,
                method="GET",
            )
            
            job_id = result.get("job_id")
            if not job_id:
                raise EZThrottleError("No job_id in response")
            
            print(f"     ✅ Job queued: {job_id}")
            
            webhook_data = self.webhook_client.wait_for_job(job_id, timeout=30)
            
            if not webhook_data:
                return TestResult(
                    "SDK queue_request",
                    False,
                    int((time.time() - start) * 1000),
                    "Webhook not received",
                    job_id=job_id
                )
            
            passed = webhook_data.get("status") == 200
            duration = int((time.time() - start) * 1000)
            
            return TestResult(
                "SDK queue_request",
                passed,
                duration,
                f"Status: {webhook_data.get('status')}",
                job_id=job_id
            )
            
        except Exception as e:
            return TestResult(
                "SDK queue_request",
                False,
                int((time.time() - start) * 1000),
                f"Exception: {str(e)}"
            )
    
    def test_sdk_smart_request_no_429(self) -> TestResult:
        """Test 2: SDK request() method"""
        print("\n" + "="*70)
        print("TEST 2: SDK request() - Smart Request (No 429)")
        print("="*70)
        
        start = time.time()
        
        try:
            print("  📤 Calling client.request()...")
            response = self.client.request(
                url="https://httpbin.org/get",
                method="GET"
            )
            
            print(f"     ✅ Response status: {response.status_code}")
            
            passed = response.status_code == 200
            duration = int((time.time() - start) * 1000)
            
            return TestResult(
                "SDK request (no 429)",
                passed,
                duration,
                f"Direct request succeeded in {duration}ms"
            )
            
        except Exception as e:
            return TestResult(
                "SDK request (no 429)",
                False,
                int((time.time() - start) * 1000),
                f"Exception: {str(e)}"
            )
    
    def test_sdk_queue_and_wait_429(self) -> TestResult:
        """Test 3: Queue 429 job"""
        print("\n" + "="*70)
        print("TEST 3: SDK queue_and_wait() - Rate Limited Job (429)")
        print("="*70)
        
        start = time.time()
        
        try:
            print("  📤 Calling client.queue_request()...")
            result = self.client.queue_request(
                url="https://httpbin.org/status/429",
                webhook_url=WEBHOOK_URL,
                method="GET",
            )
            
            job_id = result.get("job_id")
            if not job_id:
                raise EZThrottleError("No job_id in response")
            
            print(f"     ✅ Job queued: {job_id}")
            
            webhook_data = self.webhook_client.wait_for_job(job_id, timeout=TEST_TIMEOUT)
            
            duration = int((time.time() - start) * 1000)
            
            if not webhook_data:
                return TestResult(
                    "SDK 429 handling",
                    False,
                    duration,
                    "Webhook not received after retry window",
                    job_id=job_id
                )
            
            passed = webhook_data.get("job_id") == job_id
            
            return TestResult(
                "SDK 429 handling",
                passed,
                duration,
                f"Completed in {duration}ms",
                job_id=job_id
            )
            
        except Exception as e:
            return TestResult(
                "SDK 429 handling",
                False,
                int((time.time() - start) * 1000),
                f"Exception: {str(e)}"
            )
    
    def test_sdk_burst_requests(self) -> TestResult:
        """Test 4: Burst requests"""
        print("\n" + "="*70)
        print("TEST 4: SDK Burst Requests - Load Distribution")
        print("="*70)
        
        start = time.time()
        job_ids = []
        
        try:
            print("  📤 Submitting burst of 5 jobs...")
            for i in range(5):
                result = self.client.queue_request(
                    url=f"https://httpbin.org/delay/1?id={i}",
                    webhook_url=WEBHOOK_URL,
                    method="GET",
                )
                job_id = result.get("job_id")
                if job_id:
                    print(f"     ✅ Job {i+1}/5 queued: {job_id}")
                    job_ids.append(job_id)
                time.sleep(0.5)
            
            print("  ⏳ Waiting for completions...")
            completed = 0
            for job_id in job_ids:
                webhook_data = self.webhook_client.wait_for_job(job_id, timeout=15)
                if webhook_data:
                    completed += 1
            
            duration = int((time.time() - start) * 1000)
            passed = completed >= 3
            
            return TestResult(
                "SDK Burst Requests",
                passed,
                duration,
                f"{completed}/{len(job_ids)} jobs completed"
            )
            
        except Exception as e:
            return TestResult(
                "SDK Burst Requests",
                False,
                int((time.time() - start) * 1000),
                f"Exception: {str(e)}"
            )
    
    def run_all_tests(self):
        """Run all tests"""
        print("="*70)
        print("🧪 EZThrottle SDK Integration Test Suite")
        print("="*70)
        print(f"API Key: {API_KEY[:20]}...")
        print(f"Customer: {CUSTOMER_ID}")
        print(f"Webhook: {WEBHOOK_URL}")
        print("="*70)
        
        # Clear webhooks before starting
        print("\n🧹 Clearing old webhooks...")
        self.webhook_client.clear_all_requests()
        time.sleep(2)  # Give webhook.site time to clear
        print()
        
        self.results.append(self.test_sdk_queue_request())
        time.sleep(2)
        
        self.results.append(self.test_sdk_smart_request_no_429())
        time.sleep(2)
        
        self.results.append(self.test_sdk_queue_and_wait_429())
        time.sleep(2)
        
        self.results.append(self.test_sdk_burst_requests())
        
        self.print_summary()
    
    def print_summary(self):
        """Print results"""
        print("\n" + "="*70)
        print("📊 TEST RESULTS SUMMARY")
        print("="*70)
        
        for result in self.results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"\n{status} {result.test_name}")
            print(f"   Duration: {result.duration_ms}ms")
            print(f"   Details: {result.details}")
            if result.job_id:
                print(f"   Job ID: {result.job_id}")
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        
        print("\n" + "="*70)
        print(f"OVERALL: {passed}/{total} tests passed ({int(passed/total*100) if total > 0 else 0}%)")
        print("="*70)
        
        if passed < total:
            print(f"⚠️  {total - passed} test(s) failed")
        else:
            print("🎉 All tests passed!")
        
        print("\n📊 Verification:")
        print(f"   1. Webhooks: {WEBHOOK_URL}")
        print(f"   2. Dashboard: https://tracktags.fly.dev/")
        print(f"   3. Logs: fly logs -a ezthrottle")


def main():
    test = SDKIntegrationTest()
    test.run_all_tests()


if __name__ == "__main__":
    main()
