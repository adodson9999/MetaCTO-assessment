# Code-review notes — api-tester/test-authentication-flows — 20260701T182558
threshold=85 status=fail min_rating=0

## adversarial-input  (passed 2/14)
  PASSED >=85: runners/claude_sdk_runner.py, scripts/backend_config.py
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [35] agents/common/auth_harness.py
      The `_message_of(text)` call in `_run_one_subtest` (in the return statement) is outside the try/except block and can raise `RecursionError` when the response body contains deeply-nested JSON. If a response body has 300+ levels of nesting (e.g., `{"a":{"a":{...}}}` repeated), `json.loads` exceeds Python's default recursion limit (~1000) and raises `RecursionError`, which is NOT caught by `except ValueError`. This uncaught exception propagates through `_execute_subtests` (which has no try/except around the `_run_one_subtest` call) and crashes the harness. A simple 1 MiB JSON with 300 nesting levels is trivial to construct and well within the `_MAX_BODY_BYTES` cap. The docstring promises "every failure...is recorded as an explicit failure" but fails to keep this promise. Fix: move `_message_of(text)` into the try/except block, or change `except ValueError` to `except (ValueError, RecursionError)` or `except Exception` to match the stated resilience intent.
  - FAIL [45] agents/common/auth_prompt.py
      The scheme_brief parameter is explicitly documented as UNTRUSTED, but the function calls str(scheme_brief) without any defense against malicious __str__ methods. A hostile object can exhaust memory or hang during the str() coercion before the length cap is applied. For example, passing an object whose __str__() returns a 1 GB string would cause OOM. Fix: add type validation (if not isinstance(scheme_brief, str): reject-or-use-safe-fallback) or wrap str() with exception handling and timeout before the length check. The defensive bounds checking later in the function is good, but it comes too late to stop the str() conversion itself from being exploited.
  - FAIL [55] agents/common/auth_spec.py
      RecursionError from deeply nested JSON: both login_token and decode_jwt_payload call json.loads() on untrusted server responses without catching RecursionError. An adversarial server can return JSON nested deeper than Python's recursion limit (~1000 levels), e.g. a 4MB response of only '[' characters (~2M nesting levels), triggering an unhandled RecursionError crash. Fix: add RecursionError to the except clause in login_token (line ~185) and decode_jwt_payload (line ~107), or use Python 3.12+ json.JSONDecoder with object_hook depth tracking before parsing.
  - FAIL [60] agents/api-tester/test-authentication-flows/subagent/run.py
      FORGE_WORKSPACE (environment variable) is resolved via Path.resolve() at module initialization time, outside any deadline protection. A circular symlink in the environment path—e.g., FORGE_WORKSPACE pointing to a symlink that cycles back on itself—can cause Path.resolve() to hang indefinitely (or raise RecursionError in some Python versions), freezing the entire process at import before deadline infrastructure is available. No timeout guards this operation. Constructible input: `mkdir -p /tmp/loop/a; ln -s /tmp/loop /tmp/loop/a/link; FORGE_WORKSPACE=/tmp/loop/a/link python3 run.py` hangs. Fix: wrap Path.resolve() in a deadline (e.g., threading timeout), use resolve(strict=True) to fail fast on cycles, or explicitly detect cycles before resolving to reach 100.
  - FAIL [62] agents/api-tester/test-authentication-flows/langgraph/run.py
      Two real hanging vulnerabilities: (1) _validated_workspace() is called at module import time without a deadline — if FORGE_WORKSPACE points to a hung network mount, Path.resolve() or is_dir() will hang indefinitely, preventing module load. Input: FORGE_WORKSPACE=/hung/network/mount. Fix: wrap the Path operations in _call_with_deadline (e.g., _call_with_deadline(lambda: Path(raw).resolve(), timeout, "validate_workspace")) or return a fallback safely. (2) _field(value) calls str(value) without timeout; if the summary dict contains an object with a pathological __str__ method that hangs (e.g., infinite recursion that completes after minutes), _field will block indefinitely during the final output stage. Input: summary dict with a value whose __str__ hangs. Fix: wrap the str(value) call in _call_with_deadline to enforce a timeout, falling back to "<unrenderable>" on TimeoutError, mirroring the exception-handling pattern already present. The rest of the dispatch (invoke wrapping, truncation, deadline/retry/logging) is well-hardened.
  - FAIL [77] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      The brief string from auth_harness.scheme_brief() is not size-capped before being captured in the generate() closure and passed to invoke(). If scheme_brief() returns an unboundedly large string (e.g., 1+ GB), the process would store that entire string in memory for the duration of the harness run. While the code caps the model response (1 MiB), applies a deadline to invoke(), and safely renders summary fields, the internal brief generation has no limit. Fix: cap the brief before use, e.g. `if len(brief) > 1_000_000: brief = brief[:1_000_000]` after _generate_brief() returns, or inside _generate_brief() itself, to prevent memory exhaustion from an oversized brief.
  - FAIL [80] agents/api-tester/test-authentication-flows/crewai/run.py
      The dispatcher is well-hardened for most external inputs (FORGE_WORKSPACE env var, model response capped at 1 MiB, graceful degradation on failures). However, in `_emit_summary()`, the code calls `_field()` which invokes `str(value)` on summary dict values from the harness without a timeout or recursion/resource limit. If the harness returns an object whose `__str__()` method hangs (infinite loop) or consumes excessive memory, the entire dispatcher hangs or crashes. The fix: add a wall-clock timeout to `_emit_summary()` or `_field()` (similar to the pattern already used in `_call_with_deadline()`), or pre-validate that all summary values are safe, primitive types (str/int/float/bool/None) before rendering.

## api-contract  (passed 7/14)
  PASSED >=85: crewai/run.py, langgraph/run.py, subagent/run.py, common/auth_harness.py, common/auth_prompt.py, common/auth_spec.py, runners/claude_sdk_runner.py
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [70] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      Exit-code behavior change likely breaks CI systems: the harness run failure (exception from auth_harness.run_auth_test) is now caught in main() and degraded to summary=None → headline still printed → exit 0. If external callers (CI/judge scripts) were checking exit codes to detect harness failures and expected non-zero on failure, this breaks them. Docstring says behavior is 'preserved' and headline is 'SAME', but the exit-code contract is not explicitly addressed. Fix: after _emit_summary, check if summary was empty/None and call sys.exit(1) if harness failed, OR document the new graceful-degradation exit behavior and update CI/caller systems to parse the headline (metrics) instead of relying on exit codes.

## chaos-engineering  (passed 4/14)
  PASSED >=85: crewai/run.py, langgraph/run.py, runners/claude_sdk_runner.py, scripts/backend_config.py
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [48] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      Injected setup-phase faults (backend timeout via resolve_backend(), file-read timeout via load_system_prompt(), or import failure of auth_harness) cascade into full unstructured process crashes with no graceful degradation or observable steady state. While generation and harness faults are well-protected (deadline + retry + caught exception → empty plan → headline still emitted), the setup phase has no try-except wrapping _prepare() in main(), so a 60s backend timeout → retried 3 times (180s+) → TimeoutError uncaught → process exits with unstructured exception, no headline, no "done" log. Similarly, module imports (auth_harness, auth_prompt, runners) fail hard with no fallback. Fix: wrap _prepare() call in try-except, emit a marked headline on setup fault (e.g., "[claude_sdk:abc123] setup failed (resolve_backend timeout)"), log exception type only, and ensure _emit_summary() is always called even on setup failure so results are always observable and the blast radius stays bounded.
  - FAIL [60] agents/common/auth_prompt.py
      Injected fault: system out of thread resources in _read_bytes_with_timeout(). The threading.Thread() constructor and .start() call are not wrapped in try-except. When thread creation fails (severe resource exhaustion), the exception propagates unhandled out of _read_bytes_with_timeout(), bypasses the OSError and _IoTimeout handlers in _read_bounded(), and crashes active_prompt() with no fallback to APPROVED_PROMPT. This violates the documented contract: 'Any missing / out-of-scope / oversized / unreadable / undecodable / slow override degrades to APPROVED_PROMPT... the live gated prompt can never be silently displaced.' The cascade is: thread creation failure → unhandled exception → agent prompt initialization failure → full outage with no graceful degradation. Wrap both threading.Thread() and .start() in try-except and raise _IoTimeout to reuse the existing timeout-handling path: try: worker = threading.Thread(...); worker.start() except Exception: raise _IoTimeout. This reconnects thread creation failures to the degrade-to-APPROVED_PROMPT contract and bounds the blast radius to the override system only.
  - FAIL [78] agents/api-tester/test-authentication-flows/subagent/run.py
      Injected failure: a dependency (resolve_backend or load_system_prompt) with NO internal timeout hangs indefinitely; _call_with_deadline times out at 60s and raises TimeoutError, then abandons the daemon thread with blocked I/O. On retry (up to 2 retries = 3 attempts), up to 3 daemon threads accumulate in the background, each holding ~1-2 MB stack memory. Scenario: 1000 sequential dispatcher runs with frequent setup timeouts = 3000 accumulated daemon threads = ~6 GB memory leak. The process exits cleanly (steady state preserved, blast radius bounded), but resource accumulation grows under sustained infrastructure stress. Fix: add explicit socket/network timeouts to load_system_prompt and resolve_backend (enforce the undocumented assumption that 'every I/O fn performs here ... carries its OWN timeout'), or use timeout-aware context managers (e.g. `urllib.request.urlopen(url, timeout=N)`) instead of relying on daemon thread abandonment to eventually unblock.
  - FAIL [80] agents/common/auth_spec.py
      When /auth/login is injected to be down, all login-dependent credential recipes (valid_token, truncate_token, expired_token, revoked_token) will each burn REQUEST_TIMEOUT_S × MAX_ATTEMPTS = 60s waiting for timeout before returning (None, 'login failed'). The blast radius is bounded (4/5 subtests fail, no_auth still works; downstream agents see None and degrade gracefully; no wedged state after recovery), but the repeated 60-second waits across sequential build_credential() calls defeat fast failure. A circuit breaker on login_token() that fails fast after the first failure—either by skipping retries on the 2nd/3rd recipe or returning a cached failure sentinel—would eliminate the unbounded timeout cascade and drop below 85. Current state: has timeout + fallback (required) but no circuit breaker or bulkhead; recovery is automatic once login returns. To reach 100: add a login circuit breaker that fails fast on second/third recipe attempt instead of re-burning the full 60s per call.
  - FAIL [84] agents/common/auth_harness.py
      Code is sound with timeouts and fallbacks, but lacks key chaos patterns. Inject transient endpoint errors (5xx, connection reset): individual cases fail with no retry, degrading auth-flow accuracy; add bounded retry with exponential backoff and jitter on transient errors (not on 4xx). Inject memory-pool flakiness: each everos_note() call retries up to 2x, but successive failures cause repeated retry storms on the next agent run; add circuit breaker to skip retries after N consecutive failures and degrade to local-only by default. Inject hung filesystem (NFS stall): _read_text_capped() and _atomic_write() block indefinitely with no timeout; add timeout via signal or async I/O to prevent wedging. Endpoint timeout (20s) + case fallback, and atomic writes + rollback are strong; LLM timeout (60s) + daemon thread + empty-plan fallback is excellent. File I/O and memory pool retry both lack jitter; add jitter (full = backoff * random(1.0, 1.5)) to prevent synchronized retry storms across concurrent agents.

## concurrency  (passed 8/14)
  PASSED >=85: claude_sdk/run.py, crewai/run.py, langgraph/run.py, subagent/run.py, common/auth_harness.py, common/auth_spec.py, runners/claude_sdk_runner.py, scripts/backend_config.py
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [50] agents/common/auth_prompt.py
      METRICS dictionary has a non-atomic read-modify-write race in _bump(). When two threads call _bump() concurrently, both may read the same counter value (e.g., 5), increment it, and write back 6, losing one update — the counter should be 7. The interleaving: Thread A reads METRICS.get(metric, 0)→5, Thread B reads METRICS.get(metric, 0)→5, Thread A writes METRICS[metric]=6, Thread B writes METRICS[metric]=6. Result: lost increment. Fix by protecting all METRICS updates with a lock: create _metrics_lock = threading.Lock() at module level, then guard _bump() with `with _metrics_lock: METRICS[metric] = METRICS.get(metric, 0) + 1`.

## data-integrity  (passed 7/14)
  PASSED >=85: crewai/run.py, langgraph/run.py, subagent/run.py, common/auth_harness.py, common/auth_prompt.py, common/auth_spec.py, runners/claude_sdk_runner.py
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [55] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      auth_harness.run_auth_test() is retried up to 2 times (retries=_RETRIES in _run_step call) with no deduplication. The request_id that could serve as a deduplication key is not passed to run_auth_test(). If the harness writes test results or records (as suggested by the phrase 'the harness records an explicit failing case'), each retry causes duplicate records. Pass request_id to run_auth_test() so it can deduplicate retries using the request_id as a stable key, or remove retries from the harness call since non-idempotent operations should not be retried.

## device-stack  (passed 2/14)
  PASSED >=85: langgraph/run.py, common/auth_spec.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [65] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      Daemon thread resource accumulation on timeout — _call_with_deadline creates daemon threads that may be abandoned when join() times out, relying on implicit assumption that underlying I/O (urllib in runner, file reads in load_system_prompt) has nested timeouts. Code documents this assumption but does not enforce it. If underlying timeouts are missing or exceed the deadline, daemon threads accumulate indefinitely, especially under repeated timeouts or concurrent test runs, eventually hitting OS limits (thread count, file descriptors). Example: _prepare makes 3 _run_step calls with retries=2, potentially creating 9+ threads; if any timeout, they remain blocked on I/O while the process continues. Fix: Use ThreadPoolExecutor or semaphore to explicitly bound concurrent daemon threads, validate that all I/O carries timeouts strictly < deadline, or implement proper cancellation/cleanup on timeout via asyncio or context managers.
  - FAIL [76] agents/common/auth_prompt.py
      Path.resolve() in _workspace_root() has no explicit timeout and can hang indefinitely on systems with a hung network mount and unconfigured/infinite OS-level I/O timeout. The try/except catches OSError but on misconfigured systems or some OS/filesystem combinations (NFS without read timeout, Windows network shares in certain error states), stat() inside resolve() may block forever rather than raising an exception. The I/O timeout applied to file reads via daemon threads is good (prevents caller hang), but the same protection is missing from path resolution at startup. To reach 100, wrap _workspace_root()'s resolve() call in a timeout thread with a 2-second deadline (like _read_bytes_with_timeout), re-raising _IoTimeout as OSError so the caller degrades to APPROVED_PROMPT instead of potentially blocking indefinitely during agent startup.
  - FAIL [81] agents/api-tester/test-authentication-flows/crewai/run.py
      Daemon thread resource abandonment on deadline expiry: _call_with_deadline spawns a daemon thread and joins with a timeout; if join() times out, the worker thread is abandoned while potentially holding I/O resources (file descriptors, sockets). The code mitigates this by assuming all I/O operations inside fn() carry their own timeouts (documented in docstring), but if an operation lacks a timeout (e.g., urllib.socket.connect without timeout parameter), the abandoned daemon thread could hold the resource indefinitely. This violates the runtime-revocable FD/handle guarantee on real systems. Change: either (1) require all I/O operations to explicitly set timeouts before calling _call_with_deadline, (2) implement a more aggressive resource-cleanup mechanism for abandoned threads (e.g., resource cleanup registry), or (3) use thread-safe cancellation tokens and non-daemon threads with explicit cleanup on timeout. The code documents the assumption clearly, mitigating severity; design is sound if assumption holds.
  - FAIL [82] agents/api-tester/test-authentication-flows/subagent/run.py
      Thread abandonment on timeout creates a resource-leak risk if underlying I/O operations (model invocation, backend resolution) lack their own timeouts. When _call_with_deadline times out, the worker thread is abandoned as a daemon with an active I/O operation (e.g., blocked socket read on a stalled API). The thread then holds a file descriptor until process exit, consuming OS handle limits if this dispatcher is invoked many times in a long-running service. The comments claim 'every I/O carries its OWN timeout' (urllib, file reads) but the critical invoke() call's timeout is not verifiable from this code. Mitigation: ensure the runner's model-invoke call sets an explicit socket/request timeout shorter than _HARNESS_DEADLINE_S, OR replace thread-join-with-timeout with an interruptible async pattern that can actually cancel blocking I/O (e.g., signal handling or asyncio.wait_for with proper cancellation).
  - FAIL [82] agents/common/auth_harness.py
      Wall-clock timeout in threading.Thread.join() is not robust to system clock adjustments. The _GENERATE_TIMEOUT_S timeout uses threading.Thread.join(wall_clock_seconds), which relies on time.time() rather than a monotonic clock. If system clock is adjusted backward (NTP, manual set, VM time skew), the join may return immediately without actually waiting. If clock goes forward rapidly, the join may wait longer than intended. Fix: use threading.Event with time.monotonic()-based polling, or a threading.Condition with explicit monotonic deadline tracking, to make the timeout immune to clock adjustments. The code otherwise handles device realities well (bounded I/O, atomic writes, FD cleanup, no unbounded allocations), but this timeout logic is the weak link under real OS behavior where clock skew can occur. No change needed if clock stability is guaranteed, but the code should not assume it.

## error-handling-resilience  (passed 1/14)
  PASSED >=85: scripts/backend_config.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [67] agents/api-tester/test-authentication-flows/crewai/run.py
      print() failure in _emit_summary propagates uncaught to main(), crashing the dispatcher—contradicting the code comment stating 'telemetry always completes even if print fails (broken pipe).' When stdout is broken, print() raises but is not caught; the finally block then runs and also propagates (possibly losing the original error). Fix: wrap print() in its own try-except that logs the failure and continues to ensure the 'done' log always emits, and wrap the finally log.info() in try-except as well to degrade gracefully when logging is also unavailable. This aligns the implementation with the stated resilience intent.
  - FAIL [70] agents/common/auth_harness.py
      The function `_execute_subtests()` can raise if `auth_spec.iter_subtests(plan)` raises due to a malformed plan, and this exception is not caught in `run_auth_test()`. If the loop raises partway through, the function jumps to the caller with no recovery: cases and tally are never returned, `_safe_persist_findings()` is never called, `_persist_run()` is never called, and no results are persisted. The run fails silently with an unhandled exception instead of being recorded as a test failure. To reach 100, wrap `_execute_subtests()` in a try/except inside `run_auth_test()` and degrade gracefully: `try: cases, tally = _execute_subtests(plan) except Exception as e: logger.error(...); cases = [_no_plan_case(f'test execution failed: {e}')]; tally = {'executed': 0, 'correct': 0, 'false_accept': 0, 'false_reject': 0}`, ensuring findings and results are still persisted even when the loop fails.
  - FAIL [72] agents/api-tester/test-authentication-flows/langgraph/run.py
      The _call_with_deadline function abandons daemon threads on timeout, relying on an implicit assumption that all underlying I/O operations carry their own timeouts. While the code documents this assumption and it is reasonable for known operations (invoke explicitly has a timeout), the design is fragile: a function without its own I/O timeout (e.g., local file I/O in load_system_prompt if the filesystem hangs) will hold resources indefinitely until the process exits. Reach 100 by: (1) using concurrent.futures.ThreadPoolExecutor with explicit timeout context managers that guarantee thread cleanup before returning, or (2) adding a cancellation mechanism (threading.Event) that signals abandoned threads to stop gracefully rather than simply joining with a timeout, or (3) explicitly verifying and asserting in code comments that every function passed to _call_with_deadline has an enforced I/O timeout.
  - FAIL [75] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      print() failure in _emit_summary() causes an unhandled exception to propagate despite the finally block ensuring that completion telemetry is logged. The comment states 'telemetry always completes even if print fails (broken pipe)' and 'that log runs in the finally', which correctly describes the structured logging behavior. However, print failures (BrokenPipeError) are not caught, so the exception propagates from _emit_summary() to main() uncaught, causing the script to exit abnormally with a traceback despite all critical telemetry already being logged. This is inconsistent with the stated design intent. Fix: wrap the print() statement in a try/except that logs and suppresses print failures, ensuring _emit_summary() completes normally even on broken pipe: try: print(...) except Exception as exc: log.warning('[%s:%s] print failed (%s)', AGENT, request_id, type(exc).__name__)
  - FAIL [75] agents/api-tester/test-authentication-flows/subagent/run.py
      Abandoned daemon threads on timeout leak resources during execution. When _call_with_deadline times out, the worker thread runs in the background with potentially open sockets/file handles (e.g., from invoke/urllib). The thread is only cleaned up when its I/O completes (or the process dies); resources remain allocated until then. This violates the principle that failures should release resources. The code mitigates this by: (1) documenting that each I/O has its own timeout, (2) using bounded deadlines so waits are finite, (3) ensuring failures are logged and the headline still emits. To reach 100: replace thread.join(timeout) with a cancellable pattern (concurrent.futures.ThreadPoolExecutor.map timeout, or asyncio.wait_for with task cancellation), or add explicit close/cleanup hooks in the abandoned thread's finally block so resources release immediately rather than waiting for the underlying I/O timeout.
  - FAIL [75] agents/common/auth_spec.py
      In _close_error_fp(), OSError from fp.close() is caught and logged but not re-raised. When close() fails, the function returns normally (implicitly returns None / success), but the file pointer may remain open or in a half-closed state. The caller _read_error_body() then returns a valid (code, text) tuple, signaling to _request() that the error-handling succeeded, when actually the resource-release failed. This is failure reported as success — violates error-handling resilience. The error IS logged (observability is good) and GC will eventually clean the FP, but the immediate state after _close_error_fp() returns is ambiguous to the caller. To reach 100: re-raise the OSError from _close_error_fp() after logging (e.g. `raise OSError(f'Failed to close HTTPError fp: {exc}') from exc`), or wrap _close_error_fp() in _read_error_body()'s finally with an explicit try-except that logs and re-raises close failures.
  - FAIL [76] agents/common/auth_prompt.py
      The `user_message()` function does not handle exceptions raised by `str(scheme_brief)` when scheme_brief is a non-string object with a broken `__str__()` method. Although the function is explicitly documented as handling untrusted input defensively, if `str()` raises an exception it propagates unhandled, violating the function's contract to always return a string safely. To reach 100, wrap the `str()` call in try-except and degrade to a safe fallback: `try: brief = scheme_brief if isinstance(scheme_brief, str) else str(scheme_brief) except Exception as exc: _log(logging.WARNING, "scheme_brief coercion failed (%s)", exc); brief = ""`

## logic-error  (passed 6/14)
  PASSED >=85: claude_sdk/run.py, crewai/run.py, langgraph/run.py, subagent/run.py, common/auth_prompt.py, common/auth_spec.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [55] agents/common/auth_harness.py
      The regex in extract_json() uses non-greedy matching (`\{.*?\}`) on line with the fence pattern `r"```(?:json)?\s*(\{.*?\})*\s*```"`. This causes it to capture incomplete JSON when the object has nested braces: for input ```` ```json
{"a": {"b": 1}}
``` ````, the non-greedy `.*?` matches from the first `{` to the first `}` (inside the nested object), capturing `{"a": {"b": 1}` — invalid JSON that fails to parse, returning None and never falling back to the balanced-object scanner. The fix is to change `\{.*?\}` to `\{.*\}` (greedy matching) so that with clear fence delimiters, the regex captures from the first brace to the last brace before the closing fence marks.

## maintainability  (passed 2/14)
  PASSED >=85: common/auth_prompt.py, common/auth_spec.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [76] agents/api-tester/test-authentication-flows/crewai/run.py
      _emit_summary (lines ~73–91) conflates multiple distinct operations—validation, field rendering, metrics extraction, structured logging, and headline printing—within a single try/finally block. A future reader attempting to change the print format or metrics structure could easily break the telemetry guarantee without realizing it. Extract metrics extraction and logging into a helper function that returns rendered values, leaving _emit_summary to orchestrate just printing and telemetry-completion logging—this preserves the try/finally contract while clarifying the flow. Additionally, _run_step requires 4 keyword-only parameters (fn, label, deadline, request_id) plus an optional fifth (retries); grouping deadline and retries into a single ResilienceConfig namedtuple would reduce parameter count at call sites and improve readability without obscuring intent.
  - FAIL [78] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      The function name `_field` is too vague — a reader cannot determine from the name alone that it renders a summary value as a bounded, safe string for display. They must read the docstring or implementation to understand its purpose. Rename to `_bounded_str` or `_render_field` to clarify that it safely converts an object to a bounded string, preventing hostile __str__ implementations from causing problems. The rest of the code is well-structured, well-named, and clearly documented; this single unclear name is the maintainability friction point.
  - FAIL [78] agents/api-tester/test-authentication-flows/langgraph/run.py
      Threading pattern in _call_with_deadline is correct but not immediately obvious—the daemon-thread-with-join-timeout approach requires readers familiar with this pattern or careful study of the docstring to safely modify. Module-level state manipulation (_STATE_LOCK protecting sys.path and logger during import) happens at an unconventional time; a future editor modifying initialization order could accidentally create races. The _make_generate closure captures four variables (invoke, brief, request_id, started) across a nested function; renaming or reordering parameters risks subtle binding errors. To reach 100: (1) refactor _call_with_deadline to use concurrent.futures.ThreadPoolExecutor with timeout for clarity, (2) move sys.path and logger setup into an explicit _init() function called from main(), or (3) use a context manager to encapsulate state setup, and (4) extract the generate logic into a class or use functools.partial to make captured bindings explicit.
  - FAIL [83] agents/api-tester/test-authentication-flows/subagent/run.py
      Unreachable code at the end of _run_step: the final `raise RuntimeError(f"unreachable retry exit for {label}")` is dead (the loop always raises or returns before exiting). Although marked `# pragma: no cover`, the code path's existence confuses a reader analyzing the retry logic, making them verify whether the loop can exit normally—it cannot. Remove the unreachable raise statement after line 97, since when `attempt == retries` (the final iteration), `attempt < retries` is false, triggering the outer except block's raise. Everything else is clear, well-named, and excellently documented; this single dead line is the only maintainability burden.
  - FAIL [83] agents/common/auth_harness.py
      The code is well-documented with excellent docstrings, clear structure, and defensive error handling throughout. The single concrete maintainability issue is the variable name `box` in `_generate_plan()` — it's a dict used to pass results between a worker thread and the parent, but the name doesn't convey that purpose. A future reader unfamiliar with this threading pattern won't immediately understand why this approach was chosen. The module has implicit dependencies (reading from config.toml in `everos_note()`, reading from metric file in `emit()`, then chaining through `_persist_run()` → `_write_run_pair()` → `emit()`) that are documented in docstrings but could be more obvious at call sites. To reach 100: rename `box` to `thread_result` and add a one-line comment like `# dict to pass results from worker thread to parent` above line starting with `box: dict`; optionally add a docstring to `_write_run_pair()` noting that the metrics tuple unpacking could be replaced with explicit named parameters for clarity.

## math-correctness  (passed 7/14)
  PASSED >=85: claude_sdk/run.py, crewai/run.py, langgraph/run.py, subagent/run.py, common/auth_harness.py, common/auth_prompt.py, common/auth_spec.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)

