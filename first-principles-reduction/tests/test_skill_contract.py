"""Pins the parts of SKILL.md that are load-bearing.

A judgement skill has no code to test. What it has is a contract, and the
failure mode is that someone editing it for length quietly drops an interlock
— the nine mandatory fields become seven, "no hits in four weeks is a signal,
never a proof" gets trimmed as wordy. Nothing breaks visibly; the skill just
starts clearing deletions it should not.

These tests are the mechanism that notices. They assert on substance, not on
wording, so a rewrite that keeps the meaning stays green.
"""
import json
import re
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
TEMPLATE = (SKILL_DIR / "references" / "report-template.md").read_text(encoding="utf-8")
EXAMPLES = (SKILL_DIR / "references" / "examples.md").read_text(encoding="utf-8")
FRONTMATTER = SKILL.split("---", 2)[1]
ORACLE = json.loads(
    (SKILL_DIR / "references" / "acceptance" / "oracle.json").read_text(encoding="utf-8"))

# Which worked example carries which acceptance case. Written out rather than
# guessed from the heading text, so a renamed heading fails loudly here instead
# of silently exempting a case from the comparison below.
EXAMPLE_SECTIONS = {
    "F1-duplicate-status": ("## 1 —", "## 2 —"),
    "F2-quiet-security-gate": ("## 2 —", "## 3 —"),
    "F3-redundant-abstraction": ("## 3 —", "## 4 —"),
    "F4-personal-briefing": ("## 4 —", "## The four misapplications"),
}


# One row per classified element: | <element> | `CLASS` | why |
# A table row that states a class. Deliberately generous about how the class is
# written, because Markdown is: up to three leading spaces still make a table
# row, and `PROVE`, **PROVE** and bare PROVE all render as the same claim to a
# reader. The strict backtick-only pattern let all four variants slip past the
# comparison — a row could contradict the oracle and count as neither a
# duplicate nor a stray. Emphasis is stripped from the element name for the
# same reason.
CLASS_ROW = re.compile(
    r"^[ ]{0,3}\|\s*(?P<element>[^|]+?)\s*\|"
    r"\s*(?P<open>`|\*\*|\*|_)?\s*(?P<cls>DELETE|MERGE|KEEP|PROVE)\s*(?P=open)?\s*\|",
    re.M)


def _clean(name):
    """Strip Markdown emphasis so `**source A**` and `source A` are one element."""
    return re.sub(r"^[*_`\s]+|[*_`\s]+$", "", name)


def example_section(case_id, text=None):
    start, end = EXAMPLE_SECTIONS[case_id]
    return (text if text is not None else EXAMPLES).split(start)[1].split(end)[0]


def example_classes(text=None):
    """Every class an example states, keyed by (case, element) -> list of classes.

    Read from the element table alone, never from prose. An earlier version
    accepted the class token appearing anywhere in the section, which made the
    check unfalsifiable: rewriting F3's heading to "class `PROVE`, not `DELETE`"
    left all tests green, because `DELETE` still occurred further down. A
    reviewer demonstrated that with a mutant.

    A *list*, not a single class, because the version after that fix still
    assigned `found[key] = cls` and so let a later row overwrite an earlier
    one. A third review round showed the consequence: an extra row stating
    the forbidden class, placed above the canonical row, left the comparison
    silent. Every occurrence is kept, and every occurrence is compared.
    """
    found = {}
    for case_id in EXAMPLE_SECTIONS:
        for match in CLASS_ROW.finditer(example_section(case_id, text)):
            key = (case_id, _clean(match.group("element")))
            found.setdefault(key, []).append(match.group("cls"))
    return found


def stray_class_rows(text=None):
    """Class rows in the file that lie outside every worked example.

    The comparison reads section by section, so a row placed before the first
    example or after the last one is never looked at — a third way for the
    file to state a class that nothing checks. Found while widening the two
    reported in review; the fix is the same idea: count what the file says, not
    only what the reader happens to visit.
    """
    body = EXAMPLES if text is None else text
    in_sections = sum(len(rows) for rows in example_classes(text).values())
    return len(CLASS_ROW.findall(body)) - in_sections


