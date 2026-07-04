# Code-review notes — api-tester/test-authentication-flows — 20260701T023900
threshold=85 status=fail min_rating=30

## adversarial-input  (passed 0/1)
  - FAIL [30] scripts/backend_config.py
      Input: provider='auto' in config.toml or FORGE_PROVIDER environment variable, combined with a hostname that causes socket.gethostbyname() to block indefinitely (either a slow-resolving domain, a malformed hostname triggering DNS timeouts without raising an exception, or a crafted input that exploits DNS implementation bugs). Failure: socket.gethostbyname(host) in _is_local_host() hangs indefinitely during _auto_detect(), causing the entire program startup to hang and become unresponsive. The try/except (OSError, ValueError) catches failures but not hangs. Secondary issue: tomllib.load(f) reads entire config.toml into memory with no size limit; a 10GB+ file exhausts memory on startup. Fix for DNS hang: replace socket.gethostbyname(host) with socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM, timeout=0.4), enforcing a bounded timeout on all DNS lookups. Fix for config exhaustion: check file size before loading (reject files > 1MB) via os.path.getsize(path) before opening.

## api-contract  (passed 1/1)
  PASSED >=85: scripts/backend_config.py

## chaos-engineering  (passed 0/1)
  - FAIL [67] scripts/backend_config.py
      The _auto_detect() function has a fallback that doesn't verify reachability. Injected fault: all backends are down at startup with provider='auto' (or not in Claude Code session with ollama down) → _auto_detect() probes each backend via _reachable(), finds all unreachable, but then returns 'ollama' anyway without re-verifying it → resolve() succeeds and returns an unreachable provider → all downstream requests fail when actually used. No graceful degradation and no recovery without manual restart. The cascading failure is silent: the system appears to have a valid configuration but doesn't. Fix: probe ollama one final time before the fallback return, or raise an exception if no backends are reachable (let the caller know resolution failed, don't return a provider you couldn't verify).

## concurrency  (passed 1/1)
  PASSED >=85: scripts/backend_config.py

## data-integrity  (passed 1/1)
  PASSED >=85: scripts/backend_config.py

## device-stack  (passed 0/1)
  - FAIL [55] scripts/backend_config.py
      socket.gethostbyname() in _is_local_host() is a blocking DNS call with no timeout. If the system resolver is slow, misconfigured, or hangs, or if the process is backgrounded/suspended while the call is pending, the entire foundry will block indefinitely at startup when provider='auto' triggers _auto_detect(). This occurs under normal OS conditions (resolver hangs, process backgrounding). Fix: wrap the DNS call with a timeout using socket.setdefaulttimeout() before calling gethostbyname() and restore it after, or use socket.getaddrinfo() with manual timeout handling. The default numeric-IP config avoids this, but user-supplied FORGE_* env overrides with hostnames would trigger it.

## error-handling-resilience  (passed 1/1)
  PASSED >=85: scripts/backend_config.py

## logic-error  (passed 1/1)
  PASSED >=85: scripts/backend_config.py

## maintainability  (passed 0/1)
  - FAIL [72] scripts/backend_config.py
      VALID_PROVIDERS is defined but never used, creating a maintenance hazard. When a future engineer adds a new backend to _PROVIDER_SPECS, they won't know whether to also update VALID_PROVIDERS (which is unused and therefore easy to overlook). The provider list also appears hardcoded in the resolve() error message, so changes to the provider ecosystem must be synchronized across multiple places. Cost: silent drift where _PROVIDER_SPECS and VALID_PROVIDERS diverge. Fix: either remove VALID_PROVIDERS if it's unused, or derive it as `VALID_PROVIDERS = tuple(_PROVIDER_SPECS.keys()) + ('auto',)` and use it in the validation check in resolve() so there is one source of truth.

## math-correctness  (passed 1/1)
  PASSED >=85: scripts/backend_config.py

## memory-resource  (passed 1/1)
  PASSED >=85: scripts/backend_config.py

## minimalist  (passed 1/1)
  PASSED >=85: scripts/backend_config.py

