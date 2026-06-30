# Universal Agent Authoring & Update Standard
### (Constitution + Flow amendment — applies to EVERY agent in the foundry)

These **foundry-wide governing rules** apply to any agent built by **forge-agents** or
modified by **update-agent**, across all four frameworks (LangGraph, CrewAI, Claude
Code subagent, Claude Agent SDK) and the judge. They generalize ten authoring
decisions into reusable invariants.

It adds one new invariant on top of those ten: **no two agents may test the same
thing** — enforced by a hard-halting MECE gate.

> **Location.** This is the canonical copy at
> `agent-foundry/references/agent-authoring-standard.md`. Every agent's system prompt
> must reference this path (see the compliance clause in
> `references/agent-standard-compliance-clause.md`).
>
> **How to wire this in (insertion points).** Append **Part A** (Articles G1–G11) to
> `forge-agents/references/constitution.md`; add **Part B** to both the `update-agent`
> `references/flow.md` and the forge-agents flow; add `scripts/mece_gate.py` (Part C)
> beside `code_review_gate.py` and wire it into the `update_agent.py` completion
> contract. These edits are listed, not auto-applied — the constitution/flow live in
> the skills, which are read-only from this session.

---

## Generalization map — every original answer → general rule

| # | Decision (what you chose) | Generalized article |
|---|---|---|
| 1 | Spell out every detail like to a novice; agent does testing+reporting, not test-case fabrication; log every step | **G1** role, **G2** explicitness, **G4** logging |
| 2 | Stay JSON-only; the JSON carries plan + execution + log + report; harness executes | **G1** specifier-not-executor |
| 3 | Top-level grouped by endpoint, self-describing cases | **G3** standardized self-describing envelope |
| 4 | No fixed step count — maximally atomic, every step logged | **G4** atomic fully-logged steps |
| 5 | `expected_class` primary + `also_accept` array | **G5** primary + also_accept expectations |
| 6 | Full body assertions incl. rotation + negative (no token on failure) | **G6** assert success, state-change, and leak-nothing-on-failure |
| 7 | Closed credential-recipe vocabulary, every variant enumerated | **G7** closed input-recipe vocabulary |
| 8 | Broadest coverage: field-omission matrix everywhere + tamper on every credential call, count derived from the brief | **G8** deterministic exhaustive coverage generator |
| 9 | Layered guardrail, fail closed, named handoff to sibling agents | **G9** declared lane + fail closed + named handoff |
| 10 | Byte-stable golden + schema + full coverage + lane/security tests | **G10** per-agent regression safety net |
| — | *(new caveat)* no two agents test the same thing | **G11** foundry MECE invariant |

---

## Part A — Constitution articles (governing invariants)

**G1 — Specifier, not executor.** Every agent emits exactly **one structured artifact**
(a single JSON object) that is a *complete plan + execution + logging + report
contract*. The agent performs **no network calls, no logins, no side effects**, and
confines all file access to `FORGE_WORKSPACE`. It never fabricates real artifacts
(tokens, fixtures, payloads); it only **names recipes** for a separate deterministic
harness to build and execute. *Interpretation: the agent's job is to specify testing
and reporting exhaustively; the harness is the only thing that touches the world.*

**G2 — Maximum explicitness, zero ambiguity.** Instructions are authored so any model
or reader resolves them exactly one way; every rule carries a concrete example. The
four-member debate gate must collapse each line to a single interpretation before it
is written. *No "obvious" step is left implicit.*

**G3 — Self-describing, standardized envelope.** Output is grouped by the natural
**unit of work** under a fixed top-level shape, and each case is readable end-to-end
in one place:

```json
{
  "meta": { "agent": "...", "lane": "...", "surface": [ ... ] },
  "units": [ { "unit": "...", "target": { ... }, "cases": [ { ...self-describing case... } ] } ],
  "out_of_scope": { "<adjacent concern>": "<owning sibling agent>" },
  "report_spec": { "metrics": [ ... ], "per_case": [ "verdict" ], "output": "results/runs/<run-id>/<agent>.json", "log_output": "results/runs/<run-id>/steps.jsonl" }
}
```

