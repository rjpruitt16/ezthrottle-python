# Test 2: PERFORMANCE - Multi-region racing
# Flow: Submit job with 3 regions → Race execution → Verify fastest wins

POST {{APP_URL}}/test/performance/racing
HTTP 200

[Captures]
job_id: jsonpath "$.result.job_id"
idempotent_key: jsonpath "$.idempotent_key"

[Asserts]
jsonpath "$.test" == "performance_racing"
jsonpath "$.result.status" == "racing"
jsonpath "$.idempotent_key" startsWith "performance_racing_"

# Poll for webhook (racing might be faster, but allow 30s)
GET {{APP_URL}}/webhooks/{{job_id}}
[Options]
retry: 30
retry-interval: 1000
HTTP 200

[Asserts]
jsonpath "$.found" == true
jsonpath "$.webhook.data.job_id" == "{{job_id}}"
jsonpath "$.webhook.data.status" == "success"
jsonpath "$.webhook.data.idempotent_key" == "{{idempotent_key}}"
