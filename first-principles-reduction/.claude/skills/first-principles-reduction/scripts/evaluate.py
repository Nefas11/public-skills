#!/usr/bin/env python3
"""Compare an agent's classification against the acceptance oracle.

Why this exists: the first version of the acceptance fixtures carried
`expected` right next to the subject and only checked that the answer key was
internally legal. Two things were wrong with that. The reviewer could read the
answers, and — the worse one — a deliberately WRONG key stayed green, because
nothing ever compared a real answer against it.

So the comparison happens here, mechanically, and this script is itself under
test: tests/test_evaluator.py corrupts the oracle and requires this evaluator to
go red. An evaluator that cannot be made to fail is not evidence. For the same
reason an oracle without cases is refused instead of passing everything.

Usage:
    evaluate.py ANSWER.json [--oracle PATH] [--strict]

ANSWER.json:
    {"F2-quiet-security-gate": {"elements": {"pre-push credential scanner": "PROVE"},
                                "stopped_at_phase": 2},
     "N4-cosmetic": {"behaviour": "do-not-trigger"}}

Every positive case needs `stopped_at_phase`, an integer 1..5: the last phase
with supported analytical progress, not the last heading that was written.

The answer may name only the cases and elements the subjects offered. An
invented case or element is a mismatch, not something to ignore: a made-up
"production backup: DELETE" riding along inside an otherwise correct answer
would otherwise pass.

Exit 0 = every interlock matched (and, with --strict, every element).
Exit 1 = a mismatch. Exit 2 = the answer or the oracle is unusable.

The evaluator reads two local JSON files and nothing else: no network, no live
subject, no execution of any recommendation.
"""
import argparse
import json
import sys
from pathlib import Path

VALID_CLASSES = {"DELETE", "MERGE", "KEEP", "PROVE"}
VALID_BEHAVIOURS = {"stop-at-phase-1-or-2", "no-clearance-escalate",
                    "classify-PROVE", "do-not-trigger"}
# A positive case answers with a classification and where the analysis stopped.
# Nothing else: an answer carrying extra keys is claiming something the oracle
# has no opinion on, which is how an invented "recommendations" block rode
# along inside an otherwise correct answer.
POSITIVE_KEYS = {"elements", "stopped_at_phase"}
NEGATIVE_KEYS = {"behaviour"}
# Phase 3 and later work on what survived phase 2 — KEEP and MERGE. A case whose
# submitted classes contain neither has nothing to simplify, accelerate or
# automate, so those phases are unreachable for it.
REDUCIBLE_CLASSES = {"KEEP", "MERGE"}
DEFAULT_ORACLE = Path(__file__).resolve().parent.parent / "references" / "acceptance" / "oracle.json"


class Mismatch(dict):
    """One disagreement, in a shape that prints and asserts equally well."""