## network  (passed 0/1)
  - FAIL [70] scripts/backend_config.py
      socket.gethostbyname() in _is_local_host() has no explicit timeout and will block for the system DNS timeout (typically 15+ seconds) if the hostname is slow or unresolvable, stalling the entire startup via _auto_detect(). Fix: wrap gethostbyname() with socket.settimeout() before the call, or use socket.getaddrinfo() with an explicit timeout parameter. Secondary issue: _reachable() retries with no exponential backoff (minor for local TCP probes, add jitter between the two attempts). Tertiary: defaulting to 'ollama' when all backends are unreachable creates a weak fallback; better strategy: return None or raise an error if no backend is reachable, forcing the caller to handle unavailability explicitly rather than proceeding with a known-down backend.

## observability  (passed 0/1)
  - FAIL [60] scripts/backend_config.py
      _reachable() swallows OSError on each probe attempt with no logging, making it invisible which backends failed and why (connection refused? timeout? DNS? transient network blip?). When auto-detect falls back, the WARNING 'found no reachable backend' tells you it happened, but not which backends were tried or why each failed — that's a serious gap for diagnosing startup failures. Add log.debug("backend %s:%d unreachable after %d attempts: %s", host, port, _PROBE_ATTEMPTS, e) before the final return False. Also: _is_local_host() silently swallows OSError from gethostbyname(), so misconfigured hostnames fail diagnostically invisible — add log.debug("cannot resolve hostname %r: %s", host, e) in the OSError handler. These are startup-critical paths; their failures must be visible.

## performance  (passed 1/1)
  PASSED >=85: scripts/backend_config.py

## security  (passed 0/1)
  - FAIL [80] scripts/backend_config.py
      Path traversal via FORGE_WORKSPACE env var: an attacker who can set this env var could specify a path like `/etc` to read arbitrary `config.toml` files on the system. Downstream validation (provider whitelist, `_is_local_host()` SSRF containment) limits the practical impact, but path traversal should be prevented by validating that workspace doesn't escape the expected foundry root—reject `..` sequences or use `Path.resolve()` with bounds checking.

## system-design  (passed 1/1)
  PASSED >=85: scripts/backend_config.py

## unit-test  (passed 0/1)
  - FAIL [75] scripts/backend_config.py
      Tests cover config layering, resilience, SSRF containment, and basic auto-detect behavior, but miss critical paths: (1) _reachable has no test for successful TCP connection (only False cases); add test monkeypatching socket.create_connection to return a listening connection and assert _reachable returns True. (2) resolve() is never called with provider='auto' in config; add test that writes config.toml with provider="auto" and calls resolve(), verifying it returns a correct backend spec. (3) Preference order in _auto_detect is not verified when multiple backends are reachable; add test where _reachable returns True for both 'claude-cli' and 'claude-haiku' URLs and assert _auto_detect returns 'claude-cli' first (not 'claude-haiku' or 'ollama'). (4) Non-Claude-session behavior (when _is_claude_code_session=False) is never tested; add test that monkeypatches _is_claude_code_session to False and assert _auto_detect only tries ['ollama'], not the 3-item preference list. These gaps allow preference-order bugs, integration bugs, and the success path of _reachable to slip through undetected.

## vulnerability  (passed 0/1)
  - FAIL [58] scripts/backend_config.py
      TOCTOU-based SSRF bypass in _reachable(). Vulnerability class: Time-of-Check-Time-of-Use race condition in network request. Source-to-sink path: attacker-controlled base_url (via FORGE_* env vars or config.toml) → _is_local_host() resolves hostname to check if local (passes if DNS returns 127.0.0.1) → _reachable() then re-resolves hostname via socket.create_connection() (attacker can rebind DNS to return public IP during this window) → connects to arbitrary host. Exploit requires DNS rebinding or attacker-controlled DNS. Real problem with limited impact (TCP SYN only, not full HTTP exfiltration). Fix: resolve hostname once, verify result is local, then use the resolved IP address (not re-resolve the hostname) when calling socket.create_connection(): after _is_local_host() passes, replace socket.create_connection((host, port)) with ip = ipaddress.ip_address(socket.gethostbyname(host)); socket.create_connection((str(ip), port)). This ensures the connection target is identical to the checked target, closing the TOCTOU window.