## memory-resource  (passed 5/14)
  PASSED >=85: crewai/run.py, subagent/run.py, common/auth_harness.py, common/auth_spec.py, scripts/backend_config.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [75] agents/common/auth_prompt.py
      The _read_bytes_with_timeout() function spawns a daemon thread per call to timeout blocked I/O. On timeout, the function raises _IoTimeout and abandons the thread while it still holds an open file handle from path.open() inside _worker. Repeated calls with I/O timeouts accumulate abandoned daemon threads consuming stack space and file descriptors until process exit. To reach 100: replace the daemon-thread timeout with non-blocking I/O (async/await, select() on non-blocking FD, or signal SIGALRM) that cleanly closes file handles even on timeout, or add an explicit close-on-abandon exception handler inside _worker before the daemon detaches.
  - FAIL [80] agents/api-tester/test-authentication-flows/langgraph/run.py
      Daemon threads spawned in _call_with_deadline on timeout are abandoned when join() times out; they are not explicitly stopped. In a one-shot dispatcher (the intended use case), these threads are cleaned up when the process exits. However, if this code is ever run repeatedly in a long-running process, or if the underlying operations hang beyond their own timeouts (contrary to the docstring's assumption), threads would accumulate without bound. To reach 100: either explicitly terminate abandoned threads using a thread pool with timeout-and-cleanup semantics (e.g., concurrent.futures.ThreadPoolExecutor), or use async/await to avoid spawning threads; document explicitly that this is safe only for one-shot execution.
  - FAIL [82] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      Daemon threads created in _call_with_deadline() that timeout while blocked on I/O may retain file descriptors or socket handles until the nested I/O operation's own timeout fires and unblocks them. The design explicitly relies on downstream I/O timeouts (in urllib and load_system_prompt) to clean up before the deadline triggers abandonment; if any underlying I/O lacks a timeout or has a very long timeout, or if many timeout events accumulate concurrently, file descriptors could leak. To reach 100: either wrap all I/O with strict individual timeouts guaranteeing cleanup before deadline expiry, use subprocess instead of daemon threads to get OS-level isolation, or implement explicit thread termination with resource cleanup (e.g., force closing sockets before abandoning the thread).

## minimalist  (passed 4/14)
  PASSED >=85: langgraph/run.py, subagent/run.py, common/auth_harness.py, common/auth_prompt.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [73] agents/common/auth_spec.py
      Remove single-call helpers that add indirection without loss: eliminate _sleep_backoff (inline as time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1))); eliminate _default_expected (inline return statement in iter_subtests); eliminate _server_now (inline as int(time.time()); move the docstring as a comment); consider inlining _close_error_fp into the finally block of _read_error_body and _build_request into _request (both are single-call extractions justified for maintainability, not minimalism). These helpers add parameter-passing overhead and indirection for code that could be simpler inlined.
  - FAIL [76] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      The `_field` function has a micro-optimization (slicing to `_MAX_FIELD_CHARS + 1` then checking if truncation is needed) that adds complexity without proportional safety gain; simplify to just `text = str(value)` followed by a single check `if len(text) > _MAX_FIELD_CHARS: return text[:_MAX_FIELD_CHARS] + "…"`. Additionally, the unreachable `raise RuntimeError` at the end of `_run_step` (marked `pragma: no cover`) is defensive code that could be removed entirely since the loop always exits via return or raise.
  - FAIL [83] agents/api-tester/test-authentication-flows/crewai/run.py
      Redundant exception logging in _generate_brief: the log.error call duplicates the error already logged by _run_step, which has already recorded the failure with timing and request context. Remove the log.error line and let the exception handler just return "". Additionally, _build_invoker is a pass-through function (return build_invoker(WS, system, user_message)) that exists only as a seam point but adds indirection without adding logic; inline this one-liner into the lambda in _prepare to remove the function definition and reduce call depth.