def validate_oracle(oracle) -> None:
    """Refuse an oracle that could not fail anything, or that says nonsense.

    An empty or malformed answer key would produce zero mismatches and read as
    PASS. That is the one outcome this script must never produce by accident.

    The first version checked only that the sections existed and were not empty.
    Review showed that too thin: an invalid class, an `interlock` that
    is a string rather than a boolean, or a `behaviour` outside the enum all
    slipped through, and an oracle with every interlock removed still passed
    while pinning nothing. The whole shape is checked here, once, before any
    comparison — a yardstick that is not itself measured is not a yardstick.
    """
    if type(oracle) is not dict:
        raise ValueError("oracle must be a JSON object")
    for key in ("cases", "negative_cases"):
        section = oracle.get(key)
        if type(section) is not dict or not section:
            raise ValueError(f"oracle has no usable '{key}' section")

    interlocks = 0
    for case_id, spec in oracle["cases"].items():
        if type(spec) is not dict:
            raise ValueError(f"oracle case {case_id} is not an object")
        elements = spec.get("elements")
        if type(elements) is not dict or not elements:
            raise ValueError(f"oracle case {case_id} names no elements")
        for element, s in elements.items():
            if type(s) is not dict:
                raise ValueError(f"oracle {case_id}/{element} is not an object")
            if s.get("class") not in VALID_CLASSES:
                raise ValueError(
                    f"oracle {case_id}/{element} has class {s.get('class')!r}, "
                    f"expected one of {sorted(VALID_CLASSES)}")
            if "interlock" in s and type(s["interlock"]) is not bool:
                raise ValueError(
                    f"oracle {case_id}/{element}: interlock must be true or false, "
                    f"got {s['interlock']!r} — a truthy string would pin silently")
            if s.get("interlock"):
                interlocks += 1
                if not str(s.get("why", "")).strip():
                    raise ValueError(f"oracle {case_id}/{element}: interlock without a reason")
        forbidden = spec.get("forbidden_classes", [])
        if type(forbidden) is not list or any(c not in VALID_CLASSES for c in forbidden):
            raise ValueError(f"oracle case {case_id}: forbidden_classes must list real classes")
        bound = spec.get("must_not_reach_phase")
        if bound is not None and (type(bound) is not int or type(bound) is bool
                                  or not 2 <= bound <= 6):
            raise ValueError(
                f"oracle case {case_id}: must_not_reach_phase must be an integer 2..6, "
                f"got {bound!r}")

    if not interlocks:
        raise ValueError(
            "oracle pins no interlock — every element would be judgement, and the "
            "agreement this fixture exists to demonstrate could not be shown")

    for case_id, spec in oracle["negative_cases"].items():
        if type(spec) is not dict:
            raise ValueError(f"oracle negative case {case_id} is not an object")
        if spec.get("behaviour") not in VALID_BEHAVIOURS:
            raise ValueError(
                f"oracle negative case {case_id} has behaviour {spec.get('behaviour')!r}, "
                f"expected one of {sorted(VALID_BEHAVIOURS)}")


def phase_bounds(case_id, spec, submitted_classes):
    """The phases an answer to this case may legitimately have stopped at.

    Returns (lowest, highest, why). Derived from the answer, not from a scalar
    in the oracle, because the same case admits different phases depending on
    what was classified:

    * Every element classified means phase 2 is finished, so stopping at 1
      contradicts the answer's own content.
    * Phases 3-5 operate on what survived deletion. With no KEEP and no MERGE
      among the submitted classes there is nothing to simplify, speed up or
      automate, so the analysis cannot honestly have gone past 2.

    A case may additionally pin a hard ceiling via `must_not_reach_phase`; the
    tighter of the two wins. Review showed why the scalar alone was
    wrong in both directions: a complete classification claiming phase 1 passed,
    a single PROVE element claiming phase 5 passed, and F1 was barred from
    phase 5 even though its reduced KEEP/MERGE flow may legitimately be taken
    that far.
    """
    lowest, why_low = 1, ""
    if len(submitted_classes) == len(spec["elements"]):
        lowest, why_low = 2, "every element is classified, so phase 2 is complete"

    if REDUCIBLE_CLASSES & set(submitted_classes.values()):
        highest, why_high = 5, ""
    else:
        highest = 2
        why_high = ("no element was classified KEEP or MERGE, so phases 3-5 have "
                    "nothing to work on")

    bound = spec.get("must_not_reach_phase")
    if bound is not None and bound - 1 < highest:
        highest = bound - 1
        why_high = spec.get("why_phase_bound", "")
    return lowest, highest, (why_low if why_low else "") or why_high


