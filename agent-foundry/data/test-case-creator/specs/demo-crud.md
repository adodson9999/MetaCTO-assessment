# api-tester-demo-crud — node card

- **What:** Exercise a full create/read/update/delete lifecycle and verify DB state.
- **How:**
1. Send POST /users with a valid body and capture the new id.
2. Query the database with SELECT * FROM users WHERE id = the captured id and assert one row.
3a. Send PUT /users/{id} changing one field and assert exactly 200.
3b. Query the database again and assert the changed field persisted.
4. Send DELETE /users/{id} and assert exactly 204.
5. Record the lifecycle outcome to results/crud-log.json.
- **Tools:** Python urllib, psql.
- **Metric:** CRUD Integrity Rate = correct steps / total steps. Pass: 100%. Fail: any HTTP or DB state mismatch.
