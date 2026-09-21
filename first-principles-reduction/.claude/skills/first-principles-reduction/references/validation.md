# Maintainer validation

A normal analysis needs none of this. The skill works on supplied text without
Python, Git, credentials, a particular model or network access. These checks
are for maintainers and for explicit release evaluations.

## Local regression tests

With Python 3 available, run from the skill directory:

```bash
python3 -B -m unittest discover -s tests -v
```

Only the standard library is used. The tests create temporary synthetic answer
files and never inspect a subject under review. They pin the contract in
`SKILL.md` (phase order, interlocks, the nine candidate fields, the budget),
keep subjects and answer key apart, and deliberately corrupt answers and oracle
entries so that a false pass becomes visible. An oracle without cases is
refused rather than passed.

## Independent behavioural evaluation

1. When explicitly evaluating a release and delegation is available and
   authorised, give three independent reviewers `SKILL.md` plus
   `references/acceptance/subjects.json`. Do not give them the oracle or the
   worked examples before they answer. Without delegation, use independent
   human reviews, or report that agreement has not been measured.
2. Each reviewer produces a JSON object keyed by case id. Positive cases
   contain `elements`, mapping the supplied element names to
   `DELETE` / `MERGE` / `KEEP` / `PROVE`, and `stopped_at_phase`, an integer
   1–5: the last phase with supported analytical progress, not the last report
   heading written. Negative cases contain the stated `behaviour` value and no
   phase. Reviewers classify; they do not implement or execute anything.
3. Save each answer outside any inspected subject, then evaluate it:

```bash
python3 -B scripts/evaluate.py /path/to/reviewer-answer.json
```

   `references/acceptance/oracle.json` is loaded only after the answers exist.
   This is procedural separation, not a security boundary against an agent
   with file access.
4. Require agreement where a hard rule decides. Non-interlock judgements may
   differ; `--strict` checks those too, but strict agreement is not the default
   acceptance criterion. `--oracle PATH` selects a different key, for testing
   the evaluator itself.
5. Report individual results and disagreements. A green run shows that the
   yardstick holds on these fixtures, not that every future recommendation is
   correct, and never that a proposed change was run.

Exit codes: 0 = matches; 1 = mismatch; 2 = unusable input or evaluator failure.