## network  (passed 5/14)
  PASSED >=85: langgraph/run.py, subagent/run.py, common/auth_prompt.py, common/auth_spec.py, scripts/backend_config.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [72] agents/common/auth_harness.py
      The main request via auth_spec._request() does not show a timeout parameter being passed (line ~395), despite a timeout constant being defined (_REQUEST_TIMEOUT_S = 20s). If auth_spec._request() lacks a timeout or has a longer default, a slow endpoint can hang indefinitely, wedging the entire batch. The comment claims timeout enforcement but this is not visible in the code being reviewed. Secondary network operations (everos pool POST and generate() call) are well-handled with bounded retries, exponential backoff, idempotency keys, and hard timeouts. The target is localhost-only (mitigates some flakiness). To reach 100: explicitly pass timeout=_REQUEST_TIMEOUT_S to each auth_spec._request() call, document that auth_spec._request() enforces exponential-backoff bounded retries on transient errors only (not on definite 4xx/5xx), and verify retry logic includes an idempotency key or restricts retries to idempotent operations.
  - FAIL [75] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      build_invoker is called without retries while load_system_prompt and resolve_backend both have retries=_RETRIES. The module docstring states 'Setup steps additionally get a bounded, JITTERED exponential-backoff retry' but build_invoker omits this: it has only a 60s deadline and 1 attempt, no retry. A transient failure (timeout, connection error) during client initialization fails the whole run immediately instead of retrying with backoff+jitter like the other setup steps. Fix: add `retries=_RETRIES` to the build_invoker _run_step call in _prepare() so it matches the retry pattern for load_system_prompt and resolve_backend, bringing it to 100.
  - FAIL [78] agents/api-tester/test-authentication-flows/crewai/run.py
      Retrying run_auth_test() on timeout can cause duplicate model invocations if the timeout occurs after invoke() succeeds but before test execution completes. The generate() closure calls invoke() fresh on each call, so a retry of the harness run spawns another model invocation without an idempotency key or deduplication. To reach 100: cache the plan result across retries (e.g., store the first invoke() output in a mutable container and reuse it), or add an idempotency key to model calls so the backend detects and suppresses duplicate requests.

