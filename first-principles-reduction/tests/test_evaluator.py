"""Proves the acceptance evaluator can actually fail.

The first version of the fixtures put `expected` next to the subject and only
validated that the answer key was internally legal. A deliberately wrong key
stayed green, because nothing compared a real answer against it. "The tests
pass" said nothing about classification.

The four properties the review asked for, and where each lives:

  1. subjects-only input, no expected/why/interlock  -> Separation below
  2. mechanical comparison against a separate oracle -> PositiveControl
  3. negative control: corrupt an expected value, the SAME evaluator must go red
                                                     -> NegativeControl
  4. positive control with the intact oracle is green -> PositiveControl

The negative control is the load-bearing one. Without it this file would only
prove that the evaluator agrees with itself. OracleStructure extends it to the
shape of the oracle: an empty answer key must be refused, not passed.
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import evaluate  # noqa: E402

ACCEPT = SKILL_DIR / "references" / "acceptance"
SUBJECTS = json.loads((ACCEPT / "subjects.json").read_text(encoding="utf-8"))
ORACLE = json.loads((ACCEPT / "oracle.json").read_text(encoding="utf-8"))
EVALUATOR = SKILL_DIR / "scripts" / "evaluate.py"


# The answer a correct run produces — derived from the oracle on purpose. It is
# the thing under test in PositiveControl and the thing we perturb everywhere
# else; writing it out by hand would only add a second place to get it wrong.
def perfect_answer(oracle=ORACLE):
    answer = {}
    for case_id, spec in oracle["cases"].items():
        answer[case_id] = {
            "elements": {el: s["class"] for el, s in spec["elements"].items()},
            "stopped_at_phase": 2,
        }
        if "must_not_reach_phase" in spec:
            answer[case_id]["stopped_at_phase"] = spec["must_not_reach_phase"] - 1
    for case_id, spec in oracle["negative_cases"].items():
        answer[case_id] = {"behaviour": spec["behaviour"]}
    return answer


def run_cli(*args):
    return subprocess.run([sys.executable, "-B", str(EVALUATOR), *map(str, args)],
                          capture_output=True, text=True, check=False)


class Separation(unittest.TestCase):
    """What the reviewer sees must not contain what it is supposed to produce."""

    LEAKS = ("expected", "class", "interlock", "why", "forbidden_classes",
             "required_evidence", "expected_behaviour")

    def test_subjects_carry_no_answer(self):
        blob = json.dumps({k: v for k, v in SUBJECTS.items() if k != "_comment"})
        for leak in self.LEAKS:
            self.assertNotIn(f'"{leak}"', blob,
                             f"subjects.json exposes '{leak}' — the reviewer can read the answer")
        for cls in evaluate.VALID_CLASSES:
            self.assertNotIn(f'"{cls}"', blob, f"subjects.json names the class {cls}")

    def test_every_subject_has_an_oracle_entry_and_vice_versa(self):
        subj = {c["id"] for c in SUBJECTS["cases"]}
        self.assertEqual(subj, set(ORACLE["cases"]), "subjects and oracle disagree on cases")
        subj_neg = {c["id"] for c in SUBJECTS["negative_cases"]}
        self.assertEqual(subj_neg, set(ORACLE["negative_cases"]),
                         "subjects and oracle disagree on negative cases")

    def test_every_element_in_the_oracle_was_offered_in_the_subject(self):
        by_id = {c["id"]: c for c in SUBJECTS["cases"]}
        for case_id, spec in ORACLE["cases"].items():
            offered = set(by_id[case_id]["elements"])
            self.assertEqual(set(spec["elements"]), offered,
                             f"{case_id}: oracle classifies elements the subject never named")

    def test_facts_needed_to_judge_stay_in_the_subject(self):
        # Irreversibility and control class are facts, not answers. Hiding them
        # would test guessing; the oracle must not be the only place they exist.
        f2 = next(c for c in SUBJECTS["cases"] if c["id"] == "F2-quiet-security-gate")
        self.assertEqual(f2["facts"].get("control_class"), "secrets")
        self.assertIs(f2["facts"].get("reversible"), False)

    def test_the_answer_format_demands_the_phase(self):
        # The phase bound is only checkable if the reviewer is told to report
        # the phase. An answer format that says "omit" makes the bound decoration.
        self.assertRegex(SUBJECTS["answer_format"]["stopped_at_phase"], r"(?i)required")


class PositiveControl(unittest.TestCase):
    def test_the_correct_answer_passes(self):
        self.assertEqual(evaluate.evaluate(perfect_answer(), ORACLE), [])

    def test_the_correct_answer_passes_even_under_strict(self):
        self.assertEqual(evaluate.evaluate(perfect_answer(), ORACLE, strict=True), [])


class NegativeControl(unittest.TestCase):
    """Corrupt one value; the same evaluator has to notice. This is the point."""

    def test_a_corrupted_interlock_class_is_caught(self):
        bad = copy.deepcopy(ORACLE)
        # The quiet security gate: flip the oracle from PROVE to DELETE.
        bad["cases"]["F2-quiet-security-gate"]["elements"][
            "pre-push credential scanner"]["class"] = "DELETE"
        problems = evaluate.evaluate(perfect_answer(), bad)
        self.assertTrue(problems, "a corrupted interlock passed unnoticed")
        self.assertEqual(problems[0]["kind"], "interlock")

    def test_a_wrong_answer_on_an_interlock_is_caught(self):
        answer = perfect_answer()
        answer["F2-quiet-security-gate"]["elements"]["pre-push credential scanner"] = "DELETE"
        problems = evaluate.evaluate(answer, ORACLE)
        self.assertTrue(problems, "deleting a quiet secrets control was accepted")
        self.assertIn(problems[0]["kind"], ("interlock", "forbidden"))

    def test_a_forbidden_class_is_caught_even_on_a_judgement_element(self):
        answer = perfect_answer()
        answer["F2-quiet-security-gate"]["elements"]["pre-push credential scanner"] = "DELETE"
        kinds = {p["kind"] for p in evaluate.evaluate(answer, ORACLE)}
        self.assertIn("forbidden", kinds)

    def test_a_judgement_element_differing_is_tolerated_by_default(self):
        # F3's wrapper is not an interlock: an agent arguing PROVE instead of
        # DELETE is being cautious, not wrong. Only --strict pins it.
        answer = perfect_answer()
        answer["F3-redundant-abstraction"]["elements"]["repository wrapper"] = "PROVE"
        self.assertEqual(evaluate.evaluate(answer, ORACLE), [])
        self.assertTrue(evaluate.evaluate(answer, ORACLE, strict=True),
                        "--strict must still notice the difference")

    def test_a_missing_case_is_not_silently_a_pass(self):
        answer = perfect_answer()
        del answer["F1-duplicate-status"]
        problems = evaluate.evaluate(answer, ORACLE)
        self.assertTrue(any(p["kind"] == "missing" for p in problems))

    def test_an_invented_class_is_rejected(self):
        answer = perfect_answer()
        answer["F2-quiet-security-gate"]["elements"]["pre-push credential scanner"] = "PROBABLY"
        self.assertTrue(any(p["kind"] == "not-a-class" for p in evaluate.evaluate(answer, ORACLE)))

    def test_reaching_a_forbidden_phase_is_caught(self):
        # F2's only element is PROVE and the case pins a ceiling, so phases 3-5
        # are out of reach twice over.
        answer = perfect_answer()
        answer["F2-quiet-security-gate"]["stopped_at_phase"] = 5
        self.assertTrue(any(p["kind"] == "phase" for p in evaluate.evaluate(answer, ORACLE)))


class ThePhaseMustFitTheClassification(unittest.TestCase):
    """The reachable phases follow from the answer, not from a scalar alone.

    Review showed the scalar bound wrong in both directions: a
    complete classification could claim phase 1, a case whose single element is
    PROVE could claim phase 5, and F1 was barred from phase 5 even though its
    reduced KEEP/MERGE flow may legitimately be taken that far. The bound is now
    derived per answer; these tests pin all three directions.
    """

    def test_a_complete_classification_cannot_have_stopped_at_phase_one(self):
        for case_id in ORACLE["cases"]:
            with self.subTest(case=case_id):
                answer = perfect_answer()
                answer[case_id]["stopped_at_phase"] = 1
                self.assertTrue(
                    any(p["kind"] == "phase" and p["case"] == case_id
                        for p in evaluate.evaluate(answer, ORACLE)),
                    "every element is classified, so phase 2 is finished")

    def test_nothing_to_reduce_means_phases_three_to_five_are_unreachable(self):
        # Make F3's only element PROVE: no KEEP, no MERGE, nothing to simplify.
        for phase in (3, 4, 5):
            with self.subTest(phase=phase):
                answer = perfect_answer()
                answer["F3-redundant-abstraction"]["elements"]["repository wrapper"] = "PROVE"
                answer["F3-redundant-abstraction"]["stopped_at_phase"] = phase
                self.assertTrue(
                    any(p["kind"] == "phase" for p in evaluate.evaluate(answer, ORACLE)),
                    f"phase {phase} with nothing classified KEEP or MERGE")

    def test_a_reduced_flow_may_legitimately_reach_automation(self):
        # The other direction, and the reason the old scalar was wrong: once the
        # duplication in F1 is merged away, taking what remains as far as phase 5
        # is a legitimate analysis, not a contract violation.
        answer = perfect_answer()
        answer["F1-duplicate-status"]["stopped_at_phase"] = 5
        self.assertEqual(evaluate.evaluate(answer, ORACLE), [],
                         "a KEEP/MERGE remainder must be allowed to reach automation")

    def test_a_hard_ceiling_still_binds_where_the_oracle_sets_one(self):
        pinned = [cid for cid, spec in ORACLE["cases"].items()
                  if "must_not_reach_phase" in spec]
        self.assertTrue(pinned, "no case pins a ceiling — this rule would be untested")
        for case_id in pinned:
            with self.subTest(case=case_id):
                answer = perfect_answer()
                answer[case_id]["stopped_at_phase"] = ORACLE["cases"][case_id]["must_not_reach_phase"]
                self.assertTrue(any(p["kind"] == "phase" and p["case"] == case_id
                                    for p in evaluate.evaluate(answer, ORACLE)))

    def test_a_wrong_negative_behaviour_is_caught(self):
        answer = perfect_answer()
        answer["N2-irreversible-no-rollback"]["behaviour"] = "classify-PROVE"
        problems = evaluate.evaluate(answer, ORACLE)
        self.assertTrue(any(p["kind"] == "behaviour" for p in problems))


class PhaseIsMandatory(unittest.TestCase):
    """An answer that hides where it stopped cannot be checked against a bound.

    The first evaluator only checked the phase when the answer volunteered it,
    and the answer format told reviewers to omit it. The bound was decoration.
    """

    def test_every_positive_case_requires_a_valid_phase(self):
        for case_id in ORACLE["cases"]:
            for invalid in (None, True, 0, 6, "2"):
                with self.subTest(case=case_id, phase=invalid):
                    answer = perfect_answer()
                    if invalid is None:
                        answer[case_id].pop("stopped_at_phase")
                    else:
                        answer[case_id]["stopped_at_phase"] = invalid
                    self.assertTrue(any(p["kind"] == "phase" and p["case"] == case_id
                                        for p in evaluate.evaluate(answer, ORACLE)))

    def test_missing_bounded_phase_is_not_a_pass(self):
        answer = perfect_answer()
        answer["F1-duplicate-status"].pop("stopped_at_phase", None)
        self.assertTrue(any(p["kind"] == "phase" for p in evaluate.evaluate(answer, ORACLE)))

    def test_boolean_phase_is_not_an_integer_phase(self):
        answer = perfect_answer()
        answer["F1-duplicate-status"]["stopped_at_phase"] = True
        self.assertTrue(any(p["kind"] == "phase" for p in evaluate.evaluate(answer, ORACLE)))


class OnlyWhatTheSubjectOffered(unittest.TestCase):
    """An answer may not classify things nobody asked about.

    Found in review: the evaluator walked the oracle and ignored
    everything else the answer contained, so a correct answer carrying an
    invented `production backup: DELETE` still passed. The forbidden-class rule
    caught it in exactly one fixture, the only one with `forbidden_classes` —
    which made the gap look narrower than it was.
    """

    def test_an_invented_element_is_caught(self):
        answer = perfect_answer()
        answer["F3-redundant-abstraction"]["elements"]["production backup"] = "DELETE"
        problems = evaluate.evaluate(answer, ORACLE)
        self.assertTrue(any(p["kind"] == "unknown-element" for p in problems),
                        "an invented element rode along inside a passing answer")

    def test_an_invented_case_is_caught(self):
        answer = perfect_answer()
        answer["F9-does-not-exist"] = {"elements": {"whatever": "DELETE"}, "stopped_at_phase": 5}
        problems = evaluate.evaluate(answer, ORACLE)
        self.assertTrue(any(p["kind"] == "unknown-case" for p in problems))

    def test_every_fixture_is_covered_not_just_the_one_with_forbidden_classes(self):
        # The old gap hid behind F2. Assert the rule bites in every case, so a
        # future fixture without `forbidden_classes` is not silently exempt.
        for case_id in ORACLE["cases"]:
            with self.subTest(case=case_id):
                answer = perfect_answer()
                answer[case_id]["elements"]["invented element"] = "DELETE"
                self.assertTrue(
                    any(p["kind"] == "unknown-element" and p["case"] == case_id
                        for p in evaluate.evaluate(answer, ORACLE)))

    def test_the_correct_answer_is_still_accepted(self):
        # The exactness must not turn into "everything fails".
        self.assertEqual(evaluate.evaluate(perfect_answer(), ORACLE), [])

    def test_a_negative_case_may_not_smuggle_elements(self):
        # A second review round: the exactness above only walked the positive
        # cases, so the same ride-along stayed open on the negative side.
        for case_id in ORACLE["negative_cases"]:
            with self.subTest(case=case_id):
                answer = perfect_answer()
                answer[case_id]["elements"] = {"production backup": "DELETE"}
                self.assertTrue(any(p["kind"] == "unexpected-field" and p["case"] == case_id
                                    for p in evaluate.evaluate(answer, ORACLE)))

    def test_a_negative_case_may_not_carry_a_phase(self):
        for case_id in ORACLE["negative_cases"]:
            with self.subTest(case=case_id):
                answer = perfect_answer()
                answer[case_id]["stopped_at_phase"] = 5
                self.assertTrue(any(p["kind"] == "unexpected-field" and p["case"] == case_id
                                    for p in evaluate.evaluate(answer, ORACLE)))

    def test_the_exact_mutant_from_the_review_is_caught(self):
        answer = perfect_answer()
        answer["N4-cosmetic"]["elements"] = {"production backup": "DELETE"}
        answer["N4-cosmetic"]["stopped_at_phase"] = 5
        self.assertTrue(evaluate.evaluate(answer, ORACLE),
                        "an invented DELETE inside a negative case still passed")


class PositiveCasesTakeExactlyTwoKeys(unittest.TestCase):
    """A ride-along field in a positive case used to pass, --strict included.

    The exact-set rule from the earlier round covered element names and case
    ids, and the negative cases were later pinned to their single key. Positive
    cases stayed open, so `recommendations: {...}` travelled along inside an
    otherwise correct answer. Raised in review.
    """

    def test_an_extra_field_is_rejected(self):
        for extra in ("recommendations", "notes", "elements_v2"):
            for strict in (False, True):
                with self.subTest(field=extra, strict=strict):
                    answer = perfect_answer()
                    answer["F3-redundant-abstraction"][extra] = {"production backup": "DELETE"}
                    problems = evaluate.evaluate(answer, ORACLE, strict=strict)
                    self.assertTrue(any(p["kind"] == "unexpected-field" for p in problems),
                                    f"{extra} rode along (strict={strict})")

    def test_the_two_legitimate_keys_are_accepted(self):
        self.assertEqual(evaluate.evaluate(perfect_answer(), ORACLE), [])


class TheOracleSchemaIsCheckedBeforeUse(unittest.TestCase):
    """A yardstick that is not itself measured is not a yardstick.

    Six shapes of broken answer key used to produce PASS rather than an error:
    an invalid class, a non-boolean interlock, an oracle with every interlock
    removed, an out-of-enum behaviour, nonsense in forbidden_classes and a
    non-integer phase ceiling.
    """

    def corrupt(self, mutate):
        bad = copy.deepcopy(ORACLE)
        mutate(bad)
        return bad

    def assert_refused(self, mutate, needle=""):
        with self.assertRaises(ValueError) as caught:
            evaluate.evaluate(perfect_answer(), self.corrupt(mutate))
        if needle:
            self.assertIn(needle, str(caught.exception))

    def test_an_invalid_class_is_refused(self):
        self.assert_refused(
            lambda b: b["cases"]["F1-duplicate-status"]["elements"]["chat status post"]
            .__setitem__("class", "PROBABLY"), "class")

    def test_a_non_boolean_interlock_is_refused(self):
        # A truthy string would pin silently and read as an interlock everywhere.
        self.assert_refused(
            lambda b: b["cases"]["F1-duplicate-status"]["elements"]["per-run log file"]
            .__setitem__("interlock", "yes"), "interlock")

    def test_an_oracle_pinning_nothing_is_refused(self):
        self.assert_refused(
            lambda b: [s.pop("interlock", None)
                       for c in b["cases"].values() for s in c["elements"].values()],
            "pins no interlock")

    def test_an_interlock_without_a_reason_is_refused(self):
        self.assert_refused(
            lambda b: b["cases"]["F2-quiet-security-gate"]["elements"]
            ["pre-push credential scanner"].__setitem__("why", "  "), "reason")

    def test_an_out_of_enum_behaviour_is_refused(self):
        self.assert_refused(
            lambda b: b["negative_cases"]["N4-cosmetic"].__setitem__("behaviour", "do-whatever"),
            "behaviour")

    def test_nonsense_in_forbidden_classes_is_refused(self):
        self.assert_refused(
            lambda b: b["cases"]["F2-quiet-security-gate"]
            .__setitem__("forbidden_classes", ["NOPE"]), "forbidden_classes")

    def test_a_non_integer_ceiling_is_refused(self):
        self.assert_refused(
            lambda b: b["cases"]["F2-quiet-security-gate"]
            .__setitem__("must_not_reach_phase", "three"), "must_not_reach_phase")

    def test_the_shipped_oracle_passes_its_own_schema(self):
        # Positive control: without it every assertion above would be satisfied
        # by a validator that rejects everything.
        evaluate.validate_oracle(ORACLE)


class OracleStructure(unittest.TestCase):
    """An answer key that cannot fail anything is refused, never passed."""

    def test_an_empty_oracle_is_refused(self):
        with self.assertRaises(ValueError):
            evaluate.evaluate(perfect_answer(), {})

    def test_an_oracle_without_cases_is_refused(self):
        with self.assertRaises(ValueError):
            evaluate.evaluate(perfect_answer(),
                              {"cases": {}, "negative_cases": ORACLE["negative_cases"]})

    def test_an_oracle_case_without_elements_is_refused(self):
        bad = copy.deepcopy(ORACLE)
        bad["cases"]["F3-redundant-abstraction"]["elements"] = {}
        with self.assertRaises(ValueError):
            evaluate.evaluate(perfect_answer(), bad)

    def test_an_empty_oracle_exits_two_on_the_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            answer = Path(tmp) / "answer.json"
            answer.write_text(json.dumps(perfect_answer()), encoding="utf-8")
            oracle = Path(tmp) / "oracle.json"
            oracle.write_text("{}", encoding="utf-8")
            result = run_cli(answer, "--oracle", oracle)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn("PASS", result.stdout)


class OracleObeysTheInterlocks(unittest.TestCase):
    """The answer key must obey the rules the skill imposes on everyone else.

    A wrong yardstick would teach all three agents the same wrong thing and
    still look like agreement — the worst outcome, because the agreement then
    becomes the evidence.
    """
    PROTECTED = {"security", "identity", "secrets", "production", "compliance",
                 "external-communication"}

    def _facts(self, case_id):
        return next(c for c in SUBJECTS["cases"] if c["id"] == case_id).get("facts", {})

    def test_no_protected_control_is_marked_delete(self):
        for case_id, spec in ORACLE["cases"].items():
            if self._facts(case_id).get("control_class") in self.PROTECTED:
                for element, s in spec["elements"].items():
                    self.assertNotEqual(s["class"], "DELETE",
                                        f"{case_id}/{element}: protected control marked DELETE")

    def test_nothing_irreversible_is_marked_delete(self):
        for case_id, spec in ORACLE["cases"].items():
            if self._facts(case_id).get("reversible") is False:
                for element, s in spec["elements"].items():
                    self.assertNotEqual(s["class"], "DELETE",
                                        f"{case_id}/{element}: irreversible marked DELETE")

    def test_a_delete_states_the_evidence_that_earns_it(self):
        for case_id, spec in ORACLE["cases"].items():
            if any(s["class"] == "DELETE" for s in spec["elements"].values()):
                self.assertTrue(spec.get("required_evidence", "").strip(),
                                f"{case_id} expects a DELETE but names no required_evidence")

    def test_a_delete_rests_on_a_probe_the_subject_says_was_carried_out(self):
        # Raised in review: SKILL.md says a proposed test is not a
        # passed test, while F3 expected DELETE on the strength of a probe that
        # the fixture only described as planned. Either the facts state that the
        # probe ran, or the class is PROVE. Nothing in between.
        #
        # Checked per element, not per case: subjects.json keys a fact about one
        # element by that element's name, so an unrelated fact elsewhere in the
        # same case cannot stand in for the evidence this class needs.
        for case_id, spec in ORACLE["cases"].items():
            facts = self._facts(case_id)
            for element, s in spec["elements"].items():
                if s["class"] != "DELETE":
                    continue
                fact = facts.get(element)
                # Typed, not matched. The substring version accepted "no safe
                # probe was carried out" — the negation contained the phrase it
                # denied, so a fixture could deny its evidence and still license
                # a DELETE. Raised in review.
                self.assertIsInstance(
                    fact, dict,
                    f"{case_id}/{element} expects a DELETE, so its fact must be an object "
                    "stating safe_probe and outcome, not prose")
                self.assertEqual(
                    fact.get("safe_probe"), "carried out",
                    f"{case_id}/{element}: a DELETE needs a probe that was carried out")
                self.assertEqual(
                    fact.get("outcome"), "pass",
                    f"{case_id}/{element}: a probe that ran but did not pass earns no DELETE")

    def test_the_element_keyed_fact_convention_holds_where_a_test_relies_on_it(self):
        # The two element-level rules above are only as good as the convention
        # they read. If a fixture stops keying its per-element facts by element
        # name, those rules would quietly check empty strings and pass.
        pinned = 0
        for case_id, spec in ORACLE["cases"].items():
            facts = self._facts(case_id)
            for element in spec["elements"]:
                if element in facts:
                    pinned += 1
        self.assertGreaterEqual(
            pinned, 6,
            "too few element-keyed facts — the per-element evidence rules would be vacuous")

    def test_an_unused_source_alone_never_earns_a_delete(self):
        # The counterpart: the skill forbids reading absence of use as proof of
        # uselessness, so a fixture whose only evidence is "nothing acted upon"
        # must stay PROVE — and pinned, or the rule is decoration.
        for case_id, spec in ORACLE["cases"].items():
            facts = self._facts(case_id)
            for element, s in spec["elements"].items():
                fact = str(facts.get(element, "")).lower()
                if "nothing acted upon" in fact:
                    self.assertEqual(s["class"], "PROVE",
                                     f"{case_id}/{element}: unused is not useless")
                    self.assertTrue(s.get("interlock"),
                                    f"{case_id}/{element}: the rule decides here, so pin it")

    def test_every_class_in_the_oracle_is_a_real_class(self):
        for case_id, spec in ORACLE["cases"].items():
            for element, s in spec["elements"].items():
                self.assertIn(s["class"], evaluate.VALID_CLASSES, f"{case_id}/{element}")

    def test_every_interlock_carries_its_reason(self):
        for case_id, spec in ORACLE["cases"].items():
            for element, s in spec["elements"].items():
                if s.get("interlock"):
                    self.assertTrue(s.get("why", "").strip(),
                                    f"{case_id}/{element}: interlock without a reason")

    def test_a_case_with_a_hard_rule_pins_it_as_an_interlock(self):
        # Not every case needs one: F3 is deliberately a judgement case, where
        # DELETE and PROVE are both defensible and forcing agreement would
        # reward copying. But wherever a hard rule decides — irreversible, or a
        # protected control class — the element must be pinned, or the rule is
        # decoration.
        for case_id, spec in ORACLE["cases"].items():
            facts = self._facts(case_id)
            hard = facts.get("reversible") is False or facts.get("control_class") in self.PROTECTED
            if hard:
                self.assertTrue(
                    any(s.get("interlock") for s in spec["elements"].values()),
                    f"{case_id} is decided by a hard rule but pins nothing as an interlock")

    def test_an_all_prove_case_bounds_the_phase_it_may_reach(self):
        # Raised in a second review round: F2 is entirely PROVE, and SKILL.md
        # keeps PROVE items out of phases 3 to 5 until they are decided — but
        # the oracle bound nothing, so `stopped_at_phase: 5` passed. Where every
        # element is undecided, the phase the analysis may reach is a rule, not
        # judgement, and a rule that nothing enforces is decoration.
        for case_id, spec in ORACLE["cases"].items():
            classes = {s["class"] for s in spec["elements"].values()}
            if classes == {"PROVE"}:
                bound = spec.get("must_not_reach_phase")
                self.assertIsNotNone(bound, f"{case_id}: all-PROVE case binds no phase")
                self.assertLessEqual(bound, 3,
                                     f"{case_id}: an undecided case may not reach simplification")
                self.assertTrue(spec.get("why_phase_bound", "").strip(),
                                f"{case_id}: phase bound without a reason")

    def test_the_bounded_phase_is_enforced_for_every_case_that_has_one(self):
        for case_id, spec in ORACLE["cases"].items():
            bound = spec.get("must_not_reach_phase")
            if bound is None:
                continue
            with self.subTest(case=case_id):
                answer = perfect_answer()
                answer[case_id]["stopped_at_phase"] = bound
                self.assertTrue(any(p["kind"] == "phase" and p["case"] == case_id
                                    for p in evaluate.evaluate(answer, ORACLE)))

    def test_the_suite_pins_enough_to_show_agreement_at_all(self):
        pinned = sum(1 for spec in ORACLE["cases"].values()
                     for s in spec["elements"].values() if s.get("interlock"))
        self.assertGreaterEqual(pinned, 3,
                                "too few interlocks to demonstrate cross-agent agreement")

    def test_the_oracle_carries_no_field_the_evaluator_never_reads(self):
        # A field nobody reads is a promise nobody keeps. Every top-level case
        # key must be consumed by evaluate.py or by a test in this file.
        known = {"elements", "must_not_reach_phase", "why_phase_bound",
                 "forbidden_classes", "required_evidence", "note"}
        for case_id, spec in ORACLE["cases"].items():
            self.assertLessEqual(set(spec), known, f"{case_id} carries unread fields")


class CommandLine(unittest.TestCase):
    def test_exit_codes_distinguish_pass_fail_and_broken(self):
        import contextlib
        import io
        # main() reports to stdout; swallow it so the suite output stays readable.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps(perfect_answer()), encoding="utf-8")
            self.assertEqual(evaluate.main([str(good)]), 0)

            bad_answer = perfect_answer()
            bad_answer["F2-quiet-security-gate"]["elements"][
                "pre-push credential scanner"] = "DELETE"
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps(bad_answer), encoding="utf-8")
            self.assertEqual(evaluate.main([str(bad)]), 1)

            self.assertEqual(evaluate.main([str(Path(tmp) / "missing.json")]), 2)

    def test_bad_cli_inputs_exit_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answer.json"
            for content in (None, "{broken", "[]"):
                with self.subTest(content=content):
                    if content is not None:
                        path.write_text(content, encoding="utf-8")
                    result = run_cli(path)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertNotIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
