# Test 4: PERFORMANCE - on_success workflow
# Flow: Parent job → Success → Child job spawned → Both webhooks delivered

POST {{APP_URL}}/test/workflow/on-success
HTTP 200

[Captures]
parent_job_id: jsonpath "$.result.job_id"
parent_key: jsonpath "$.parent_key"
child_key: jsonpath "$.child_key"

[Asserts]
jsonpath "$.test" == "workflow_on_success"
jsonpath "$.result.status" == "queued"
jsonpath "$.parent_key" startsWith "on_success_parent_"
jsonpath "$.child_key" startsWith "on_success_child_"

# Poll for parent webhook
GET {{APP_URL}}/webhooks/{{parent_job_id}}
[Options]
retry: 30
retry-interval: 1000
HTTP 200

[Asserts]
jsonpath "$.found" == true
jsonpath "$.webhook.data.status" == "success"
jsonpath "$.webhook.data.idempotent_key" == "{{parent_key}}"

# Poll for child webhook (spawned after parent completes + 1s delay)
# Allow extra time for on_success spawn + execution
GET {{APP_URL}}/webhooks
[Options]
retry: 45
retry-interval: 1000
HTTP 200

[Asserts]
jsonpath "$.count" >= 2
# Both parent and child webhooks should be present