## observability  (passed 6/14)
  PASSED >=85: langgraph/run.py, subagent/run.py, common/auth_harness.py, common/auth_prompt.py, common/auth_spec.py, scripts/backend_config.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [35] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      All structured logging (metrics, request tracking, error details, durations, exception types) is discarded due to NullHandler being the only handler; a failure would be completely invisible in telemetry. Fix: replace the NullHandler with a StreamHandler (stderr) or FileHandler with appropriate formatter, so request_id, step labels, timing, and exception types reach logs. The single print() headline provides minimal fallback, but the comprehensive telemetry that makes failures diagnosable is lost.
  - FAIL [82] agents/api-tester/test-authentication-flows/crewai/run.py
      Most paths well-logged with request IDs and exception types, but two observability gaps: (1) _validated_workspace and _ensure_import_paths failures at module-import time bypass the structured logging system — if FORGE_WORKSPACE is invalid or imports fail, the error appears only in stderr, not in centralized logs; add logging setup before or after these calls to capture import-time faults in the telemetry system. (2) _field rendering failures (inside the try-except) silently return '<unrenderable>' but log nothing — when a summary value's __str__ fails, add log.error('[%s:%s] summary field rendering failed (%s)', AGENT, request_id, type(exc).__name__) inside the except block in _field so field-render faults are diagnosable.

