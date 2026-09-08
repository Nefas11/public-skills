# Worked examples

Four subjects from four domains, plus the four ways the algorithm is most often
misapplied. The machine-checkable form lives in `acceptance/` — the subjects a
reviewer is handed, and the oracle they are scored against. If you change a
classification here, change it in `acceptance/oracle.json` too; the reasoning
below is what that answer key is short for.

---

## 1 — Process: duplicated status reporting

**Subject.** A crew of agents posts run status in three places: a chat channel,
a per-run log file, and a status line in a shared markdown board.

**Phase 1.** The stated requirement is "everyone can see what is running". That
is a property, not a solution. The three channels are one solution assumption
that was never compared against alternatives. → `CHALLENGE`.

**Phase 2.** Necessary effect: *an observer can answer "is it running?" without
asking*. The chat post and the board line both deliver it; the log file delivers
something else — after-the-fact reconstruction — and is the only one that
survives a restart.

| Element | Class | Why |
|---|---|---|
| chat status post | `MERGE` | same effect as the board, different place |
| board status line | `KEEP` | the durable answer to "is it running?" |
| per-run log file | `KEEP` | different effect: reconstruction, not visibility |

**Phase 5 — and this is the point of the example.** The obvious first instinct
was "automate the three postings so they cannot drift". That would have
mechanised a duplication instead of removing it, and made the removal harder,
because afterwards there is a script to justify. Delete first, then ask whether
what remains still needs automating. Usually it does not.

---

## 2 — Rule: a security gate with no hits

**Subject.** A pre-push gate that scans for credentials. In four weeks it has
blocked nothing.

**The trap.** Zero hits reads as "useless". It is equally consistent with
"working perfectly" — people stopped pasting secrets *because* the gate exists.
The data cannot distinguish these, so no amount of staring at it will.

**Class: `PROVE`, never `DELETE`.** The hard interlock applies twice over: it is
a secrets control, and its failure is irreversible — a leaked credential cannot
be un-leaked by reverting a commit.

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

**Subject.** A repository layer wrapping a data store, with exactly one
implementation and no test that substitutes another.

**Phase 1.** The requirement was "we might swap the store". Three years, no
swap. That is a historical requirement, not a current one → `CHALLENGE`.

**Phase 2 — class `DELETE`, with the proof the class demands:**

| Field | |
|---|---|
| Purpose today | indirection for a substitution that never happened |
| Evidence of use | one implementation; no test doubles it; no second binding |
| Replacing protection | the store's own contract tests, which the wrapper only forwards to |
| Blast radius | every call site — large but entirely inside the repo |
| Reversibility | full: one commit, revert restores it |
| Detector | contract test suite; a type error at compile time |
| Safe probe | inline the wrapper on a branch, run the full suite, compare coverage |
| Stop criterion | any contract test fails, or coverage drops |

Contrast with example 2: the same class, `DELETE`, is defensible here purely
because the effect is reversible and a mechanical detector exists.

---

## 4 — Personal workflow: a daily briefing

**Subject.** Someone assembles a briefing by hand each morning from five
sources and wants it automated.

**The request is for Phase 5. Start at Phase 1 anyway.**

Questioning reveals that two of the five sources have never once produced
something acted upon → `DELETE`. Two others report the same items from
different angles → `MERGE`. What remains is one source and a filter.

**Phase 3.** The remaining flow is now three steps, not eleven.

**Phase 5.** *Now* automation is worth discussing — and it is cheap, because
there are three typed steps instead of eleven ad-hoc ones. Had this been
automated as requested on day one, the two useless sources would have been
enshrined in a script, and their removal would have needed a code change
instead of a decision.

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
