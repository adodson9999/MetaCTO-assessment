#!/usr/bin/env python3
# Used by: shared — debate gate used by EVERY agent's _*_gate_authoring.py.
"""
Debate-gate bookkeeping scaffold.

The four interpretive readings (Literal, Adversarial, Intent, Ultron) are
produced by the model — this script does NOT decide consensus. Its job is to
make the gate impossible to skip: it tracks the current line, accumulates the
debate trail, refuses to write a line until a single agreed interpretation has
been recorded, and emits both output files:

    agent_built_prompts/<agent>.prompt.md   (clean approved lines only)
    agent_built_prompts/<agent>.debate.md   (full trail, every loop iteration)

See references/debate-gate.md for the panel and the consensus rule.

Typical use (driven by the model, one line at a time):

    g = DebateGate("langgraph", out_dir)
    # loop until consensus, asking the user on any disagreement:
    g.record_round(line, readings={
        "literal": "...", "adversarial": "...",
        "intent": "...", "ultron": "..."},
        consensus=None)                      # None => not yet agreed; will not write
    ...
    g.commit_line(final_line, agreed_interpretation="...")  # writes only on consensus
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

PANEL = ("literal", "adversarial", "intent", "ultron")


class GateNotConverged(Exception):
    pass


class DebateGate:
    def __init__(self, agent: str, out_dir: str | Path, group: str | None = None):
        self.agent = agent
        self.out = Path(out_dir)
        # All frameworks of one build live together in a single build folder,
        # nested by position then workflow:
        #   agent_built_prompts/<position>/<workflow>/<framework>.{prompt,debate}.md
        # `group` is that relative path, e.g. "api-tester/validate-request-payloads"
        # (position = the role, e.g. "api-tester"; workflow = "validate-request-payloads").
        # group may be a single segment or a nested path; if None, files are flat (back-compat).
        self.build_dir = self.out / group if group else self.out
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.prompt_path = self.build_dir / f"{agent}.prompt.md"
        self.debate_path = self.build_dir / f"{agent}.debate.md"
        self._committed: list[str] = []
        self._trail: list[dict] = []
        if not self.prompt_path.exists():
            self.prompt_path.write_text(f"# {agent} — approved prompt (debate-gated)\n\n")
        if not self.debate_path.exists():
            self.debate_path.write_text(f"# {agent} — debate trail\n\n")

    def record_round(self, line: str, readings: dict, consensus: str | None) -> None:
        """Record one debate round for a candidate line.

        readings: each of PANEL -> the interpretation that member raised.
        consensus: the single agreed interpretation, or None if not yet agreed.
        """
        missing = [m for m in PANEL if m not in readings]
        if missing:
            raise ValueError(f"missing panel readings: {missing}")
        self._trail.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "line": line,
            "readings": {m: readings[m] for m in PANEL},
            "consensus": consensus,
        })
        self._flush_trail()

    def commit_line(self, line: str, agreed_interpretation: str) -> None:
        """Write a line to the clean prompt. Only call when all four panel
        members agree on exactly one interpretation."""
        if not agreed_interpretation:
            raise GateNotConverged(
                "Refusing to write line: no single agreed interpretation. "
                "Halt and ask the user, then re-run the panel."
            )
        # Require that the most recent recorded round for this line reached consensus.
        last_for_line = [r for r in self._trail if r["line"] == line]
        if not last_for_line or last_for_line[-1]["consensus"] is None:
            raise GateNotConverged(
                "Refusing to write line: last recorded round did not reach consensus."
            )
        self._committed.append(line)
        with open(self.prompt_path, "a") as f:
            f.write(line.rstrip() + "\n")
        with open(self.debate_path, "a") as f:
            f.write(f"\n## RESOLVED: {line.strip()}\n")
            f.write(f"- single interpretation: {agreed_interpretation}\n")

    def _flush_trail(self) -> None:
        with open(self.debate_path, "a") as f:
            r = self._trail[-1]
            f.write(f"\n### candidate @ {r['ts']}\n")
            f.write(f"> {r['line'].strip()}\n\n")
            for m in PANEL:
                f.write(f"- **{m}**: {r['readings'][m]}\n")
            status = "CONSENSUS" if r["consensus"] else "NO CONSENSUS — halt & ask user"
            f.write(f"- _status_: {status}\n")

    def summary(self) -> dict:
        return {
            "agent": self.agent,
            "committed_lines": len(self._committed),
            "rounds": len(self._trail),
            "prompt": str(self.prompt_path),
            "debate": str(self.debate_path),
        }


if __name__ == "__main__":
    # tiny self-test of the bookkeeping (no model calls)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        g = DebateGate("demo", d)
        g.record_round("Maximize task success.", {
            "literal": "increase a number called task success",
            "adversarial": "could cut corners to inflate the number",
            "intent": "do the task well per the spec",
            "ultron": "remove all tasks so none can fail => trivially 'maximized'",
        }, consensus=None)
        try:
            g.commit_line("Maximize task success.", "")
        except GateNotConverged as e:
            print("correctly blocked:", e)
        g.record_round("Maximize exact-match accuracy on the held-out set.", {
            "literal": "the held-out exact-match fraction",
            "adversarial": "same",
            "intent": "same",
            "ultron": "same (no destructive extreme survives)",
        }, consensus="held-out exact-match accuracy fraction")
        g.commit_line("Maximize exact-match accuracy on the held-out set.",
                      "held-out exact-match accuracy fraction")
        print(json.dumps(g.summary(), indent=2))