def compare_examples_to_oracle(text=None):
    """Return the disagreements between the examples and the answer key.

    A function rather than a test body so the mutation tests below can run the
    same comparison against a deliberately corrupted examples.md and require it
    to report something. A coupling that cannot be made to fail is decoration.
    """
    stated = example_classes(text)
    problems = []
    stray = stray_class_rows(text)
    if stray:
        problems.append(
            f"{stray} class row(s) outside every worked example — a class stated "
            "where nothing compares it")
    for case_id, spec in ORACLE["cases"].items():
        for element, s in spec["elements"].items():
            rows = stated.get((case_id, element), [])
            if not rows:
                problems.append(f"{case_id}/{element}: no class row in the example")
                continue
            # One element, one row. Two rows are a defect even when they agree:
            # the reader is handed two statements and has to guess which binds,
            # and a disagreeing pair is how a forbidden class slipped past.
            if len(rows) > 1:
                problems.append(
                    f"{case_id}/{element}: classified {len(rows)} times ({', '.join(rows)}) "
                    "— exactly one class row per element")
            for have in rows:
                if have != s["class"]:
                    problems.append(
                        f"{case_id}/{element}: example says {have}, oracle says {s['class']}")
    for (case_id, element), rows in stated.items():
        if element not in ORACLE["cases"][case_id]["elements"]:
            problems.append(
                f"{case_id}: example classifies unknown element '{element}' as {'/'.join(rows)}")
    return problems

# The nine fields a DELETE/MERGE candidate must carry. Matched by a keyword
# that survives rephrasing, not by the full sentence.
CANDIDATE_FIELDS = [
    "element", "purpose", "evidence", "replacing protection", "blast radius",
    "reversibility", "detector", "safe probe", "stop",
]


class Frontmatter(unittest.TestCase):
    """Three platforms parse this header; the strictest of them decides."""

    def test_name_matches_the_folder(self):
        self.assertRegex(FRONTMATTER, rf"(?m)^name:\s*{re.escape(SKILL_DIR.name)}\s*$")

    def test_description_is_a_block_scalar_or_quoted(self):
        # A plain scalar dies on the first ": " inside the text under a strict
        # YAML parser (ClawHub). Claude Code is lenient, which is how this went
        # unnoticed once. Only block scalars and quoted strings are safe.
        line = re.search(r"^description:\s*(.*)$", FRONTMATTER, re.M).group(1).strip()
        self.assertRegex(line, r'^(>-?|\|-?|"[^"]*"|\'[^\']*\')$',
                         "description must be a >- block scalar or a quoted string")

    def test_license_is_declared_and_shipped(self):
        self.assertRegex(FRONTMATTER, r"(?m)^license:\s*MIT-0\s*$")
        self.assertTrue((SKILL_DIR / "LICENSE").exists(), "LICENSE file missing next to SKILL.md")
        self.assertIn("MIT No Attribution", (SKILL_DIR / "LICENSE").read_text(encoding="utf-8"))


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
        # The earlier version of this test also accepted any mention of `PROVE`,
        # which made it impossible to fail. Only the instruction counts.
        self.assertRegex(SKILL, r"say `PROVE` instead",
                         "PROVE must be the stated answer when evidence is missing")


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

    def test_the_read_only_promise_is_stated(self):
        self.assertRegex(SKILL, r"[Yy]ou never execute")

    def test_the_baseline_is_both_recorded_and_compared(self):
        """Two roles, two checks — the earlier version only asked for the string.

        `git status --porcelain` appears twice: once in the read-only paragraph
        (record at the start, compare at the end) and once in Phase 0 (record
        it now). Deleting the first left the skill saying "record" and never
        "compare", which is half a mechanism — and the old `assertIn` stayed
        green because the second occurrence still matched. Found by removing
        each load-bearing sentence in turn and requiring the suite to go red;
        this was the only one that did not.
        """
        promise = SKILL.split("## The one failure mode")[0]
        self.assertIn("git status --porcelain", promise,
                      "the read-only paragraph no longer names the baseline command")
        self.assertRegex(promise, r"compare at the end",
                         "recording a baseline proves nothing unless it is compared")
        self.assertRegex(promise, r"byte-identical",
                         "the comparison must state what counts as unchanged")

        phase0 = SKILL.split("## Phase 0")[1].split("## Phase 1")[0]
        self.assertIn("git status --porcelain", phase0,
                      "Phase 0 no longer tells the analyst to record the baseline")

    def test_the_skill_never_disables_a_gate_to_probe_it(self):
        self.assertRegex(SKILL, r"never\s+disables a gate")


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

    def test_a_proposed_test_is_not_a_passed_test(self):
        self.assertRegex(SKILL, r"[Aa] proposed test\s+is not a passed test")


