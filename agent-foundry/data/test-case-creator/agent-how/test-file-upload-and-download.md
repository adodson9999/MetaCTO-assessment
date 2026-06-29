# api-tester-test-file-upload-and-download — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for file upload/download testing. Assert the setup preconditions hold before probing.
  2. Upload a valid file. Assert it is accepted and retrievable.
  3. Upload an oversized file. Assert it is rejected per docs.
  4. Upload an invalid mime type. Assert it is rejected.
  5. Aggregate every scenario result and record the outcome. Assert the file integrity and rejection rates is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: file integrity and rejection rates meets the gold threshold. Fail: a file operation diverges from docs.
