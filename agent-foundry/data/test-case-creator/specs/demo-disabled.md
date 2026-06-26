# api-tester-demo-disabled — node card

- **What:** A disabled node, excluded from the registry by the manifest filter.
- **How:**
1. Send GET /ignored and assert exactly 200.
- **Tools:** Python urllib.
- **Metric:** Should never appear in the registry. Pass: absent. Fail: present.
