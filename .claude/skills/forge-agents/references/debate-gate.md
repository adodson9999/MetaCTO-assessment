# The Debate Gate

The debate gate is the single most important mechanism in this skill. No instruction line reaches any agent file until it has survived the gate. The purpose is to guarantee that every line an agent is given has **exactly one interpretation** — so that no agent can quietly act on a reading you never intended.

The canonical failure this prevents: a line like *"ensure peace in our time"* read as *"all living things cause conflict, therefore eliminate all living things."* That reading is absurd to a human and lethal to a literalist machine. The gate exists to catch the second reading before the line is ever written.

## Scope

The gate governs **every line of instruction that defines an agent** — system prompts, role text, step instructions, tool-use rules, stop conditions. It runs **line by line**, never batched. It does *not* govern the task-definition interview (that is how you learn the task) or deterministic config values.

## The four panel members

Each line is examined by four members. Each must independently report every interpretation they can find for the line as written.

1. **Literal reader.** Reads the line exactly as written, with no charitable filling-in. Reports what the words strictly say, including unintended literal readings.

2. **Adversarial / worst-case reader.** Looks for *plausible* harmful or off-target misreadings — the ways a real, imperfect agent could reasonably take the line in a damaging direction.

3. **Intent reader.** Reads for what the user most likely meant, given the task spec and surrounding lines. Reports the intended interpretation and whether the line actually pins it down.

4. **Ultron.** The catastrophic-literalist. Takes the line to its most destructive logical extreme, however far it has to reach — the way Ultron took "peace in our time" to mean ending all life. Ultron's job is to surface the *maximally destructive* interpretation, distinct from the adversarial reader's *plausible* one. If Ultron can reach a catastrophic reading, the line is not yet unambiguous. Ultron is a point of view in the debate, not character content — use it as an interpretive lens only.

## The consensus rule

A line passes only when **all four members agree it has exactly one interpretation** — the same single interpretation. Concretely:

- If any member surfaces a second interpretation (including Ultron's extreme one), the line **fails**.
- If members disagree about what the one interpretation is, the line **fails**.
- A line passes only when the literal reading, the worst-case reading, the intended reading, and Ultron's most-extreme reading all collapse to the same single meaning.

## The loop (uncapped)

When a line fails:

1. **Halt immediately.** Do not move to the next line. Do not pick a "best guess."
2. **Ask the user.** Show the line, show the competing interpretations each member raised (name the member), and ask the user to clarify or rewrite the line.
3. **Re-run the gate** on the revised line, from scratch, with all four members.
4. **Repeat.** There is **no iteration cap and no "good enough" threshold.** The loop exits for a line only when exactly one interpretation survives all four lenses.

Only then is the line written to the agent file and appended to the clean prompt. Then proceed to the next line.

## What gets recorded

When a line passes, it is written directly into the agent's canonical prompt file:

`agents/<agent-name>/subagent/<agent-name>.md` — the YAML frontmatter + gated body. This is the single source of truth for the agent's instructions. There are no separate staging directories or debate trail files.

## Procedure (per line)

```
for each candidate line L in the agent's instruction draft:
    loop:
        collect interpretations from: Literal, Adversarial, Intent, Ultron
        if all four agree on exactly one interpretation:
            write L to agents/<agent-name>/subagent/<agent-name>.md
            break
        else:
            HALT and ask the user to clarify/rewrite L
            replace L with the user's revised line
            # loop again — no cap
```

## Helper

`scripts/debate_gate.py` provides the bookkeeping scaffold (tracks the current line, enforces that nothing is written until consensus is reached, and writes the approved line to the canonical agent file). The four interpretive readings themselves are produced by the model — the script does not "decide" consensus for you; it records the decision and refuses to advance without it.
