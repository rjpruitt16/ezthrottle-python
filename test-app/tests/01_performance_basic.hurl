# Test 1: PERFORMANCE - Basic webhook delivery
# Flow: Submit job → Return job_id → Poll for webhook → Verify success

POST {{TEST_APP_URL}}/test/performance/basic
HTTP 200

[Captures]
job_id: jsonpath "$.result.job_id"
idempotent_key: jsonpath "$.idempotent_key"

[Asserts]
jsonpath "$.test" == "performance_basic"
jsonpath "$.result.status" == "queued"
jsonpath "$.result.job_id" exists
jsonpath "$.idempotent_key" startsWith "performance_basic_"

# Poll for webhook (retry up to 30 times with 1s interval = 30s max)
GET {{TEST_APP_URL}}/webhooks/{{job_id}}
[Options]
retry: 30
retry-interval: 1000
HTTP 200

[Asserts]
jsonpath "$.found" == true
jsonpath "$.webhook.data.job_id" == "{{job_id}}"
jsonpath "$.webhook.data.status" == "success"
jsonpath "$.webhook.data.idempotent_key" == "{{idempotent_key}}"