def evaluate(answer: dict, oracle: dict, strict: bool = False) -> list:
    """Return a list of Mismatch. Empty list means the answer passed.

    Interlock elements are always checked. Non-interlock elements are checked
    only under --strict: they are judgement, and demanding agreement there
    would reward copying over reasoning.
    """
    validate_oracle(oracle)
    if type(answer) is not dict:
        raise ValueError("answer must be a JSON object")
    problems = []

    # An answer may only speak about the cases it was given. Anything else is a
    # classification of something nobody asked about, and the oracle has no
    # opinion on it — which is exactly why silently ignoring it would let an
    # invented "production backup: DELETE" ride along inside a passing answer.
    for case_id in answer:
        if case_id not in oracle["cases"] and case_id not in oracle["negative_cases"]:
            problems.append(Mismatch(case=case_id, kind="unknown-case",
                                     expected="a case from the subjects", got=case_id))

    for case_id, expected in oracle["cases"].items():
        got = answer.get(case_id)
        if type(got) is not dict:
            problems.append(Mismatch(case=case_id, kind="missing",
                                     detail="the answer says nothing about this case"))
            continue
        # A positive case answers with exactly two things. The negative cases
        # were already held to their single key; leaving the positive side open
        # let an invented `recommendations` block ride along inside an otherwise
        # correct answer, under --strict as much as without it.
        for key in sorted(set(got) - POSITIVE_KEYS):
            problems.append(Mismatch(case=case_id, kind="unexpected-field",
                                     expected=f"only {sorted(POSITIVE_KEYS)}", got=key))

        got_elements = got.get("elements", {})
        if type(got_elements) is not dict:
            got_elements = {}

        # Same rule one level down: the element set must be exactly the one the
        # subject offered. An extra element is an invented finding.
        for element in got_elements:
            if element not in expected["elements"]:
                problems.append(Mismatch(case=case_id, element=element, kind="unknown-element",
                                         expected="an element named in the subject", got=element))

        for element, spec in expected["elements"].items():
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

        # The phase is mandatory. An answer that stays silent about where it
        # stopped cannot be checked against a phase bound, so silence is a
        # mismatch, not a pass. `bool` is excluded on purpose: True would pass
        # an `int` check and compare as 1.
        stop = got.get("stopped_at_phase")
        if type(stop) is not int or type(stop) is bool or not 1 <= stop <= 5:
            problems.append(Mismatch(case=case_id, kind="phase",
                                     expected="integer 1..5", got=stop))
        else:
            classes = {el: c for el, c in got_elements.items()
                       if el in expected["elements"] and c in VALID_CLASSES}
            lowest, highest, why = phase_bounds(case_id, expected, classes)
            if stop < lowest:
                problems.append(Mismatch(case=case_id, kind="phase",
                                         expected=f">= {lowest}", got=stop, why=why))
            elif stop > highest:
                problems.append(Mismatch(case=case_id, kind="phase",
                                         expected=f"<= {highest}", got=stop, why=why))

    for case_id, expected in oracle["negative_cases"].items():
        got = answer.get(case_id)
        if type(got) is not dict:
            problems.append(Mismatch(case=case_id, kind="missing",
                                     detail="the answer says nothing about this case"))
            continue
        have = got.get("behaviour")
        if have != expected["behaviour"]:
            problems.append(Mismatch(case=case_id, kind="behaviour",
                                     expected=expected["behaviour"], got=have,
                                     why=expected.get("why", "")))
        # A negative case offers no elements and asks for no phase; it asks what
        # the skill should DO. Reading only `behaviour` and ignoring the rest
        # left the ride-along open on this side: an answer could smuggle
        # `elements: {"production backup": "DELETE"}` into N4 and still pass.
        extra = sorted(set(got) - {"behaviour"})
        if extra:
            problems.append(Mismatch(
                case=case_id, kind="unexpected-field",
                expected="only 'behaviour'", got=", ".join(extra),
                why="a negative case names no elements and no phase to classify"))

    return problems


def load(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"{label} not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc}") from None
    if type(value) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    return value


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("answer", type=Path)
    ap.add_argument("--oracle", type=Path, default=DEFAULT_ORACLE)
    ap.add_argument("--strict", action="store_true",
                    help="also require agreement on judgement (non-interlock) elements")
    args = ap.parse_args(argv)

    try:
        problems = evaluate(load(args.answer, "answer"), load(args.oracle, "oracle"), args.strict)
    except ValueError as exc:
        print(f"ERROR — {exc}", file=sys.stderr)
        return 2
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
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — a crashed evaluator must not read as PASS
        print(f"ERROR — evaluator failed: {exc}", file=sys.stderr)
        sys.exit(2)
