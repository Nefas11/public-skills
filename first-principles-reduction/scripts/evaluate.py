#!/usr/bin/env python3
"""Compare an agent's classification against the acceptance oracle.

Why this exists (Senox, review on PR #18): the first version of the acceptance
fixtures carried `expected` right next to the subject and only checked that the
answer key was internally legal. Two things were wrong with that. The reviewer
could read the answers, and — the worse one — a deliberately WRONG key stayed
green, because nothing ever compared a real answer against it.

So the comparison happens here, mechanically, and this script is itself under
test: tests/test_evaluator.py corrupts the oracle and requires this evaluator to
go red. An evaluator that cannot be made to fail is not evidence.

Usage:
    evaluate.py ANSWER.json [--oracle PATH] [--strict]

ANSWER.json:
    {"F2-quiet-security-gate": {"elements": {"pre-push credential scanner": "PROVE"}},
     "N4-cosmetic": {"behaviour": "do-not-trigger"}}

Exit 0 = every interlock matched (and, with --strict, every element).
Exit 1 = a mismatch. Exit 2 = the answer or the oracle is unusable.
"""
import argparse
import json
import sys
from pathlib import Path

VALID_CLASSES = {"DELETE", "MERGE", "KEEP", "PROVE"}
DEFAULT_ORACLE = Path(__file__).resolve().parent.parent / "references" / "acceptance" / "oracle.json"


class Mismatch(dict):
    """One disagreement, in a shape that prints and asserts equally well."""


def evaluate(answer: dict, oracle: dict, strict: bool = False) -> list:
    """Return a list of Mismatch. Empty list means the answer passed.

    Interlock elements are always checked. Non-interlock elements are checked
    only under --strict: they are judgement, and demanding agreement there
    would reward copying over reasoning.
    """
    problems = []

    for case_id, expected in oracle.get("cases", {}).items():
        got = answer.get(case_id)
        if got is None:
            problems.append(Mismatch(case=case_id, kind="missing",
                                     detail="the answer says nothing about this case"))
            continue
        got_elements = got.get("elements", {})

        for element, spec in expected.get("elements", {}).items():
            want = spec["class"]
            have = got_elements.get(element)
            if have is None:
                problems.append(Mismatch(case=case_id, element=element, kind="missing",
                                         expected=want, got=None))
                continue
            if have not in VALID_CLASSES:
                problems.append(Mismatch(case=case_id, element=element, kind="not-a-class",
                                         expected=want, got=have))
                continue
            if have != want and (spec.get("interlock") or strict):
                problems.append(Mismatch(
                    case=case_id, element=element,
                    kind="interlock" if spec.get("interlock") else "class",
                    expected=want, got=have, why=spec.get("why", "")))

        # A class the oracle forbids is a failure wherever it appears — this is
        # the "never delete a quiet security control" rule, mechanised.
        for forbidden in expected.get("forbidden_classes", []):
            for element, have in got_elements.items():
                if have == forbidden:
                    problems.append(Mismatch(case=case_id, element=element, kind="forbidden",
                                             expected=f"anything but {forbidden}", got=have))

        stop = got.get("stopped_at_phase")
        bound = expected.get("must_not_reach_phase")
        if bound is not None and stop is not None and stop >= bound:
            problems.append(Mismatch(case=case_id, kind="phase",
                                     expected=f"< {bound}", got=stop,
                                     why=expected.get("why_phase_bound", "")))

    for case_id, expected in oracle.get("negative_cases", {}).items():
        got = answer.get(case_id)
        if got is None:
            problems.append(Mismatch(case=case_id, kind="missing",
                                     detail="the answer says nothing about this case"))
            continue
        have = got.get("behaviour")
        if have != expected["behaviour"]:
            problems.append(Mismatch(case=case_id, kind="behaviour",
                                     expected=expected["behaviour"], got=have,
                                     why=expected.get("why", "")))

    return problems


def load(path: Path, label: str) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"{label} not found: {path}")
    except json.JSONDecodeError as exc:
        sys.exit(f"{label} is not valid JSON: {exc}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("answer", type=Path)
    ap.add_argument("--oracle", type=Path, default=DEFAULT_ORACLE)
    ap.add_argument("--strict", action="store_true",
                    help="also require agreement on judgement (non-interlock) elements")
    args = ap.parse_args(argv)

    problems = evaluate(load(args.answer, "answer"), load(args.oracle, "oracle"), args.strict)
    if not problems:
        print("PASS — every interlock matched" + (" and every element agreed" if args.strict else ""))
        return 0

    print(f"FAIL — {len(problems)} mismatch(es)")
    for p in problems:
        where = p.get("case", "?")
        if p.get("element"):
            where += f" / {p['element']}"
        print(f"  [{p['kind']}] {where}: expected {p.get('expected')!r}, got {p.get('got')!r}")
        if p.get("why"):
            print(f"      {p['why']}")
        if p.get("detail"):
            print(f"      {p['detail']}")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as exc:
        raise
    except Exception as exc:  # noqa: BLE001 — a crashed evaluator must not read as PASS
        print(f"ERROR — evaluator failed: {exc}", file=sys.stderr)
        sys.exit(2)
