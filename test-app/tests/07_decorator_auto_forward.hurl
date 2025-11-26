# Test 7: @auto_forward Decorator - Legacy code integration
# Flow: Legacy code raises exception → Decorator auto-forwards → Job queued

POST {{APP_URL}}/test/decorator/auto-forward
HTTP 200

[Captures]
job_id: jsonpath "$.result.job_id"
idempotent_key: jsonpath "$.idempotent_key"

[Asserts]
jsonpath "$.test" == "decorator_auto_forward"
jsonpath "$.message" == "Auto-forwarded!"
jsonpath "$.result.status" == "queued"
jsonpath "$.result.job_id" exists
jsonpath "$.idempotent_key" startsWith "decorator_forward_"

# Poll for webhook (auto-forwarded request)
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