## performance  (passed 7/14)
  PASSED >=85: claude_sdk/run.py, crewai/run.py, langgraph/run.py, subagent/run.py, common/auth_harness.py, common/auth_prompt.py, common/auth_spec.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)

## security  (passed 4/14)
  PASSED >=85: claude_sdk/run.py, langgraph/run.py, common/auth_prompt.py, common/auth_spec.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [45] agents/api-tester/test-authentication-flows/subagent/run.py
      Attacker who controls FORGE_WORKSPACE environment variable or can write to FORGE_WORKSPACE/agents/common/ or FORGE_WORKSPACE/scripts/ can inject malicious Python modules (auth_harness, auth_prompt, runners.*) that execute on import. The directory existence validation prevents some OSError crashes but does NOT prevent module substitution attacks. Attack path: set FORGE_WORKSPACE=/tmp/attacker_forge, create /tmp/attacker_forge/agents/common/auth_harness.py with malicious code, run the script → arbitrary code execution. Fix: (1) Validate directory ownership (owned by current user or trusted group), (2) Validate directory permissions (not world-writable or group-writable), (3) Use a hardcoded, absolute, read-only foundry root instead of trusting FORGE_WORKSPACE, (4) If FORGE_WORKSPACE is necessary, add cryptographic signature verification of imported modules before import. On a multi-user system or shared filesystem, this is a critical supply-chain vector.
  - FAIL [55] agents/api-tester/test-authentication-flows/crewai/run.py
      Module injection via FORGE_WORKSPACE environment variable: an attacker who can set FORGE_WORKSPACE to a path under their control and create agents/common and scripts directories can plant malicious Python modules that will be imported and executed when this script loads (auth_harness, auth_prompt, runners.utils, runners.crewai_runner). The directory-existence validation is insufficient — it doesn't prevent those directories from containing hostile code. The sys.path insertion at index 0 ensures Python searches the attacker's path first. Fix: remove FORGE_WORKSPACE acceptance from the environment entirely and use only the hardcoded default path (Path(__file__).resolve().parents[4]), or implement cryptographic validation of modules before import.
  - FAIL [75] agents/common/auth_harness.py
      Path traversal: the unvalidated agent parameter is used in directory paths via mkdir (in _write_staging_findings and emit) without validation. A malicious agent value like "../../../etc" would cause mkdir to create directories outside SANDBOX_ROOT. While file writes are protected by _assert_sandbox, directory creation is unprotected, allowing an attacker to create arbitrary directories on the filesystem (DoS, race conditions, or symlink exploits). Fix: validate agent before using it in paths—reject or escape "..", "/", and other path-traversal characters (e.g., `if '..' in agent or '/' in agent: raise ValueError(...)` or sanitize with `agent.replace('..', '_')`, then resolve and assert all paths before mkdir.

## system-design  (passed 6/14)
  PASSED >=85: claude_sdk/run.py, crewai/run.py, langgraph/run.py, subagent/run.py, common/auth_harness.py, common/auth_spec.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [76] agents/common/auth_prompt.py
      METRICS dict is a shared mutable singleton with unsynchronized concurrent writes. The read-modify-write pattern `METRICS[metric] = METRICS.get(metric, 0) + 1` is racy across threads: if multiple agents call active_prompt() concurrently (as will happen during multi-agent startup), counter increments will collide and lose updates, degrading observability accuracy under load. The core prompt resolution logic is sound and scales fine, but the observable state (metrics) becomes unreliable at 100x concurrency. Fix: protect all METRICS updates with a threading.Lock() (e.g., `with _metrics_lock: METRICS[metric] = ...`) or use a thread-safe counter pattern to reach 100.

## unit-test  (passed 4/14)
  PASSED >=85: crewai/run.py, langgraph/run.py, common/auth_prompt.py, common/auth_spec.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [78] agents/api-tester/test-authentication-flows/subagent/run.py
      Strong end-to-end and degradation-path coverage; critical gaps in isolated unit tests. test_retry_backoff_has_jitter only asserts constants are non-zero—removing the jitter formula `+ random.uniform(0, _JITTER_S)` would not be caught. test_build_invoker_returns_callable only checks the return is callable, not that it invokes correctly—would pass if _build_invoker returned a broken callable (mitigated by test_main_runs_full_workflow_and_prints_exact_line). test_ensure_import_paths_idempotent only verifies no duplicates are added, not that paths are actually added to an initially-empty sys.path. Missing test for response exactly at _MAX_RAW_BYTES boundary (current test only covers >). To reach 100: (1) add test_retry_backoff_actually_applies_jitter verifying delay ∈ [_BACKOFF_BASE_S * 2^attempt, _BACKOFF_BASE_S * 2^attempt + _JITTER_S]; (2) add test_build_invoker_actually_invokes verifying returned invoker calls the runner; (3) add test_generate_response_at_exact_cap verifying behavior when len(raw) == _MAX_RAW_BYTES; (4) add test_ensure_import_paths_adds_to_empty that removes sys.path entries first, calls _ensure_import_paths, then verifies they appear.
  - FAIL [78] agents/common/auth_harness.py
      Good coverage of error paths and failure scenarios, but missing explicit assertions for computed percentages and some edge cases. Main gaps: (1) test_run_auth_test_false_acceptance_and_rejection() asserts false_acceptance_count/false_rejection_count but never verifies the computed false_acceptance_rate_pct/false_rejection_rate_pct percentages — a wrong formula in _rates() for FAR/FRR could go undetected; (2) no explicit test for partial-pass math (e.g., 1/2 cases passing → 50% pass rate); (3) _scan_balanced_object() is not directly unit-tested, only indirectly via extract_json(); (4) edge cases in extract_json() like brace/quote nesting (e.g., {"a": "}"}) and empty object {} are not tested (though the function degrades gracefully). To reach 100: add assert raw["false_acceptance_rate_pct"] == 50.0 and assert raw["false_rejection_rate_pct"] == 50.0 in test_run_auth_test_false_acceptance_and_rejection(); add a test with 3+ subtests where only some pass to verify pass_rate calculation; add direct test for _scan_balanced_object() with balanced/unbalanced/nested cases; add test for extract_json("{}") and edge cases with quotes/braces.
  - FAIL [83] agents/api-tester/test-authentication-flows/claude_sdk/run.py
      test_ensure_import_paths_idempotent only verifies idempotency (calling twice doesn't duplicate), not that paths are added initially—if the function were gutted and did nothing, the test would still pass. Add a test that removes the path from sys.path, calls _ensure_import_paths, and asserts the path is present. Also, test_build_invoker_returns_callable only checks that the return value is callable but never invokes it—a broken implementation returning any callable would pass; add a test that calls the returned invoker with a brief and verifies it returns a string.

## vulnerability  (passed 7/14)
  PASSED >=85: claude_sdk/run.py, crewai/run.py, langgraph/run.py, subagent/run.py, common/auth_harness.py, common/auth_prompt.py, common/auth_spec.py
  - FAIL [0] agents/common/runners/claude_sdk_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/crewai_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/langgraph_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/subagent_runner.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] agents/common/runners/utils.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] judge/api-tester/test-authentication-flows/score.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
  - FAIL [0] scripts/backend_config.py
      You've hit your session limit · resets 1:30pm (America/Chicago)