**G4 — Atomic, fully-logged steps.** Each case decomposes into a **variable-length**
array of the **most atomic steps possible** — no fixed count. Every step carries
`"log": true`; the harness fills `observed`, `verdict`, `ts` as it executes and writes
one log line per step. *Log every step, no exceptions; leave no room for
misinterpretation.*

**G5 — Expectations as primary + also_accept.** Every expected outcome is a single
**primary** expectation plus an explicit **`also_accept`** array of other acceptable
outcomes (often empty). Verdict passes **iff** `observed == primary` OR
`observed ∈ also_accept`. *No hidden either/or; the acceptable set is always
enumerated.*

**G6 — Assert success, state-change, and leak-nothing-on-failure.** Positive cases
assert the full success contract, **including state changes** where they exist
(rotation, idempotency, ordering, pagination cursors, etc.). Negative cases assert the
failure outcome **and** that no protected artifact or unintended side effect leaks
(e.g., no token/record/resource returned or mutated). *Failure must fail closed at the
assertion level too.*

**G7 — Closed input-recipe vocabulary.** Each agent defines a **closed, documented**
vocabulary of input recipes (`kind` + `params`). The agent may use **only** those
kinds; it never invents one. Every variant is enumerated with explicit params.

**G8 — Deterministic, exhaustive coverage generator.** The case set is a
**deterministic function of the target's documented surface** (read from the
brief/spec), not a hand-picked list. The agent enumerates **every applicable variant
for every unit** — e.g., the per-field omission matrix plus the empty case, plus each
applicable negative/tamper variant for every credential-bearing call. Fixed counts
("exactly N") are replaced by "exactly the computed set for this surface — none
omitted, no extras."

**G9 — Declared lane, fail closed, named handoff.** Every agent **declares its lane**
and emits only in-lane output. On out-of-lane input it emits a **single error
sentinel and nothing else** — fail closed: non-zero exit, no results written, no
partial artifact. It names, in `out_of_scope`, the **sibling agent that owns each
adjacent concern**. Enforced in three layers: the system prompt, **every framework's
`run.py` validator**, and a unit test.

**G10 — Per-agent regression safety net.** Every agent ships, as its regression
baseline: (a) a **byte-stable golden** for a fixed canonical brief with deterministic
key + case ordering; (b) **JSON-Schema** shape validation of every case; (c) a **full
deterministic coverage** assertion (count == computed, none missing, no extras); and
(d) **lane + security** assertions — all as `pytest`, stored at
`tests/golden/<group>/<name>/golden.json` and `tests/<group>/<name>/`.

**G11 — MECE across the foundry: no two agents test the same thing.** *(the caveat)*
- **Mutual exclusivity:** the set of **canonical case-identities** owned by any two
  agents must be **disjoint** — no case-identity may appear in more than one agent.
- **Collective exhaustiveness:** the **union** of all agents' owned case-identities
  must cover the **whole declared test surface**; any deliberate gap is recorded as
  `out_of_scope` owned-by-nobody = `needs_new_agent` (never a silent hole).
- **Canonical case-identity** = a normalized key the family defines, e.g.
  `sha1(method + path + recipe.kind + sorted(params) + assertion-signature)`; two
  cases with the same identity are "the same thing."
- Every agent declares its lane + owned identities in a **coverage manifest**
  (`agent-foundry/registry/coverage-manifest.json`, refreshed per agent).
- Enforced by a foundry-level **MECE gate that HARD-HALTS** on any overlap (one
  identity in two agents) or gap — see Part B. *Interpretation: lanes are not just
  declared, they are proven disjoint and complete on every build/update.*

---

## Part B — Flow amendment (where the new gate runs)

Apply alongside the existing gates (debate → determinism → 95 quality floor → dynamic
code-review ≥85 → `/analyze` → re-judge + tournament → verify). Add:

**Authoring pass (forge-agents create + update-agent re-author).** When writing or
regenerating any agent's prompt across all four frameworks + the judge, apply Articles
G1–G10. The debate gate enforces G2; the determinism check enforces G4/G8 stability;
the 95 floor + code-review ≥85 apply to every `run.py` validator (G9) and `score.py`.
Add to every agent's system prompt, beside the existing self-awareness clause, the
**standard-compliance / ownership clause** (see
`references/agent-standard-compliance-clause.md`): it cites this standard by path,
states the agent owns a unique, non-overlapping slice of the test surface, and that it
must never duplicate another agent's case-identity.

