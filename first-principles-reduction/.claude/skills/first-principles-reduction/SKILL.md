---
name: first-principles-reduction
description: Apply the five-step reduction algorithm — question requirements, delete, simplify, accelerate, automate — to any system in that fixed order, and classify every element DELETE / MERGE / KEEP / PROVE with the evidence that justifies it. Read-only: it recommends, it never changes anything. Use when asked "what can go?", "simplify this process/architecture/ruleset", "review this from first principles", "which gates or steps are unnecessary?", "delete before optimising", or "apply the five-step algorithm to this". The subject is free — a process, a ruleset, code, an architecture, a document, an org, a personal workflow. NOT for implementing a change, for cosmetic shortening, or when the deletion decision is already made and only execution remains.
---

# first-principles-reduction

Most reduction efforts fail the same way: they start at step 5. Someone
automates a process nobody questioned, built from steps nobody deleted. The
result is a faster version of the wrong thing, and it is now harder to remove
because it has a script.

This skill enforces the order. Each phase may only touch what survived the one
before it.

```
 1 QUESTION ──▶ 2 DELETE ──▶ 3 SIMPLIFY ──▶ 4 ACCELERATE ──▶ 5 AUTOMATE
   requirements   remove        what is left    the critical      only what is
   and their      what has      after removal   path, once it     stable and
   evidence       no purpose                    is minimal        necessary
```

**You never execute.** Not one file, not one setting, not one deletion. The
deliverable is a report with tests someone else can run. If the subject is a
repository, `git status --porcelain` must be byte-identical before and after
your analysis — take it at the start and compare at the end. This is not a
formality: an "audit" that edits is no longer evidence about the system, it is
a change to it.

## The one failure mode that matters

**Absence of evidence is not evidence of absence.** A gate that has caught
nothing in four weeks might be useless — or it might be the reason the four
weeks were quiet. These two look identical in the data. The whole burden of
this skill rests on telling them apart, and the answer is never "it hasn't
fired, so delete it".

That is what `PROVE` is for. Use it generously. A classification you cannot
defend is worse than an open question, because it looks finished.

## Input contract

**Required — refuse to classify without these:**

| | |
|---|---|
| **Subject and boundary** | what is in scope, and explicitly what is not |
| **Desired outcome** | the observable benefit the subject exists to produce |

**Optional but valuable:** non-negotiable constraints · known risks ·
measurements · observation window · who is allowed to change what.

If the purpose is missing, derive it from the artefacts and **mark it as an
assumption in the report**. Never recommend a deletion while the necessary
effects of the thing are unnamed — you would be deleting a purpose you never
found, which is indistinguishable from deleting one that was not there.

## Phase 0 — Scope and baseline

- Fix the subject and its boundary. Name what you did **not** examine.
- Inventory the current state: every element that could later be classified.
- For a repository: record `git status --porcelain` now.
- Search for prior decisions and accepted risks. **Do not recycle a risk
  someone already accepted as a new finding** — that is how audits become
  noise that gets ignored wholesale.

## Phase 1 — Question the requirements

For each requirement, ask:

- Who needs it? A named role, not "the business".
- What observable problem does it solve?
- What evidence supports it?
- Is it current, or historical residue?
- Is it a requirement, a **solution assumption**, or a habit?
- What measurably happens if it is gone?