class ReportBudget(unittest.TestCase):
    def test_budget_is_three_deletions_and_five_recommendations(self):
        self.assertRegex(SKILL, r"at most 3 prioritised deletion candidates and 5")

    def test_template_repeats_the_budget_where_it_is_applied(self):
        self.assertRegex(TEMPLATE, r"[Aa]t most three")


class AcceptanceClaim(unittest.TestCase):
    """The acceptance section may not promise more than the evaluator checks.

    Raised in review: the evaluator compares classes and phases, never
    the nine evidence fields, so a claim that acceptance secures the evidence
    contract would be false. The honest boundary is stated, and pinned here.
    """

    def test_the_limit_of_the_check_is_stated(self):
        section = SKILL.split("## Acceptance")[1].split("## What this skill")[0]
        self.assertRegex(section, r"does \*\*not\*\* read the nine\s+fields",
                         "the acceptance section must say what it does not check")
        self.assertRegex(section, r"not a licence to skip the nine fields")

    def test_examples_are_named_as_carrying_the_evidence_burden(self):
        section = SKILL.split("## Acceptance")[1].split("## What this skill")[0]
        self.assertRegex(section, r"carried out")


class Portability(unittest.TestCase):
    """One folder serves Claude Code, Codex and ClawHub. Nothing may assume one."""

    def test_no_platform_prerequisite_is_claimed(self):
        self.assertRegex(SKILL, r"needs no API key")

    def test_maintainer_procedure_is_linked_not_inlined(self):
        self.assertIn("references/validation.md", SKILL)
        self.assertTrue((SKILL_DIR / "references" / "validation.md").exists())

    def test_codex_interface_file_is_present(self):
        self.assertTrue((SKILL_DIR / "agents" / "openai.yaml").exists(),
                        "agents/openai.yaml carries the Codex display metadata")


class ExamplesAgreeWithTheOracle(unittest.TestCase):
    """The prose and the answer key must say the same thing.

    examples.md used to *ask* the reader to keep both in step, and nothing
    checked it. That is how the two came apart in review: SKILL.md
    was tightened, the oracle followed, the worked example did not. A request
    in a paragraph is not a mechanism; this class is the mechanism.
    """

    def test_every_case_has_a_worked_example(self):
        self.assertEqual(set(EXAMPLE_SECTIONS), set(ORACLE["cases"]),
                         "a case without a worked example, or an example without a case")

    def test_every_element_is_named_in_its_example(self):
        for case_id, spec in ORACLE["cases"].items():
            section = example_section(case_id)
            for element in spec["elements"]:
                self.assertIn(element, section,
                              f"{case_id}: '{element}' is classified but never explained")

    def test_every_element_has_a_class_row_that_matches_the_oracle(self):
        self.assertEqual(compare_examples_to_oracle(), [])

    def test_every_element_is_covered_by_a_row(self):
        # Guards the comparison itself: if the row parser stopped matching, the
        # test above would pass on an empty set of statements.
        expected = sum(len(s["elements"]) for s in ORACLE["cases"].values())
        self.assertEqual(len(example_classes()), expected,
                         "an element is classified in the oracle but has no row in its example")

    def test_each_element_is_classified_exactly_once(self):
        # Counts rows, not keys. The key count above stays right even when one
        # element carries several contradicting rows — that is what hid the
        # overwrite bug found in the third review round.
        for (case_id, element), rows in example_classes().items():
            self.assertEqual(len(rows), 1,
                             f"{case_id}/{element}: {len(rows)} class rows ({', '.join(rows)})")

    def test_a_forbidden_class_is_never_stated_in_a_row(self):
        stated = example_classes()
        for case_id, spec in ORACLE["cases"].items():
            for forbidden in spec.get("forbidden_classes", []):
                for (cid, element), rows in stated.items():
                    if cid != case_id:
                        continue
                    # Every row, not the last one: an earlier forbidden row used
                    # to be overwritten by the canonical row and never seen.
                    for cls in rows:
                        self.assertNotEqual(cls, forbidden,
                                            f"{case_id}/{element}: example states forbidden {forbidden}")


