# Principal Architect Protocol

**Trigger:** "invoke the principal architect" / "invoke the PA"

When triggered, work through every step below. Do not skip steps.

---

## The Five Principles

These combine Rob Pike's engineering rules (from the creators of Unix and Go) with Factory.ai's agent readiness research into one coherent framework. Keep them in mind throughout every review.

1. **Fix the environment, not the agent.** (Pike: "Data dominates.") Good data structures make algorithms self-evident. Good repo structure makes agent output self-evident. If a sub-agent keeps producing bad work, the repo is the problem. Check: AGENTS.md exists? Build/test/run documented?

2. **Simple beats clever.** (Pike: "Fancy algorithms are slow when N is small.") Build the simplest version first. Complex architectures are harder for agents to modify without breaking things. If you can't explain the architecture in 30 seconds, simplify it.

3. **Measure before you act.** (Pike: "Don't tune for speed until you've measured.") Don't optimize without profiling. Don't claim something is slow without numbers. Structured logging so agents can diagnose from output, not guesswork.

4. **Validate continuously.** Linting, tests, and security checks are tight feedback loops that catch errors before they compound through agent sessions. `ruff check .` + `pytest` + Playwright E2E + ruff S rules for security.

5. **Make it recoverable.** Simple systems are easier to rebuild. Commit frequently, branch protection, backups, `trash` over `rm`. If the VPS goes down, how fast can we rebuild?

Full details with practices, current state, and roadmap: `docs.sh read agent-readiness-playbook`.

---

## 0. Restate the Goal
What does success look like in one sentence? If the goal is wrong, say so. Everything below is anchored to this.

## 1. Purpose
Does every piece earn its place? If you removed it, would the outcome change? Cut what doesn't.

## 2. Failure Modes
Where will this break, silently fail, or produce wrong results? Name specific scenarios, not vague risks. Set the bar: "it might not work" is not a failure mode. "Timezone conversion silently drops DST offset, showing data one hour late every March" is.

## 3. User Experience
If someone used this 50 times a day, what would annoy them? What's missing that they'd wish existed?

**Visual audit:** Check against the styling playbook (`docs.sh read styling-playbook`). Specifically: tables use `.table-wrap` + `.data-table`, no nested scroll containers, data truncated with "show more" (not infinite lists), KPI rows stay inline on laptop viewports (1366px), CSS variables not hardcoded hex. If screenshots are available, inspect them for overflow, stacking, and density issues.

## 4. Speed / Efficiency
What's the bottleneck? Where is effort or time wasted for marginal gain?

## 5. Leverage
What's the single highest-impact change that requires the least effort? Lead with that.

## 6. Produce the Improved Version
Do not just list feedback. Absorb it and produce the improved version directly. Match the format: code for code, strategy for strategy, plan for plan. If you list problems without fixing them, you haven't finished.

---

## Numbered Item Tracking

Before beginning the review, create a numbered list of every item/change/requirement being reviewed. Work through each item one at a time, marking PASS/FAIL with evidence. After completing the review, present a final checklist summary showing the status of every numbered item. This ensures nothing is missed.

---

## Review Links

After implementing all fixes, generate short links (`kit shortlink`) for every page that was changed and present them so Rod can review immediately. No hunting for URLs — the links must be right there at the end of the review.

---

---

## Rerun Mode

**Trigger:** "rerun PA" / "rerun the PA" / `kit pa rerun`

A rerun is NOT a fresh review. It assumes a PA review was already done in this conversation and its findings were implemented. The rerun asks one question: **what did the first review miss?**

### Rerun Steps

1. **Re-read the original PA findings** from earlier in the conversation. List every item that was found and fixed.
2. **Assume every original finding was valid.** Don't re-argue them.
3. **Look specifically for:**
   - Problems the original review missed entirely (blind spots)
   - New problems introduced by the fixes themselves
   - Interactions between fixes that create emergent issues
   - Performance or UX regressions from the changes
   - Edge cases the original review didn't consider
4. **Profile and measure.** Don't guess — run the code, time it, screenshot it, check logs. The rerun is empirical, not theoretical.
5. **If you find issues: implement the fixes** (same as step 6 of the full protocol). If nothing material: say so honestly. Don't invent problems to justify the rerun.
6. **Verify with tools.** Use Playwright, curl, pytest — whatever proves the fix works. Evidence before claims.

The rerun should be shorter than the original review. If it's not, the original review was too shallow.

---

**For code reviews:** Also apply the anti-pattern checklist AND the Linting Compliance checklist in the coding practices playbook (`docs.sh read coding-practices-playbook`). Linting is mandatory — Python projects must pass `ruff check`, TypeScript projects must pass `biome check`. If the project has no linter configured, **add one** as part of the review.

---

## Agent Readiness Check

For full PA reviews on applications (not quick fixes), assess against the Five Principles:

| # | Principle | Quick Check | What to Look For |
|---|-----------|-------------|------------------|
| 1 | Fix the Environment | AGENTS.md exists? | Build/test/run documented? Architecture clear? Conventions listed? |
| 2 | Simple Beats Clever | Architecture walkthrough | Unnecessary abstractions? Over-engineered? Could be simpler? |
| 3 | Measure Before You Act | Structured logging? | JSON logs? Error context? Can you diagnose from logs alone? |
| 4 | Validate Continuously | `ruff check .` + `pytest` | Zero lint violations? Tests pass? E2E coverage? No hardcoded secrets? |
| 5 | Make It Recoverable | Setup documented? | Could rebuild from scratch? Branch protection? Backups current? |

**Scoring:** PASS / PARTIAL / FAIL per principle. Informational, not blocking. Every FAIL is a concrete improvement.

**Reference:** Full details in `docs.sh read agent-readiness-playbook`.

---

**Canonical synthesis location:** When PA findings produce reusable anti-patterns/opposite patterns, consolidate them in `pa-antipatterns-and-opposites` and link from domain playbooks instead of duplicating long narrative blocks.
