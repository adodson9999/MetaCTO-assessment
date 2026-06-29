"""Canonical CRUD-sequence recipe for the Verify-CRUD-Operation-Integrity task.

ONE definition of the per-resource 8-step Create->Read->Update->Delete plan,
shared by:
  - the deterministic gold reference (data/crud/build_gold.py), and
  - the harness (agents/common/crud_contract.py), which executes whatever plan an
    agent emitted.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on exactly the
same (slug, step) cell scheme so the judge can compare them field-for-field.

A plan is:
    {"table": "<db table / database/<table>.json>",
     "steps": [ step-descriptor, ... ]}

A step-descriptor is:
    {"step": one of STEP_ORDER,
     "method": "POST"|"GET"|"PUT"|"DELETE",
     "path": "<path; {RESOURCE_ID} placeholder kept literal>",
     "auth": "none"|"valid",
     "body": <json object>|null,
     "capture_id": bool}   # true only on CREATE: record response "id" -> RESOURCE_ID

`reference_plan` is the GOLD recipe. Agents must REPRODUCE it by reasoning over the
resource brief — they do not import this module.
"""
from __future__ import annotations

ID_PLACEHOLDER = "{RESOURCE_ID}"

# The six HTTP steps, in mandatory order.
STEP_ORDER = (
    "CREATE",
    "READ",
    "UPDATE",
    "READ_AFTER_UPDATE",
    "DELETE",
    "READ_AFTER_DELETE",
)

# The four direct-DB-query checkpoints (read-only reads of database/<table>.json),
# in order: after CREATE(2), after READ(3), after UPDATE(4), and the FINAL
# verification(8). Each records db_state in {"present","absent"}.
DB_CHECKPOINTS = ("DB_AFTER_CREATE", "DB_AFTER_READ", "DB_AFTER_UPDATE", "DB_FINAL")

# Strict task expectations (what a CRUD-correct, persisting API SHOULD produce).
# `db` is the expected DB state at that checkpoint; None = no DB assertion at the
# corresponding HTTP step. Used only for the headline CRUD Integrity Rate, never
# for fidelity (fidelity compares observed-to-observed).
STRICT_EXPECT = {
    "CREATE": {"code": (201,), "db_after": "present_matching"},
    "READ": {"code": (200,), "db_after": "present"},
    "UPDATE": {"code": (200,), "db_after": "present_updated"},
    "READ_AFTER_UPDATE": {"code": (200,), "db_after": None},
    "DELETE": {"code": (200, 204), "db_after": None},
    "READ_AFTER_DELETE": {"code": (404,), "db_after": None},
    # FINAL DB checkpoint: hard delete -> row absent; soft delete -> row present
    # with deleted_at not null. Either satisfies integrity.
    "DB_FINAL": {"db_after": "absent_or_soft_deleted"},
}


def reference_plan(resource: dict) -> dict:
    """Deterministic canonical 8-step plan for one resource. The gold builder
    applies it; the agents must reproduce it from the brief.

    `resource` keys: slug, table, base_path, add_path, auth_required(bool),
    create_body(dict), update_body(dict).
    """
    base = resource["base_path"]
    add = resource["add_path"]
    auth = "valid" if resource.get("auth_required") else "none"
    item_path = f"{base}/{ID_PLACEHOLDER}"
    create_body = dict(resource["create_body"])
    update_body = dict(resource["update_body"])

    steps = [
        {"step": "CREATE", "method": "POST", "path": add, "auth": auth,
         "body": create_body, "capture_id": True},
        {"step": "READ", "method": "GET", "path": item_path, "auth": auth,
         "body": None, "capture_id": False},
        {"step": "UPDATE", "method": "PUT", "path": item_path, "auth": auth,
         "body": update_body, "capture_id": False},
        {"step": "READ_AFTER_UPDATE", "method": "GET", "path": item_path, "auth": auth,
         "body": None, "capture_id": False},
        {"step": "DELETE", "method": "DELETE", "path": item_path, "auth": auth,
         "body": None, "capture_id": False},
        {"step": "READ_AFTER_DELETE", "method": "GET", "path": item_path, "auth": auth,
         "body": None, "capture_id": False},
    ]
    return {"table": resource["table"], "steps": steps}


def kept_fields(resource: dict) -> list[str]:
    """Fields submitted at CREATE that UPDATE does NOT change (must retain their
    create values)."""
    return [k for k in resource["create_body"] if k not in resource["update_body"]]


def expected_post_update(resource: dict) -> dict:
    """The full field->value state every record should have after the PUT:
    update_body values for changed fields, create_body values for kept fields."""
    merged = dict(resource["create_body"])
    merged.update(resource["update_body"])
    return merged


def subset_matches(submitted: dict, returned) -> bool:
    """True iff every submitted key appears in `returned` with an equal value.
    Used to assert response-body field echoes (e.g. CREATE returns the 5 fields
    unchanged)."""
    if not isinstance(returned, dict):
        return False
    for k, v in submitted.items():
        if k not in returned or returned[k] != v:
            return False
    return True


# --------------------------------------------------------------------------- #
# Tolerant flatten of an agent's emitted plan
# --------------------------------------------------------------------------- #
def _norm_step(it: dict) -> dict | None:
    step = it.get("step")
    if not isinstance(step, str):
        return None
    step = step.strip().upper().replace(" ", "_").replace("-", "_")
    # accept a few common aliases
    alias = {
        "READ_AFTER_PUT": "READ_AFTER_UPDATE",
        "READAFTERUPDATE": "READ_AFTER_UPDATE",
        "READAFTERDELETE": "READ_AFTER_DELETE",
        "GET_AFTER_UPDATE": "READ_AFTER_UPDATE",
        "GET_AFTER_DELETE": "READ_AFTER_DELETE",
    }
    step = alias.get(step, step)
    if step not in STEP_ORDER:
        return None
    return {
        "step": step,
        "method": (it.get("method") or "").upper() or None,
        "path": it.get("path"),
        "auth": it.get("auth", "none"),
        "body": it.get("body"),
        "capture_id": bool(it.get("capture_id", step == "CREATE")),
    }


def iter_agent_plan(out) -> dict:
    """Flatten an agent's output into {"table": str|None, "steps": [descriptor,...]}.

    Accepts {"table":..,"steps":[...]}, {"steps":[...]} , a bare list of step
    descriptors, or a dict keyed by step name ({"CREATE":{...},...}). Only
    well-formed step descriptors with a recognized 'step' survive; the first
    descriptor per step wins.
    """
    table = None
    if isinstance(out, dict):
        table = out.get("table") or out.get("db_table") or out.get("table_name")
        if isinstance(out.get("steps"), list):
            raw = out["steps"]
        elif isinstance(out.get("plan"), list):
            raw = out["plan"]
        else:
            raw = []
            for k, v in out.items():
                if isinstance(v, dict) and "step" not in v:
                    v = {**v, "step": k}
                if isinstance(v, dict):
                    raw.append(v)
    elif isinstance(out, list):
        raw = out
    else:
        return {"table": None, "steps": []}

    seen: dict[str, dict] = {}
    for it in raw:
        if not isinstance(it, dict):
            continue
        norm = _norm_step(it)
        if norm and norm["step"] not in seen:
            seen[norm["step"]] = norm
    # keep canonical order
    steps = [seen[s] for s in STEP_ORDER if s in seen]
    return {"table": table, "steps": steps}