class TheCouplingCanFail(unittest.TestCase):
    """Mutation tests. Without these the coupling above proves only that it agrees with itself.

    A second review round showed the previous version passing on a
    mutant: F3's heading changed from "class `DELETE`" to "class `PROVE`, not
    `DELETE`" and all 34 contract tests stayed green, because the class token
    still occurred somewhere in the section. Each test here builds a corrupted
    examples.md in memory and requires the comparison to report something.
    """

    def mutate_row(self, element, new_class):
        """Rewrite one element's class row, leaving the rest of the file alone."""
        pattern = re.compile(rf"(^\|\s*{re.escape(element)}\s*\|\s*)`\w+`", re.M)
        mutated, n = pattern.subn(rf"\g<1>`{new_class}`", EXAMPLES)
        self.assertEqual(n, 1, f"expected exactly one class row for '{element}', found {n}")
        return mutated

    def duplicate_row(self, element, smuggled_class):
        """Insert an extra row for `element` ABOVE its canonical row.

        The exact mutant from the third review round. The parser used
        to keep only the last row per element, so the smuggled class vanished
        behind the canonical one and the comparison stayed silent.
        """
        pattern = re.compile(rf"^\|\s*{re.escape(element)}\s*\|\s*`\w+`.*$", re.M)
        match = pattern.search(EXAMPLES)
        self.assertIsNotNone(match, f"no canonical row for '{element}'")
        smuggled = f"| {element} | `{smuggled_class}` | smuggled |"
        return EXAMPLES[:match.start()] + smuggled + "\n" + EXAMPLES[match.start():]

    def test_a_smuggled_forbidden_row_above_the_canonical_one_is_detected(self):
        # F2: the oracle forbids DELETE outright. An extra DELETE row above the
        # canonical PROVE row must not be swallowed.
        problems = compare_examples_to_oracle(
            self.duplicate_row("pre-push credential scanner", "DELETE"))
        self.assertTrue(problems, "a smuggled forbidden row went unnoticed")

    def test_a_smuggled_contradicting_row_above_the_canonical_one_is_detected(self):
        # F3: the canonical class is DELETE; a PROVE row above it contradicts.
        problems = compare_examples_to_oracle(
            self.duplicate_row("repository wrapper", "PROVE"))
        self.assertTrue(problems, "a smuggled contradicting row went unnoticed")

    def test_a_duplicate_row_is_reported_even_when_it_agrees(self):
        # Fail-closed: two rows for one element are a defect regardless, because
        # the reader cannot tell which one binds.
        problems = compare_examples_to_oracle(
            self.duplicate_row("repository wrapper", "DELETE"))
        self.assertTrue(any("classified 2 times" in p for p in problems),
                        f"an agreeing duplicate was accepted: {problems}")

    def test_every_markdown_spelling_of_a_class_is_seen(self):
        """Markdown has more than one way to write the same claim.

        Up to three leading spaces still make a table row, and `PROVE`,
        **PROVE**, *PROVE* and bare PROVE all read as the same statement. The
        backtick-only pattern saw none of them, so a contradicting row counted
        as neither a duplicate nor a stray. Raised in review; each
        spelling below was measured silent before the parser was widened.
        """
        canonical = "| repository wrapper | `DELETE` |"
        self.assertIn(canonical, EXAMPLES, "the canonical row moved — update this test")
        spellings = {
            "one leading space": " | repository wrapper | `PROVE` | smuggled |\n",
            "three leading spaces": "   | repository wrapper | `PROVE` | smuggled |\n",
            "bold": "| repository wrapper | **PROVE** | smuggled |\n",
            "italic": "| repository wrapper | *PROVE* | smuggled |\n",
            "plain": "| repository wrapper | PROVE | smuggled |\n",
            "emphasised element name": "| **repository wrapper** | `PROVE` | smuggled |\n",
        }
        for label, row in spellings.items():
            with self.subTest(spelling=label):
                mutated = EXAMPLES.replace(canonical, row + canonical, 1)
                self.assertTrue(compare_examples_to_oracle(mutated),
                                f"a {label} row contradicting the oracle went unnoticed")

    def test_a_row_after_the_last_example_is_detected(self):
        # Not reported by the review — found by asking where else the file can
        # state a class that the section-by-section reader never visits.
        mutated = EXAMPLES.replace(
            "## The four misapplications",
            "## The four misapplications\n\n| pre-push credential scanner | `DELETE` | smuggled |\n",
            1)
        self.assertTrue(compare_examples_to_oracle(mutated),
                        "a class row past the last example went unnoticed")

    def test_a_row_before_the_first_example_is_detected(self):
        mutated = "| repository wrapper | `PROVE` | smuggled |\n\n" + EXAMPLES
        self.assertTrue(compare_examples_to_oracle(mutated),
                        "a class row above the first example went unnoticed")

    def test_no_stray_rows_in_the_real_file(self):
        self.assertEqual(stray_class_rows(), 0)

    def test_the_unmutated_file_still_passes(self):
        # Positive control for the three mutants above. Without it they would
        # only prove that the comparison never returns an empty list.
        self.assertEqual(compare_examples_to_oracle(), [])

    def test_flipping_any_single_class_is_detected(self):
        for case_id, spec in ORACLE["cases"].items():
            for element, s in spec["elements"].items():
                other = next(c for c in ("DELETE", "MERGE", "KEEP", "PROVE") if c != s["class"])
                with self.subTest(case=case_id, element=element, to=other):
                    problems = compare_examples_to_oracle(self.mutate_row(element, other))
                    self.assertTrue(problems, f"{case_id}/{element}: flip to {other} went unnoticed")

    def test_prose_around_a_row_cannot_rescue_a_wrong_row(self):
        # The exact mutant from the review: contradicting prose next to a row
        # must not make a wrong row look right, and must not make a right row
        # look wrong either.
        mutated = self.mutate_row("repository wrapper", "PROVE")
        mutated = mutated.replace(
            "**Phase 2 — the class, and then the proof it demands:**",
            "**Phase 2 — class `DELETE`, with the proof the class demands:**")
        self.assertTrue(compare_examples_to_oracle(mutated),
                        "prose stating the right class hid a wrong row")

    def test_deleting_a_row_is_detected(self):
        mutated = re.sub(r"^\|\s*source E\s*\|.*$", "", EXAMPLES, count=1, flags=re.M)
        self.assertTrue(compare_examples_to_oracle(mutated), "a removed class row went unnoticed")

    def test_an_invented_row_is_detected(self):
        mutated = EXAMPLES.replace(
            "| source E | `KEEP` |",
            "| production backup | `DELETE` | invented |\n| source E | `KEEP` |", 1)
        self.assertTrue(compare_examples_to_oracle(mutated), "an invented class row went unnoticed")

    def test_the_unmutated_file_passes(self):
        # Positive control: without it the tests above would also pass on a
        # comparison that reports problems for everything.
        self.assertEqual(compare_examples_to_oracle(EXAMPLES), [])


