# Test 3: PERFORMANCE - Fallback chain (OnError → OnTimeout)
# Flow: Primary fails 500 → Fallback1 (OnError) → Fallback2 (OnTimeout) → Success

POST {{APP_URL}}/test/performance/fallback-chain
HTTP 200

[Captures]
job_id: jsonpath "$.result.job_id"
idempotent_key: jsonpath "$.idempotent_key"

[Asserts]
jsonpath "$.test" == "performance_fallback_chain"
jsonpath "$.result.status" == "queued"
jsonpath "$.idempotent_key" startsWith "fallback_chain_"

# Poll for webhook (fallback chain takes longer: 500 error + 2s delay + 500ms timeout)
# Total: ~3-4 seconds, allow 45s for safety
GET {{APP_URL}}/webhooks/{{job_id}}
[Options]
retry: 45
retry-interval: 1000
HTTP 200

[Asserts]
jsonpath "$.found" == true
jsonpath "$.webhook.data.job_id" == "{{job_id}}"
jsonpath "$.webhook.data.status" == "success"
jsonpath "$.webhook.data.idempotent_key" == "{{idempotent_key}}"
# Final fallback succeeded (200 status)
