"""Proves the acceptance evaluator can actually fail.

Senox' blocker on PR #18: the first version of the fixtures put `expected` next
to the subject and only validated that the answer key was internally legal. A
deliberately wrong key stayed green, because nothing compared a real answer
against it. "The tests pass" said nothing about classification.

The four things he asked for, and where each lives:

  1. subjects-only input, no expected/why/interlock  -> Separation below
  2. mechanical comparison against a separate oracle -> PositiveControl
  3. negative control: corrupt an expected value, the SAME evaluator must go red
                                                     -> NegativeControl
  4. positive control with the intact oracle is green -> PositiveControl

The negative control is the load-bearing one. Without it this file would only
prove that the evaluator agrees with itself.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import evaluate  # noqa: E402

ACCEPT = SKILL_DIR / "references" / "acceptance"
SUBJECTS = json.loads((ACCEPT / "subjects.json").read_text(encoding="utf-8"))
ORACLE = json.loads((ACCEPT / "oracle.json").read_text(encoding="utf-8"))

# The answer a correct run produces — derived from the oracle on purpose. It is
# the thing under test in PositiveControl and the thing we perturb everywhere
# else; writing it out by hand would only add a second place to get it wrong.
def perfect_answer(oracle=ORACLE):
    answer = {}
    for case_id, spec in oracle["cases"].items():
        answer[case_id] = {
            "elements": {el: s["class"] for el, s in spec["elements"].items()},
        }
        if "must_not_reach_phase" in spec:
            answer[case_id]["stopped_at_phase"] = spec["must_not_reach_phase"] - 1
    for case_id, spec in oracle["negative_cases"].items():
        answer[case_id] = {"behaviour": spec["behaviour"]}
    return answer


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
        answer = perfect_answer()
        answer["F1-duplicate-status"]["stopped_at_phase"] = 5   # automated the duplication
        self.assertTrue(any(p["kind"] == "phase" for p in evaluate.evaluate(answer, ORACLE)))

    def test_a_wrong_negative_behaviour_is_caught(self):
        answer = perfect_answer()
        answer["N2-irreversible-no-rollback"]["behaviour"] = "classify-PROVE"
        problems = evaluate.evaluate(answer, ORACLE)
        self.assertTrue(any(p["kind"] == "behaviour" for p in problems))


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

    def test_the_suite_pins_enough_to_show_agreement_at_all(self):
        pinned = sum(1 for spec in ORACLE["cases"].values()
                     for s in spec["elements"].values() if s.get("interlock"))
        self.assertGreaterEqual(pinned, 3,
                                "too few interlocks to demonstrate cross-agent agreement")


class CommandLine(unittest.TestCase):
    def test_exit_codes_distinguish_pass_fail_and_broken(self):
        import contextlib
        import io
        import tempfile
        # main() reports to stdout; swallow it so the suite output stays readable.
        with contextlib.redirect_stdout(io.StringIO()), tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps(perfect_answer()), encoding="utf-8")
            self.assertEqual(evaluate.main([str(good)]), 0)

            bad_answer = perfect_answer()
            bad_answer["F2-quiet-security-gate"]["elements"][
                "pre-push credential scanner"] = "DELETE"
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps(bad_answer), encoding="utf-8")
            self.assertEqual(evaluate.main([str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
