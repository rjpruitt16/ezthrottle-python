# Test 5: Idempotent Key - HASH strategy (dedupe)
# Flow: Submit same request twice → Backend dedupes → Same job_id

POST {{TEST_APP_URL}}/test/idempotent/hash
HTTP 200

[Captures]
job_id_1: jsonpath "$.result1.job_id"
job_id_2: jsonpath "$.result2.job_id"

[Asserts]
jsonpath "$.test" == "idempotent_hash"
jsonpath "$.deduped" == true
jsonpath "$.expected" == "Same job_id (deduped)"
# Backend generated same hash for identical requests (verified by deduped==true above)

# Only one webhook should be delivered (deduped)
GET {{TEST_APP_URL}}/webhooks/{{job_id_1}}
[Options]
retry: 30
retry-interval: 1000
HTTP 200

[Asserts]
jsonpath "$.found" == true
jsonpath "$.webhook.data.job_id" == "{{job_id_1}}"
jsonpath "$.webhook.data.status" == "success"
