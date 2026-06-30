"""Auto-loaded by Python at startup when this directory is on PYTHONPATH. If request recording is
enabled (FORGE_RECORD_REQUESTS=1), it installs the urlopen wrapper BEFORE the agent harness runs,
so every outbound API call is captured. No-op otherwise. Placed in its own dir so it is only active
for executor subprocesses that opt in via PYTHONPATH."""
import os
import sys

if os.environ.get("FORGE_RECORD_REQUESTS"):
    ws = os.environ.get("FORGE_WORKSPACE")
    if ws:
        sys.path.insert(0, os.path.join(ws, "agents", "common"))
    try:
        import request_recorder
        request_recorder.install()
    except Exception:  # noqa: BLE001 — recording must never break an executor
        pass
