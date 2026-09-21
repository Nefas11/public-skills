# Worked examples

Four subjects from four domains, plus the four ways the algorithm is most often
misapplied. The machine-checkable form lives in `acceptance/` — the subjects a
reviewer is handed, and the oracle they are scored against. The reasoning below
is what that answer key is short for, so the two must agree.

That agreement used to be a request in this paragraph and nothing more, which
is how a class here and a class there came apart during review.
`tests/test_skill_contract.py` now compares every class named below against
`acceptance/oracle.json`, so changing one without the other goes red.

---

## 1 — Process: duplicated status reporting

**Subject.** A crew of agents posts run status in three places: a chat channel,
a per-run log file, and a status line in a shared markdown board.

**Phase 1.** The requirements are "everyone can see what is running" and "runs
can be reconstructed after a restart". Those are properties, not solutions. The
three channels are one solution assumption that was never compared against
alternatives. → `CHALLENGE`.

**Phase 2.** Necessary effect: *an observer can answer "is it running?" without
asking*. The chat post and the board line both deliver it; the log file delivers
something else — after-the-fact reconstruction — and is the only one that
survives a restart.

| Element | Class | Why |
|---|---|---|
| chat status post | `MERGE` | same effect as the board, different place |
| board status line | `KEEP` | the current answer to "is it running?" |
| per-run log file | `KEEP` | different effect: reconstruction, not visibility |

**Phase 5 — and this is the point of the example.** The obvious first instinct
was "automate the three postings so they cannot drift". That would have
mechanised a duplication instead of removing it, and made the removal harder,
because afterwards there is a script to justify. Delete first, then ask whether
what remains still needs automating. Usually it does not.

---

## 2 — Rule: a security gate with no hits

**Subject.** A pre-push credential scanner, run as a gate before every push. In
four weeks it has blocked nothing.

**The trap.** Zero hits reads as "useless". It is equally consistent with
"working perfectly" — people stopped pasting secrets *because* the gate exists.
The data cannot distinguish these, so no amount of staring at it will.

| Element | Class | Why |
|---|---|---|
| pre-push credential scanner | `PROVE` | zero hits cannot tell "useless" from "working"; secrets control, irreversible failure |

**Never `DELETE`.** The hard interlock applies twice over: it is a secrets
control, and its failure is irreversible — a leaked credential cannot be
un-leaked by reverting a commit.

The analysis also stops here. Phases 3 to 5 may only touch what has been
decided, and nothing about this gate has been. Simplifying or automating around
an undecided control is the sideways version of removing it.

**The controlled falsification** — the only evidence that would move this:
neutralise the gate in a sandbox, introduce a known-bad test credential, and
confirm nothing downstream catches it. If nothing does, the gate is the only
protection and stays. If something does, you have found the redundancy you
claimed, and *now* you may argue `MERGE`.

Note what this costs: real work, in a sandbox, with a positive control. That
cost is the point. A protection this consequential should be expensive to
remove.

---

## 3 — Code: a redundant abstraction

**Subject.** A repository wrapper around a data store, with exactly one
implementation and no test that substitutes another.

**Phase 1.** The requirement was "we might swap the store". Three years, no
swap. That is a historical requirement, not a current one → `CHALLENGE`.

**Phase 2 — the class, and then the proof it demands:**

| Element | Class | Why |
|---|---|---|
| repository wrapper | `DELETE` | the probe ran: suite green with the wrapper inlined, coverage unchanged |

| Field | |
|---|---|
| Purpose today | indirection for a substitution that never happened |
| Evidence of use | one implementation; no test doubles it; no second binding |
| Replacing protection | the store's own contract tests — **run** on a branch with the wrapper inlined: green, coverage unchanged |
| Blast radius | every call site — large but entirely inside the repo |
| Reversibility | full: one commit, revert restores it |
| Detector | contract test suite; a type error at compile time |
| Safe probe | inlining on a branch — carried out, and the result above is what it produced |
| Stop criterion | any contract test fails, or coverage drops |

The single word that earns the class is **run**. Until the suite had actually
executed against the inlined form, "the contract tests carry the effect" was a
plausible expectation, and a plausible expectation is `PROVE`.

Contrast with example 2, where the same reasoning ends differently: there the
probe would mean disabling a secrets control, so it stays undone, and the class
stays `PROVE`. Reversibility and a detector make a probe *possible* and cheap;
only the probe's result makes the deletion defensible.

---

## 4 — Personal workflow: a daily briefing

**Subject.** Someone assembles a briefing by hand each morning from five
sources and wants it automated.

**The request is for Phase 5. Start at Phase 1 anyway.**

Questioning reveals that two of the five sources produced nothing the reader
acted on in ninety days, two others report the same items from different
angles, and one is the sole origin of acted-upon items.

| Element | Class | Why |
|---|---|---|
| source A | `PROVE` | quiet for ninety days — but nobody measured whether it carries rare events |
| source B | `PROVE` | same |
| source C | `MERGE` | same items as D, from another angle |
| source D | `MERGE` | same items as C |
| source E | `KEEP` | sole origin of acted-upon items; the necessary effect dies with it |

**The two quiet sources are `PROVE`, not `DELETE`** — and this is where the
example earns its place, because `DELETE` is the tempting answer and the wrong
one. Ninety days of no action measures *use*. The class turns on *necessity*,
and a source that carries a rare event — the quarterly filing, the one outage
notice — looks exactly like a source that carries nothing. Nobody measured
which of the two these are. That is the same shape as the quiet gate in
example 2, one domain over.

What would settle it: a window long enough to contain the rare events, or a
named source that demonstrably covers the same ground. Either produces a
`DELETE` with evidence behind it. Neither is expensive. Skipping both and
writing `DELETE` anyway is the failure this skill exists to prevent.

**Phase 3.** The `MERGE` alone already shortens the flow, and it does not wait
on the open question.

**Phase 5.** *Now* automation is worth discussing for the settled part. Had
this been automated as requested on day one, all five sources would have been
enshrined in a script, and even the uncontroversial merge would have needed a
code change instead of a decision.

---

## The four misapplications

**Automating an unsettled process.** The user asks directly for automation of
something nobody has questioned. Stop at Phase 1/2 and say so. Delivering the
automation is the failure, not the refusal.

**Irreversible deletion without a way back.** No detector, no rollback, no safe
probe → no clearance, regardless of how confident the reasoning feels.
Escalate to a human.

**Inventing certainty.** Evidence is missing, so a class gets picked anyway
because a table with `PROVE` in it looks unfinished. It is not unfinished — it
is honest. `PROVE` is a finding.

**Cosmetic shortening.** "Make this document shorter" is not this skill. There
is no requirement to question and no necessary effect to protect. Do not
trigger.