class Examples(unittest.TestCase):
    def test_every_fixture_domain_is_worked_through(self):
        for domain in ("process", "rule", "code", "personal workflow"):
            self.assertRegex(EXAMPLES, f"(?i){domain.replace(' ', '[ -]')}",
                             f"examples.md has no worked example for '{domain}'")

    def test_a_forbidden_class_is_ruled_out_in_words_too(self):
        # The table carries the class; this carries the lesson. A reader who
        # skims the row still has to meet the sentence that says why the
        # tempting class is wrong. Generic over the oracle, so a second fixture
        # with forbidden_classes is covered the day it is added.
        for case_id, spec in ORACLE["cases"].items():
            for forbidden in spec.get("forbidden_classes", []):
                self.assertRegex(
                    example_section(case_id), rf"[Nn]ever `{forbidden}`",
                    f"{case_id}: the example never rules out {forbidden} in so many words")

    def test_the_quiet_source_example_never_reaches_delete_either(self):
        # Same rule, different domain: absence of use is not absence of need.
        section = EXAMPLES.split("## 4 —")[1].split("## The four misapplications")[0]
        self.assertRegex(section, r"`PROVE`, not `DELETE`")

    def test_the_deletion_example_says_its_probe_was_run(self):
        section = EXAMPLES.split("## 3 —")[1].split("## 4 —")[0]
        self.assertRegex(section, r"(?i)carried out",
                         "the DELETE example must show a probe that ran, not one that is planned")