**New gate — MECE / no-overlap (G11), runs after re-judge, before completion.**
1. Build/refresh the coverage manifest for **every affected agent** by computing its
   owned case-identity set from its emitted plan on the canonical brief.
2. **Pairwise-disjoint check across ALL agents** in `agent-foundry/agents/**` (not just
   the affected ones): any case-identity present in two agents **hard-halts**, naming
   both agents and the duplicated identity.
3. **Coverage check:** the union must cover the declared surface; any gap **hard-halts**
   unless explicitly recorded as `needs_new_agent`.
4. **Handoff-consistency check (G9 × G11):** every `out_of_scope` handoff must resolve
   to a **real sibling agent that actually owns** those identities in the manifest; a
   handoff to a non-owner, or to an identity nobody owns, **hard-halts**.
5. **Reference check (this standard):** every affected agent's system prompt must cite
   `references/agent-authoring-standard.md`; a missing reference **hard-halts**.
6. Write a receipt `results/_global/mece-<TS>.json` and record the run to EverOS
   memory (record the agent set, overlaps found, gaps found, fixes).
7. **No-bypass completion contract:** the create/update may **not** complete unless the
   MECE receipt exists with `status: pass` and its agent set **equals**
   `agent-foundry/agents/**`. This runs **in addition to** the code-review gate and the
   regression gate — **all three must pass, for every affected agent**, looping
   (rewrite → re-run) until green.

---

## Part C — Manifest + gate spec (concrete)

**Coverage manifest** (`agent-foundry/registry/coverage-manifest.json`):

```json
{
  "agents": {
    "<group>/<agent-a>": {
      "lane": "<one-line description of agent-a's exclusive slice>",
      "owns": ["a1b2…","c3d4…", "..."],
      "handoffs": {
        "<adjacent concern 1>": "<group>/<agent-b>",
        "<adjacent concern 2>": "<group>/<agent-c>"
      }
    },
    "<group>/<agent-b>": { "lane": "<agent-b's exclusive slice>", "owns": ["e5f6…"] }
  }
}
```

**`scripts/mece_gate.py`** (sketch — same shape as `code_review_gate.py`):

```python
def canonical_identity(case) -> str:
    sig = f"{case['method']}|{case['path']}|{case['recipe']['kind']}|" \
          f"{sorted(case['recipe'].get('params',{}).items())}|{assertion_sig(case)}"
    return sha1(sig)

def mece_gate(foundry) -> Receipt:
    owns = {agent: identities_from_plan(agent) for agent in discover_agents(foundry)}
    overlaps = [(a, b, i) for a, b in pairs(owns) for i in owns[a] & owns[b]]   # disjoint
    gaps = declared_surface(foundry) - set().union(*owns.values())               # exhaustive
    bad_handoffs = unresolved_handoffs(owns)                                     # G9×G11
    missing_ref = agents_without_standard_reference(foundry)                     # this standard
    status = "pass" if not (overlaps or gaps or bad_handoffs or missing_ref) else "fail"
    write_receipt(foundry, status, owns, overlaps, gaps, bad_handoffs, missing_ref)
    if status != "pass":
        hard_halt(overlaps, gaps, bad_handoffs, missing_ref)
    return receipt
```

`discover_agents()` is **dynamic** (whatever is in `agent-foundry/agents/**` at run
time, however many); the completion contract requires the receipt's agent set to
**equal** that folder — a missing agent, an empty set, or a receipt ≠ folder fails the
update, exactly like the code-review no-bypass rule.

---

## Worked read-through (generic example)

- **G3/G8:** Agent A's units come from its documented surface; its computed case set is
  the deterministic enumeration of every applicable variant per unit (e.g. the
  input-omission matrix + the empty case + each negative/tamper variant), sized from
  the brief — not a hand-picked count.
- **G9/G11:** Agent A declares its lane, fails closed on out-of-lane input, and hands
  each adjacent concern off to the sibling that owns it (Agent B, Agent C) — whose
  identity sets are **disjoint** from Agent A's, so the MECE gate sees no overlap and
  consistent handoffs. If Agent B ever emitted a case-identity that Agent A already
  owns, the gate **hard-halts**, naming both agents and the shared identity. *That is
  the caveat, enforced.*
