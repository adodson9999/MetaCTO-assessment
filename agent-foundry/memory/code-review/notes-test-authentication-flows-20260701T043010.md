# Code-review notes — api-tester/test-authentication-flows — 20260701T043010
threshold=85 status=fail min_rating=0

## adversarial-input  (passed 0/14)
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid
  - FAIL [70] agents/common/runners/subagent_runner.py
      UnicodeDecodeError from invalid UTF-8 in HTTP response is not caught. In _request_local(), the line `raw.decode('utf-8', errors='strict')` raises UnicodeDecodeError if the backend returns invalid UTF-8 bytes. The _via_local() except clauses catch json.JSONDecodeError, KeyError, etc., and urllib.error.URLError, but not UnicodeDecodeError, so it propagates uncaught and crashes invoke(). A malformed backend returning `\xff\xfe` or other invalid UTF-8 will crash the process instead of gracefully returning None and falling through to BackendUnavailable. Fix: add UnicodeDecodeError to the except clause in _via_local() (or change errors='strict' to errors='replace'/'ignore' to match _bounded's approach). The docstring promises handling malformed responses; this violates that contract.

## api-contract  (passed 0/14)
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid
  - FAIL [82] agents/common/runners/subagent_runner.py
      Code is backward-compatible for external callers of build_invoker() and the returned invoke(brief: str) -> str contract. Minor maintainability issue: response_format uses a mutable dict default (should be None with a guard inside the function). The parameter signature, return type, and exception class (BackendUnavailable) are clear and stable. To reach 100: change response_format: Optional[dict] = {"type": "json_object"} to response_format: Optional[dict] = None, then set a local default inside build_invoker if needed.

## chaos-engineering  (passed 0/14)
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid

## concurrency  (passed 0/14)
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [38] scripts/backend_config.py
      Shared mutable state: socket.setdefaulttimeout() in _resolve_host_ip() is a check-then-act on global socket timeout with no synchronization. If two threads call _resolve_host_ip() concurrently, both read prev, both set timeout to 0.5, both run getaddrinfo(), then both restore prev in arbitrary order—the second restore overwrites the first thread's intended original value, corrupting the global timeout for other code. Interleaving: Thread A reads prev=None, Thread B reads prev=None, A sets 0.5, B sets 0.5, A restores None, B tries to restore None (already done), but now an unrelated Thread C that expected default timeout has lost it. Fix: wrap the read-modify-restore in a threading.Lock to serialize access to the global socket timeout: with _socket_timeout_lock: prev=socket.getdefaulttimeout(); socket.setdefaulttimeout(_DNS_TIMEOUT_S); ... ; socket.setdefaulttimeout(prev)
  - FAIL [75] agents/common/runners/crewai_runner.py
      Shared state: the `random` module's internal PRNG state. Interleaving: two threads call `invoke()` concurrently, both eventually hit `_kickoff_with_retry` → `_sleep_backoff` → unguarded `random.uniform()` call, which corrupts the shared PRNG state without synchronization. Consequence: the intended full-jitter de-correlation property is lost, allowing concurrent callers to retry in lockstep. Fix: add `import threading; _random_lock = threading.Lock()` at module level and wrap the call: `with _random_lock: jitter = random.uniform(0, delay)` before `time.sleep(jitter)`.

## data-integrity  (passed 2/14)
  PASSED >=85: runners/langgraph_runner.py, scripts/backend_config.py
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid

## device-stack  (passed 0/14)
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid

## error-handling-resilience  (passed 0/14)
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid

## logic-error  (passed 0/14)
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid

## maintainability  (passed 0/14)
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      ```json
{"rating": 100, "notes": "No change is needed. The code is clear, well-named, and easy to change safely. Each function has a single, obvious responsibility with appropriately documented intent. Names accurately describe what each function does (\_error\_json, \_validate\_spec, \_llm\_kwargs, \_sleep\_backoff, \_kickoff\_with\_retry, \_build\_llm, \_bounded\_brief, build\_invoker). Magic nu
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid

## math-correctness  (passed 1/14)
  PASSED >=85: runners/utils.py
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid

## memory-resource  (passed 0/14)
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [48] agents/common/runners/langgraph_runner.py
      LLM client objects (OpenAI, ChatAnthropic, ChatOllama) created in _openai_caller, _anthropic_caller, and _ollama_caller are instantiated fresh on each _build_call invocation, captured in closures, and never explicitly closed. Every call to build_invoker creates a new unclosed client (or llm) object that may hold connection pools or file handles. Over multiple agent runs in the agent-foundry system, these accumulate as leaked resources. To reach 100: (1) cache and reuse clients by backend spec and model, or (2) add explicit __del__ or close() methods to clean up clients when the returned invoke callable is garbage-collected, or (3) wrap build_invoker in a context manager that closes all clients on exit, or (4) provide a cleanup callback on the returned invoker that closes captured clients.
  - FAIL [80] scripts/backend_config.py
      Handler accumulation on module reload: logging.getLogger(__name__).addHandler(logging.NullHandler()) at module level registers a new handler every time the module is reloaded without removing the old one. While NullHandler is benign and the practical impact is minimal, handlers are still registered and never unregistered. Fix: check if the handler is already present before adding with `if not any(isinstance(h, logging.NullHandler) for h in log.handlers): log.addHandler(logging.NullHandler())`.

## minimalist  (passed 1/14)
  PASSED >=85: runners/claude_sdk_runner.py
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid

## network  (passed 2/14)
  PASSED >=85: runners/claude_sdk_runner.py, test-authentication-flows/score.py
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid
  - FAIL [74] agents/common/runners/langgraph_runner.py
      No jitter in exponential backoff; under high concurrency on a flaky network, all clients retry at synchronized times (thundering herd), amplifying load spikes on a struggling backend. Add random jitter: import random; delay = _BACKOFF_BASE_S * (2 ** (attempt - 1)) * (0.5 + random.random()); time.sleep(delay) in _with_retry() to desynchronize retry storms.

## observability  (passed 1/14)
  PASSED >=85: runners/utils.py
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid
  - FAIL [76] agents/common/runners/langgraph_runner.py
      generate_node completes without logging the success path. If the LLM call returns unexpected output (empty string, truncated response, wrong content), you won't see a log line confirming the operation completed successfully—you'd only infer it from the absence of an error log. Add `log.debug('langgraph generate_node LLM call completed', output_chars=len(content))` after the successful call (before `on_usage`) to make the happy path visible and diagnosable when troubleshooting downstream failures caused by unexpected model output.

## performance  (passed 1/14)
  PASSED >=85: runners/crewai_runner.py
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid

## security  (passed 1/14)
  PASSED >=85: runners/langgraph_runner.py
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/crewai_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid

## system-design  (passed 2/14)
  PASSED >=85: runners/langgraph_runner.py, runners/crewai_runner.py
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid

## unit-test  (passed 0/14)
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [68] agents/common/runners/crewai_runner.py
      Real gaps in critical paths: (1) _validate_spec has no tests for missing/non-string/empty 'model' field — add test_validate_spec_missing_model_raises() and test_validate_spec_non_string_model_raises(); (2) _llm_kwargs never verifies temperature=0 is set for any kind — add assertions like assert kw['temperature'] == 0 to all three kind tests; (3) build_invoker never verifies system/role/goal/expected_output are passed to Agent/Task — add checks on _FakeAgent.kwargs['backstory'] == system and _FakeTask.kwargs['description'] contains the brief after user_message_fn(). The retry, degradation, error-JSON, and brief-truncation logic are well tested, but these three gaps would allow bugs in core parameter passing and LLM configuration to escape undetected.

## vulnerability  (passed 1/14)
  PASSED >=85: runners/crewai_runner.py
  - FAIL [0] agents/api-tester/test-authentication-flows/crewai/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/subagent/run.py
      invalid
  - FAIL [0] agents/api-tester/test-authentication-flows/langgraph/run.py
      invalid
  - FAIL [0] agents/common/auth_harness.py
      invalid
  - FAIL [0] agents/common/auth_spec.py
      invalid
  - FAIL [0] agents/common/auth_prompt.py
      invalid
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      invalid
  - FAIL [0] agents/common/runners/langgraph_runner.py
      invalid
  - FAIL [0] agents/common/runners/utils.py
      invalid
  - FAIL [0] agents/common/runners/subagent_runner.py
      invalid
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      invalid
  - FAIL [0] scripts/backend_config.py
      invalid