class EveryLoadBearingSentenceIsGuarded(unittest.TestCase):
    """Delete each promise in turn; some test in this file must notice.

    The tests above assert that a sentence is present. This one asks the
    question they cannot ask about themselves: *would anything go red if it
    were gone?* A test whose assertion is satisfied by an unrelated occurrence
    elsewhere in the file looks identical to one that guards its sentence —
    until someone edits for length.

    Run once, in-process, against a copy of SKILL.md held in memory. Each
    pattern below is a sentence the skill cannot lose without becoming a
    different, weaker skill. Adding a promise to SKILL.md means adding it here.
    """

    CLAIMS = {
        "irreversible needs escalation":
            r"\*\*Irreversible effect ⇒ never an autonomous deletion clearance\.\*\* Escalate\.",
        "protected classes survive a low hit count":
            r"- Security, identity, secrets, production, compliance and external\n"
            r"  communication controls are \*\*never deleted on low hit-count alone\*\*\.",
        "four quiet weeks are a signal":
            r'- "No hits in four weeks" is a \*\*signal, never a proof\*\*\.',
        "a gate needs falsification under control": r"\*\*falsified under control\*\*",
        "the skill never executes": r"\*\*You never execute\.\*\*",
        "the baseline is compared, not just taken":
            r"If the subject is a repository, record `git status --porcelain` at the start\n"
            r"and compare at the end; it must be byte-identical\.",
        "phase 0 records the baseline":
            r"- For a repository: record `git status --porcelain` now, and keep the available\n"
            r"  diff or content baseline next to it\.",
        "a candidate carries nine fields": r"\*\*all nine fields\*\*",
        "an incomplete candidate is PROVE": r"not a candidate, it is `PROVE`",
        "the report budget": r"at most 3 prioritised deletion candidates and 5",
        "a proposed test is not a passed test": r"[Aa] proposed test\s+is not a passed test",
        "PROVE answers missing evidence": r"say `PROVE` instead",
        "the skill never disables a gate": r"never\s+disables a gate",
        "phase 3 does not polish a deletion": r"[Nn]ever optimise a `?DELETE",
        "phase 4 does not skip a gate": r"[Nn]ever accelerate by skipping",
        "acceptance states its limit": r"does \*\*not\*\* read the nine\s+fields",
        "acceptance is no licence to skip": r"not a licence to skip the nine fields",
        "no platform prerequisite": r"needs no API key",
    }

    # Tests that read SKILL.md. Re-run against the mutated text; at least one
    # must fail. Kept as a list so a new SKILL.md-reading class is easy to add.
    READERS = ("PhaseOrder", "Classes", "HardInterlocks", "CandidateFields",
               "ReportBudget", "Portability", "AcceptanceClaim", "Frontmatter")

    def _suite_notices(self, mutated):
        """True when some SKILL.md-reading test fails against `mutated`."""
        import unittest as ut
        module = sys.modules[__name__]
        original = module.SKILL
        module.SKILL = mutated
        try:
            suite = ut.TestSuite()
            loader = ut.TestLoader()
            for name in self.READERS:
                suite.addTests(loader.loadTestsFromTestCase(getattr(module, name)))
            result = ut.TestResult()
            suite.run(result)
            return bool(result.failures or result.errors)
        finally:
            module.SKILL = original

    def test_every_claim_is_load_bearing(self):
        unguarded = []
        for label, pattern in self.CLAIMS.items():
            match = re.search(pattern, SKILL)
            self.assertIsNotNone(
                match, f"'{label}': the pattern no longer matches SKILL.md — "
                       "either the sentence was rewritten or this guard is stale")
            mutated = SKILL[:match.start()] + SKILL[match.end():]
            if not self._suite_notices(mutated):
                unguarded.append(label)
        self.assertEqual(unguarded, [],
                         "these sentences can be deleted with the suite staying green")

    def test_the_unmutated_text_passes(self):
        # Positive control: without it, a broken harness that always reports
        # failure would make every claim above look guarded.
        self.assertFalse(self._suite_notices(SKILL),
                         "the reader tests fail on the unmodified SKILL.md")


