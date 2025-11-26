# Test 6: Idempotent Key - UNIQUE strategy (allow duplicates)
# Flow: Submit same request with different keys → Both allowed → Different job_ids

POST {{APP_URL}}/test/idempotent/unique
HTTP 200

[Captures]
job_id_1: jsonpath "$.result1.job_id"
job_id_2: jsonpath "$.result2.job_id"
key_1: jsonpath "$.key1"
key_2: jsonpath "$.key2"

[Asserts]
jsonpath "$.test" == "idempotent_unique"
jsonpath "$.different" == true
jsonpath "$.expected" == "Different job_ids"
# Different keys allow duplicate requests
jsonpath "$.key1" startsWith "idempotent_unique_1_"
jsonpath "$.key2" startsWith "idempotent_unique_2_"

# Both webhooks should be delivered
GET {{APP_URL}}/webhooks/{{job_id_1}}
[Options]
retry: 30
retry-interval: 1000
HTTP 200

[Asserts]
jsonpath "$.found" == true
jsonpath "$.webhook.data.job_id" == "{{job_id_1}}"
jsonpath "$.webhook.data.idempotent_key" == "{{key_1}}"

GET {{APP_URL}}/webhooks/{{job_id_2}}
[Options]
retry: 30
retry-interval: 1000
HTTP 200

[Asserts]
jsonpath "$.found" == true
jsonpath "$.webhook.data.job_id" == "{{job_id_2}}"
jsonpath "$.webhook.data.idempotent_key" == "{{key_2}}"
