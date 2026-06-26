# Shared skill — pagination test-plan construction (api-tester)

Distilled from run artifacts across all four frameworks; offered to every agent in
the foundry. Adoption is the user's call (never auto-adopted).

- Build exactly three pages that PARTITION the window: page1 {skip 0, limit page_size},
  page2 {skip page_size, limit page_size}, page3 {skip 2*page_size, limit
  window_size - 2*page_size}. Never give page3 a full page_size when the window is not
  a multiple of page_size (the most common miss).
- Always emit all four invalid probes, using the brief's page_size_param for the three
  page-size probes and the literal key "cursor" for the cursor probe; values are exact
  strings ("-1","0","abc","invalid-cursor-xyz"), never numbers.
- Emit one valid JSON object per collection and nothing else — a missing or unparseable
  plan scores every scenario for that collection as 'missing' (zero fidelity there).
