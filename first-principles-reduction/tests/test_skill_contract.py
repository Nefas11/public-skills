"""Pins the parts of SKILL.md that are load-bearing.

A judgement skill has no code to test. What it has is a contract, and the
failure mode is that someone editing it for length quietly drops an interlock
— the nine mandatory fields become seven, "no hits in four weeks is a signal,
never a proof" gets trimmed as wordy. Nothing breaks visibly; the skill just
starts clearing deletions it should not.

These tests are the mechanism that notices. They assert on substance, not on
wording, so a rewrite that keeps the meaning stays green.
"""
import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
TEMPLATE = (SKILL_DIR / "references" / "report-template.md").read_text(encoding="utf-8")
EXAMPLES = (SKILL_DIR / "references" / "examples.md").read_text(encoding="utf-8")

# The nine fields a DELETE/MERGE candidate must carry. Matched by a keyword
# that survives rephrasing, not by the full sentence.
CANDIDATE_FIELDS = [
    "element", "purpose", "evidence", "replacing protection", "blast radius",
    "reversibility", "detector", "safe probe", "stop",
]


class PhaseOrder(unittest.TestCase):
    """The order IS the skill. Any other order is a different, worse skill."""

    def test_five_phases_appear_in_algorithmic_order(self):
        headings = re.findall(r"^## Phase (\d) — (.+)$", SKILL, re.M)
        numbers = [int(n) for n, _ in headings]
        self.assertEqual(numbers, [0, 1, 2, 3, 4, 5], f"phases out of order: {headings}")

    def test_phase_names_match_the_algorithm(self):
        names = [t.lower() for _, t in re.findall(r"^## Phase (\d) — (.+)$", SKILL, re.M)]
        for expected, actual in zip(
            ["baseline", "question", "delete", "simplify", "accelerate", "automate"], names
        ):
            self.assertIn(expected, actual, f"phase heading '{actual}' lost '{expected}'")

    def test_later_phases_are_gated_on_earlier_ones(self):
        simplify = SKILL.split("## Phase 3")[1].split("## Phase 4")[0]
        self.assertRegex(simplify, r"[Nn]ever optimise a `?DELETE",
                         "phase 3 no longer forbids optimising a deletion candidate")
        accelerate = SKILL.split("## Phase 4")[1].split("## Phase 5")[0]
        self.assertRegex(accelerate, r"[Nn]ever accelerate by skipping",
                         "phase 4 no longer forbids buying speed by skipping a gate")


class Classes(unittest.TestCase):
    def test_all_four_classes_are_defined(self):
        for cls in ("DELETE", "MERGE", "KEEP", "PROVE"):
            self.assertIn(f"**`{cls}`**", SKILL, f"class {cls} is not defined in the table")

    def test_prove_is_offered_as_the_answer_to_missing_evidence(self):
        self.assertRegex(
            SKILL, r"say `PROVE` instead|is required|`PROVE`",
            "PROVE must be reachable as the honest answer when evidence is missing")


class HardInterlocks(unittest.TestCase):
    """These four sentences are why the skill can be trusted with deletion."""

    def test_irreversible_effects_get_no_autonomous_clearance(self):
        self.assertRegex(SKILL, r"[Ii]rreversible effect.{0,60}never.{0,40}clearance")

    def test_low_hit_count_alone_never_deletes_a_control(self):
        self.assertRegex(SKILL, r"never deleted on low hit-count alone")
        for control in ("[Ss]ecurity", "identity", "secrets", "production", "compliance"):
            self.assertRegex(SKILL, control, f"control class '{control}' dropped from the interlock")

    def test_four_quiet_weeks_is_a_signal_not_a_proof(self):
        self.assertRegex(SKILL, r"signal, never a proof")

    def test_a_gate_needs_falsification_under_control(self):
        self.assertRegex(SKILL, r"falsified under control")

    def test_the_read_only_promise_is_stated_and_mechanised(self):
        self.assertRegex(SKILL, r"[Yy]ou never execute")
        self.assertIn("git status --porcelain", SKILL,
                      "the byte-identity check is the only mechanical proof of read-only")


class CandidateFields(unittest.TestCase):
    def test_skill_demands_all_nine_fields(self):
        block = SKILL.split("**all nine fields**")[1].split("**Hard interlocks")[0].lower()
        for field in CANDIDATE_FIELDS:
            self.assertIn(field, block, f"mandatory candidate field '{field}' is missing")

    def test_report_template_offers_all_nine(self):
        lowered = TEMPLATE.lower()
        for field in CANDIDATE_FIELDS:
            self.assertIn(field, lowered,
                          f"report template has no row for '{field}' — the skill demands it")

    def test_an_incomplete_candidate_falls_back_to_prove(self):
        self.assertRegex(SKILL, r"not a candidate, it is `PROVE`")


class ReportBudget(unittest.TestCase):
    def test_budget_is_three_deletions_and_five_recommendations(self):
        self.assertRegex(SKILL, r"at most 3 prioritised deletion candidates and 5")

    def test_template_repeats_the_budget_where_it_is_applied(self):
        self.assertRegex(TEMPLATE, r"[Aa]t most three")


class Examples(unittest.TestCase):
    def test_every_fixture_domain_is_worked_through(self):
        for domain in ("process", "rule", "code", "personal workflow"):
            self.assertRegex(EXAMPLES, f"(?i){domain.replace(' ', '[ -]')}",
                             f"examples.md has no worked example for '{domain}'")

    def test_the_quiet_gate_example_never_reaches_delete(self):
        section = EXAMPLES.split("## 2 —")[1].split("## 3 —")[0]
        self.assertRegex(section, r"`PROVE`, never `DELETE`")


if __name__ == "__main__":
    unittest.main()