# A pointer into a tracker: a pull-request or issue number. The samples in the
# tests below are assembled at runtime so that this file does not contain the
# thing it forbids.
TRACKER_REF = re.compile(
    r"\bPR\s*#?\s*\d+|(?<![\w/&#])#\d+\b|\b(?:pull request|issue)\s+#?\d+", re.I)


def shipped_files():
    """Every file a registry or a mirror publishes: the skill root, hidden paths left out."""
    for path in sorted(SKILL_DIR.rglob("*")):
        rel = path.relative_to(SKILL_DIR)
        hidden = any(part.startswith(".") or part == "__pycache__" for part in rel.parts)
        if path.is_file() and not hidden:
            yield rel, path.read_text(encoding="utf-8")


def tracker_references(text):
    return [m.group(0) for m in TRACKER_REF.finditer(text)]


class ShippedFilesAreSelfContained(unittest.TestCase):
    """The skill is published; a reader outside cannot follow a tracker number.

    The comments in these suites explain *why* a test exists. During review
    several of them came to say *where* a finding was raised instead — a number
    in a tracker the reader cannot see. Nothing noticed, because the scan for it
    had been run once, before the review rounds that introduced it.
    """

    def test_no_shipped_file_points_into_a_tracker(self):
        found = {}
        for rel, text in shipped_files():
            refs = tracker_references(text)
            if refs:
                found[str(rel)] = refs
        self.assertEqual(found, {}, "say what was learned, not where it was raised")

    def test_the_scan_can_fail(self):
        hash_ = "#"
        for sample in ("review of PR " + hash_ + "12",
                       "see " + hash_ + "7 for details",
                       "raised in pull " + "request 40",
                       "tracked as issue " + hash_ + "3"):
            self.assertTrue(tracker_references(sample), sample)

    def test_the_scan_leaves_ordinary_text_alone(self):
        # Positive control: headings, phases and case ids are not tracker pointers.
        for sample in ("## 3 — Redundant abstraction", "stops at phase 3",
                       "F3-redundant-abstraction", "2 of 5 elements are `PROVE`"):
            self.assertEqual(tracker_references(sample), [], sample)


if __name__ == "__main__":
    unittest.main()