The third question is the one that pays. Requirements are routinely stated as
solutions ("we need a nightly sync") when the requirement is a property ("the
two stores must not diverge for more than a day"). A solution assumption that
gets promoted to requirement makes every later phase defend the wrong thing.

Output per requirement: **`RETAIN` · `CHALLENGE` · `UNKNOWN`**.

## Phase 2 — Delete

Classify every element:

| Class | Meaning |
|---|---|
| **`DELETE`** | no necessary purpose, or fully redundant |
| **`MERGE`** | purpose is necessary but covered twice |
| **`KEEP`** | necessary effect, not secured elsewhere |
| **`PROVE`** | evidence insufficient — a controlled measurement is required |

Every `DELETE` and `MERGE` candidate carries **all nine fields**. A candidate
missing any of them is not a candidate, it is `PROVE`:

1. Element
2. Purpose today
3. Evidence of use
4. Replacing protection, or proof it is unnecessary
5. Blast radius
6. Reversibility
7. Detector — who or what notices if removal was wrong
8. Safe probe — how to test removal without committing to it
9. Stop and rollback criterion

**Hard interlocks — no judgement call overrides these:**

- **Irreversible effect ⇒ never an autonomous deletion clearance.** Escalate.
- Security, identity, secrets, production, compliance and external
  communication controls are **never deleted on low hit-count alone**.
- "No hits in four weeks" is a **signal, never a proof**.
- A gate may only go once its protection is shown redundant, unnecessary, or
  **falsified under control** — meaning: you neutralised the mechanism and
  demonstrated that the thing it guards against still does not happen.

## Phase 3 — Simplify

Only what came out as `KEEP` or `MERGE`. **Never optimise a `DELETE`
candidate** — the most common way effort is wasted here, because a polished
element is much harder to remove afterwards.

Merge steps · reduce handoffs · unify where state lives · replace prose with
mechanism where the mechanism is simpler and checkable · remove special cases ·
name one source of truth.

## Phase 4 — Accelerate

Only after 1–3. Optimising the speed of a step you have not yet tried to delete
is the same mistake as automating it.

Measure wait and queue time · examine batch and handoff boundaries · remove
unnecessary synchronisation · shorten the critical path.

**Never accelerate by skipping a protective gate.** If a gate is the
bottleneck, that is a Phase 2 finding about the gate, argued on its own merits
— not a speed decision made sideways.

## Phase 5 — Automate

Only stable, necessary, already-simplified steps. All six must be yes:

- Is the input typed?
- Is success machine-observable?
- Is the failure behaviour fail-closed?
- Is there an independent detector?
- Are stop and recovery defined?
- Is it settled who may trigger it and who checks it?

Anything unstable or still disputed does not get automated. Automation of a
contested process does not settle the dispute; it hides it and makes the losing
side's objection expensive to raise.

## Deliverable

Use `references/report-template.md`. Structure:

1. **Verdict** in one or two sentences.
2. Scope, purpose, constraints, and **evidence gaps**.
3. Element table: `Element | Purpose | Evidence | Class | Risk | Recommendation`.
4. Delete/merge candidates, each with its safe probe.
5. Simplified target flow.
6. Acceleration options.
7. Automation candidates.
8. Order of execution: `REMOVE → SIMPLIFY → SPEED → AUTOMATE`.
9. **Explicit statement that nothing was changed.**

**Budget: at most 3 prioritised deletion candidates and 5 further
recommendations.** Everything else goes in a short list. This is a hard limit,
not a style note. A fifty-point report is not more thorough — it transfers the
prioritisation work back to the reader, who then does none of it. Three
candidates with runnable probes beat thirty with none.

## Relationship to the audit skills

This skill is the algorithm. The audits are the lenses that carry it to a
domain, and they call it rather than copy it — no cyclic dependency, one place
to fix.

- **`agent-rules-audit`** — rules, gates, handoffs and duplicated
  sources-of-truth. It stays report-only; findings keep their audit evidence
  and priority, and gain the reduction class as an extra field.
- **`codebase-audit`** — its simplification dimension supplies the burden of
  proof: a simpler form must cover at least the same necessary effects **and
  the same failure cases**. Defect findings stay with their own categories;
  this one supplies the simpler fix, not the bug.

## Acceptance — showing that the judgement, not just the contract, holds

Three agents using this skill must reach the same answer wherever a hard rule
decides. That is checked, not assumed:

1. The reviewer is handed `references/acceptance/subjects.json` — subjects and
   facts only. It contains no class, no reasoning, no interlock marker. Facts
   that are needed to judge (irreversibility, control class) stay in it: hiding
   those would test guessing, not judgement.
2. The answer is written as JSON: element → class, plus `behaviour` for the
   negative cases.
3. `scripts/evaluate.py ANSWER.json` compares it against
   `references/acceptance/oracle.json`, which is loaded only at that point.

Interlock elements must match — those are decided by a rule. Everything else
may differ; `--strict` pins those too, but demanding agreement on judgement
would reward copying over reasoning, which is the failure this construction
exists to prevent.

**The evaluator is itself under test.** `tests/test_evaluator.py` corrupts the
oracle and requires the same evaluator to go red. An evaluator that cannot be
made to fail proves nothing, and the earlier version of these fixtures failed
exactly there: it checked that the answer key was legal, never that it was
right.

## What this skill must never do

- Change anything. Ever. Read-only is the whole basis of its evidence.
- Recommend deleting something whose purpose was never established.
- Treat a quiet gate as a useless gate.
- Skip a phase, or let a later phase touch what an earlier one flagged.
- Produce a class without the evidence that carries it — say `PROVE` instead.
