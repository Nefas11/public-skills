"""Functional tests for scripts/sync-from-upstream.sh.

The mirror check exists to prove that what this repository publishes is what
upstream reviewed. It had the hole its upstream counterpart was found to have
in claude-skills#36: `check_self` walked a hard-coded list of directories, so a
loose file beside SKILL.md never entered the comparison. Measured before the
fix, on a copy of this repository with a licence added by hand:

    LICENSE deleted from one installed copy   -> "mirror ok", exit 0
    LICENSE corrupted in one installed copy   -> "mirror ok", exit 0

Both should be exit 1. A copy may declare `license: MIT-0` in its frontmatter
and carry no terms, and the gate says nothing — and the copies are exactly what
people install and what gets published.

These tests run the real script against a throwaway skeleton in a tmp dir, so
the checked-in skills are never touched. The skeleton carries a licence even
while the mirrored skill does not yet, because the rule has to be under test
before the first licensed skill arrives, not after.

Stdlib only; run with:  python3 -m unittest discover -s tests -v
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "sync-from-upstream.sh"

SKILL = "demo-skill"
COPIES = (f".claude/skills/{SKILL}", f".agents/skills/{SKILL}")
LICENCE_TEXT = "MIT No Attribution\n\nCopyright 2026 Example\n"
SKILL_MD = """---
name: demo-skill
description: >-
  A fixture skill. Not published, not installed, only ever read by these tests.
license: MIT-0
---

# demo-skill

Body text.
"""


def run(script, *args):
    return subprocess.run(["sh", str(script), *args], capture_output=True, text=True)


class MirrorSkeleton(unittest.TestCase):
    """A tmp mirror: the real script, a lock file, one licensed skill, two copies."""

    licensed = True

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo)
        (self.repo / "scripts").mkdir()
        self.script = self.repo / "scripts" / "sync-from-upstream.sh"
        shutil.copy2(SCRIPT, self.script)

        root = self.repo / SKILL
        (root / "references").mkdir(parents=True)
        (root / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
        (root / "references" / "notes.md").write_text("# notes\n", encoding="utf-8")
        if self.licensed:
            (root / "LICENSE").write_text(LICENCE_TEXT, encoding="utf-8")

        for rel in COPIES:
            copy = root / rel
            copy.mkdir(parents=True)
            shutil.copy2(root / "SKILL.md", copy / "SKILL.md")
            shutil.copytree(root / "references", copy / "references")
            if self.licensed:
                shutil.copy2(root / "LICENSE", copy / "LICENSE")

        (self.repo / "upstream.lock").write_text(
            f"# skill  upstream-commit  synced-on\n{SKILL} 0123456789abcdef 2026-09-09\n",
            encoding="utf-8")

    def check(self):
        return run(self.script, "--check")

    def copy_path(self, which=0):
        return self.repo / SKILL / COPIES[which]

    def assert_ok(self):
        proc = self.check()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("mirror ok", proc.stdout)

    def assert_fails(self, needle):
        proc = self.check()
        self.assertEqual(proc.returncode, 1, f"--check must fail ({needle})\n{proc.stdout}")
        self.assertIn(needle, proc.stderr)
        self.assertNotIn("mirror ok", proc.stdout)


class TestCleanSkeletonPasses(MirrorSkeleton):
    """Positive control. Without it the negative ones prove only that it never passes."""

    def test_a_correct_mirror_is_green(self):
        self.assert_ok()


class TestLicenceTravelsWithTheCopies(MirrorSkeleton):
    """The regression from claude-skills#36, in this repository's own script."""

    def test_a_missing_licence_in_a_copy_is_drift(self):
        (self.copy_path() / "LICENSE").unlink()
        self.assert_fails("LICENSE")

    def test_a_corrupted_licence_in_a_copy_is_drift(self):
        (self.copy_path(1) / "LICENSE").write_text("All rights reserved.\n", encoding="utf-8")
        self.assert_fails("LICENSE")

    def test_a_licence_only_in_a_copy_is_drift(self):
        # The reverse direction: terms appear in a copy that the skill root
        # never granted. Nobody should be able to add a licence downstream.
        (self.repo / SKILL / "LICENSE").unlink()
        self.assert_fails("LICENSE")

    def test_declaring_a_licence_without_shipping_one_fails(self):
        for rel in COPIES:
            (self.repo / SKILL / rel / "LICENSE").unlink()
        (self.repo / SKILL / "LICENSE").unlink()
        self.assert_fails("declares a license")


class TestUnlicensedSkillStillPasses(MirrorSkeleton):
    """A skill that claims no licence must not be forced to carry a file.

    Today's mirrored skill is exactly that, so a rule that demanded LICENSE
    unconditionally would turn the whole gate red for the wrong reason.
    """

    licensed = False

    def test_no_declaration_no_requirement(self):
        # The declaration has to go from the root AND both copies: dropping it
        # in one place only is ordinary drift, which the gate would report for
        # a different reason and hide what this test is actually about.
        for path in (self.repo / SKILL / "SKILL.md",
                     *(self.repo / SKILL / rel / "SKILL.md" for rel in COPIES)):
            path.write_text(path.read_text(encoding="utf-8").replace("license: MIT-0\n", ""),
                            encoding="utf-8")
        self.assert_ok()

    def test_a_declaration_without_a_file_still_fails(self):
        # Same skeleton, declaration left in place: the fixture proves the rule
        # keys on the declaration and not on the file's absence alone.
        self.assert_fails("declares a license")


class TestCopiesCarryNothingExtra(MirrorSkeleton):
    """The old loop only ever looked at names it already knew."""

    def test_a_stray_file_in_a_copy_is_drift(self):
        (self.copy_path() / "README.md").write_text("stray\n", encoding="utf-8")
        self.assert_fails("not part of the skill root")

    def test_a_stray_directory_in_a_copy_is_drift(self):
        extra = self.copy_path(1) / "templates"
        extra.mkdir()
        (extra / "t.md").write_text("x\n", encoding="utf-8")
        self.assert_fails("has no counterpart in the skill root")


class TestTheInventoryIsReal(MirrorSkeleton):
    """"Contains nothing else" has to mean the actual contents.

    Raised in review of public-skills#1. The first version walked `"$copy"/*`
    and compared each name against a joined string. Three ways past it, each
    measured returning `mirror ok` before the fix:

      * `*` never matches a name beginning with a dot,
      * `[ -e ]` is false for a symlink whose target is gone, so a broken one
        was skipped entirely,
      * a substring test accepted a file literally called "LICENSE references",
        because that string occurs inside the list of allowed names.
    """

    def test_a_dotfile_in_a_copy_is_drift(self):
        (self.copy_path() / ".extra.md").write_text("synthetic\n", encoding="utf-8")
        self.assert_fails("not part of the skill root")

    def test_a_dot_directory_in_a_copy_is_drift(self):
        extra = self.copy_path() / ".extra"
        extra.mkdir()
        (extra / "notes.md").write_text("synthetic\n", encoding="utf-8")
        self.assert_fails("not part of the skill root")

    def test_a_broken_symlink_in_a_copy_is_drift(self):
        (self.copy_path() / "stray.md").symlink_to("/nonexistent/target")
        self.assert_fails("not part of the skill root")

    def test_a_name_containing_two_allowed_names_is_drift(self):
        # "LICENSE references" is neither LICENSE nor references. The old
        # substring test saw it inside " SKILL.md LICENSE references ... ".
        (self.copy_path() / "LICENSE references").write_text("synthetic\n", encoding="utf-8")
        self.assert_fails("not part of the skill root")

    def test_a_newline_in_a_filename_is_not_two_allowed_names(self):
        """A regression I introduced, caught in the second mirror review.

        A newline is a legal character in a POSIX filename. The glob this gate
        started with saw "LICENSE\\nreferences" as one entry and rejected it.
        Replacing the glob with `find -print | while read` split that single
        file into two records — `LICENSE` and `references` — both of them
        allowed names, and the gate said `mirror ok`. Counting with find itself
        never splits.
        """
        (self.copy_path() / "LICENSE\nreferences").write_text("synthetic\n", encoding="utf-8")
        self.assert_fails("not part of the skill root")

    def test_a_license_directory_is_not_a_license_file(self):
        """`diff -r file dir` compares the file against dir/file.

        Replacing the installed LICENSE with a directory holding a LICENSE of
        the same content read as identical, and whatever else sat beside it in
        that directory rode along. The entry type is checked before the
        contents are worth comparing. Raised in the third mirror review.
        """
        licence = self.copy_path() / "LICENSE"
        contents = licence.read_bytes()
        licence.unlink()
        licence.mkdir()
        (licence / "LICENSE").write_bytes(contents)
        (licence / "UNRELATED.txt").write_text("synthetic payload\n", encoding="utf-8")
        self.assert_fails("wrong type")

    def test_a_symlinked_copy_is_refused(self):
        """The inventory and the content checks disagreed about symlinks.

        `diff` follows a symlinked copy directory; `find` does not follow one
        passed as its starting path, so the inventory saw zero children while
        the diffs walked the target. Extra files behind the link were invisible.
        One policy now: an installed copy must be a real directory.
        """
        original = self.copy_path()
        target = original.parent / ".copy-content"
        original.rename(target)
        original.symlink_to(".copy-content", target_is_directory=True)
        self.assert_fails("symlink")

    def test_a_symlinked_copy_is_refused_even_with_extra_content(self):
        original = self.copy_path()
        target = original.parent / ".copy-content"
        original.rename(target)
        original.symlink_to(".copy-content", target_is_directory=True)
        (target / "unexpected.md").write_text("synthetic payload\n", encoding="utf-8")
        self.assert_fails("symlink")

    def test_a_dangling_symlink_with_an_allowed_name_is_drift(self):
        # `templates` is an allowed name, so the inventory waved it through,
        # and the counterpart check used `-e`, which is false for a link whose
        # target is gone. Neither half saw it. It is still an entry that the
        # skill root does not have.
        self.assertFalse((self.repo / SKILL / "templates").exists(),
                         "precondition: the skill root has no templates/")
        (self.copy_path() / "templates").symlink_to("missing-synthetic-target")
        self.assert_fails("counterpart")

    def test_the_untouched_copies_still_pass(self):
        # Positive control for the four above: an inventory rule that rejects
        # everything would satisfy them all and break the repository.
        self.assert_ok()


class TestLicenceComesFromTheFrontmatter(MirrorSkeleton):
    """A fenced example in the body is documentation, not metadata.

    Both licence checks used to grep the whole SKILL.md. A skill explaining
    frontmatter — exactly what a skill about skills would do — was therefore
    read as licensed, and its sync refused with nothing wrong. The opposite
    direction was open too: `"license": MIT-0` is valid YAML and matched
    nothing, so a real declaration without a LICENSE file passed.
    """

    licensed = False

    def write_skill(self, frontmatter_line, body_example=False):
        text = "---\nname: demo-skill\ndescription: >-\n  A fixture.\n"
        if frontmatter_line:
            text += frontmatter_line + "\n"
        text += "---\n\n# demo-skill\n"
        if body_example:
            text += "\nExample only:\n\n```yaml\nlicense: MIT-0\n```\n"
        for path in (self.repo / SKILL / "SKILL.md",
                     *(self.repo / SKILL / rel / "SKILL.md" for rel in COPIES)):
            path.write_text(text, encoding="utf-8")

    def test_a_body_example_does_not_demand_a_licence_file(self):
        self.write_skill(None, body_example=True)
        self.assert_ok()

    def test_a_plain_declaration_still_demands_one(self):
        self.write_skill("license: MIT-0")
        self.assert_fails("declares a license")

    def test_a_double_quoted_key_is_recognised(self):
        self.write_skill('"license": MIT-0')
        self.assert_fails("declares a license")

    def test_a_single_quoted_key_is_recognised(self):
        self.write_skill("'license': MIT-0")
        self.assert_fails("declares a license")

    def test_a_fence_with_trailing_whitespace_still_counts(self):
        """Found by probing the parser rather than by the review.

        A first line of `--- ` renders as frontmatter everywhere, but the exact
        string comparison read it as "no frontmatter", so the declaration below
        it was never seen. Fail-open, and invisible in the rendered file.
        """
        self.write_skill("license: MIT-0")
        for path in (self.repo / SKILL / "SKILL.md",
                     *(self.repo / SKILL / rel / "SKILL.md" for rel in COPIES)):
            path.write_text(path.read_text(encoding="utf-8").replace("---\n", "--- \n", 1),
                            encoding="utf-8")
        self.assert_fails("declares a license")

    def test_crlf_line_endings_still_count(self):
        # Same shape: a CRLF file left `---\r` in the comparison and the whole
        # frontmatter went unread.
        self.write_skill("license: MIT-0")
        for path in (self.repo / SKILL / "SKILL.md",
                     *(self.repo / SKILL / rel / "SKILL.md" for rel in COPIES)):
            path.write_bytes(path.read_text(encoding="utf-8").replace("\n", "\r\n")
                             .encode("utf-8"))
        self.assert_fails("declares a license")

    def test_a_nested_map_is_undecidable(self):
        # `metadata:` with an indented block under it is nesting this parser
        # does not model. An earlier version answered "not the skill's licence"
        # and let it through, which was a guess: the same shape could carry a
        # top-level licence one line further down. Under the whitelist the
        # honest answer is "cannot read", and the message says what to change.
        self.write_skill("metadata:\n  license: MIT-0")
        self.assert_fails("cannot read")

    def test_a_value_on_the_next_line_is_refused_not_ignored(self):
        """Valid YAML this script cannot read must be refused, never assumed.

        `license:` with MIT-0 on the following line is a real declaration — a
        YAML parser reads it as such. The line-oriented check saw no value on
        the key's line and answered "no licence", so a skill declaring MIT-0
        without shipping the text passed the preflight. Raised in the second
        mirror review; the answer is a third state, not a wider regex.
        """
        self.write_skill("license:\n  MIT-0")
        self.assert_fails("cannot read")

    def test_a_flow_map_is_refused_not_ignored(self):
        for path in (self.repo / SKILL / "SKILL.md",
                     *(self.repo / SKILL / rel / "SKILL.md" for rel in COPIES)):
            path.write_text("---\n{name: demo-skill, description: fixture, license: MIT-0}\n"
                            "---\n\n# demo-skill\n", encoding="utf-8")
        self.assert_fails("cannot read")

    def test_an_indented_root_map_is_refused_not_ignored(self):
        for path in (self.repo / SKILL / "SKILL.md",
                     *(self.repo / SKILL / rel / "SKILL.md" for rel in COPIES)):
            path.write_text("---\n  name: demo-skill\n  description: fixture\n"
                            "  license: MIT-0\n---\n\n# demo-skill\n", encoding="utf-8")
        self.assert_fails("cannot read")

    def test_a_block_scalar_description_is_still_readable(self):
        """The shape the real mirrored skill uses must not become undecidable.

        Positive control for the three refusals above: a rule that called every
        multi-line frontmatter unreadable would satisfy them all and refuse the
        skill this repository actually publishes.
        """
        for path in (self.repo / SKILL / "SKILL.md",
                     *(self.repo / SKILL / rel / "SKILL.md" for rel in COPIES)):
            path.write_text("---\nname: demo-skill\ndescription: >-\n  A fixture that spans\n"
                            "  two lines.\nlicense: MIT-0\n---\n\n# demo-skill\n",
                            encoding="utf-8")
        for path in (self.repo / SKILL / "LICENSE",
                     *(self.repo / SKILL / rel / "LICENSE" for rel in COPIES)):
            path.write_text(LICENCE_TEXT, encoding="utf-8")
        self.assert_ok()

    def test_an_explicit_key_is_refused_not_ignored(self):
        """`? license` / `: MIT-0` is a real declaration YAML reads as MIT-0.

        The previous version named three bad shapes and let everything else
        fall through to "no licence" — unbounded by construction. The parser
        now validates a whitelist: anything outside the supported grammar is
        undecidable. Raised in the third mirror review.
        """
        for path in (self.repo / SKILL / "SKILL.md",
                     *(self.repo / SKILL / rel / "SKILL.md" for rel in COPIES)):
            path.write_text("---\nname: demo-skill\ndescription: fixture\n"
                            "? license\n: MIT-0\n---\n\n# demo-skill\n", encoding="utf-8")
        self.assert_fails("cannot read")

    def test_an_escaped_key_is_refused_not_ignored(self):
        # `"license"` spells license. A quoted key containing a backslash
        # is outside the grammar and therefore undecidable, rather than "not a
        # licence key".
        for path in (self.repo / SKILL / "SKILL.md",
                     *(self.repo / SKILL / rel / "SKILL.md" for rel in COPIES)):
            path.write_text('---\nname: demo-skill\n"\\u006cicense": MIT-0\n'
                            "---\n\n# demo-skill\n", encoding="utf-8")
        self.assert_fails("cannot read")

    def test_json_inside_a_block_scalar_is_content_not_structure(self):
        """A false rejection I introduced, caught in the same review.

        `description: |` opens a block scalar; its indented body is a string.
        Matching `{` across every frontmatter line turned a JSON snippet in a
        description into an "indented root map" and refused a perfectly valid
        unlicensed skill. The parser now tracks block-scalar context.
        """
        for path in (self.repo / SKILL / "SKILL.md",
                     *(self.repo / SKILL / rel / "SKILL.md" for rel in COPIES)):
            path.write_text('---\nname: demo-skill\ndescription: |\n'
                            '  {"mode": "read-only"}\n---\n\n# demo-skill\n', encoding="utf-8")
        self.assert_ok()

    def test_a_declaration_plus_the_file_passes(self):
        # Positive control: the rule must accept the legitimate combination.
        self.write_skill("license: MIT-0")
        for path in (self.repo / SKILL / "LICENSE",
                     *(self.repo / SKILL / rel / "LICENSE" for rel in COPIES)):
            path.write_text(LICENCE_TEXT, encoding="utf-8")
        self.assert_ok()


class TestOrdinaryDriftStillCaught(MirrorSkeleton):
    """Guard the checks that existed before, so this change adds without removing."""

    def test_a_mutated_skill_md_is_drift(self):
        skill = self.copy_path() / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\nsmuggled\n", encoding="utf-8")
        self.assert_fails("SKILL.md differs")

    def test_a_mutated_reference_is_drift(self):
        (self.copy_path(1) / "references" / "notes.md").write_text("# tampered\n",
                                                                   encoding="utf-8")
        self.assert_fails("references differs")

    def test_a_skill_missing_from_the_lock_is_drift(self):
        (self.repo / "upstream.lock").write_text("# skill  upstream-commit  synced-on\n",
                                                 encoding="utf-8")
        self.assert_fails("not recorded in upstream.lock")


class TestSyncValidatesBeforeWriting(unittest.TestCase):
    """The sync path needs the licence rule too, not only --check.

    Found while widening the review findings from claude-skills#36 to this
    repository. Measured before the fix, on a throwaway tree: upstream drops the
    LICENSE file but keeps `license:` in its frontmatter, the sync copies the
    skill happily, and only the *next* --check reports the mirror as broken.
    A gate that runs after the write describes damage instead of preventing it.
    """

    SKILL = "demo-skill"
    SKILL_MD = ("---\nname: demo-skill\ndescription: >-\n  A fixture.\n"
                "license: MIT-0\n---\n\n# demo-skill\n")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

        # A fake upstream checkout: git-backed, because the sync insists on one.
        self.upstream = self.tmp / "upstream"
        (self.upstream / self.SKILL / "references").mkdir(parents=True)
        (self.upstream / self.SKILL / "SKILL.md").write_text(self.SKILL_MD, encoding="utf-8")
        (self.upstream / self.SKILL / "LICENSE").write_text(LICENCE_TEXT, encoding="utf-8")
        (self.upstream / self.SKILL / "references" / "n.md").write_text("x\n", encoding="utf-8")
        self.git("init", "-q", "-b", "main")
        self.commit("init")

        self.mirror = self.tmp / "mirror"
        (self.mirror / "scripts").mkdir(parents=True)
        shutil.copy2(SCRIPT, self.mirror / "scripts" / "sync-from-upstream.sh")
        (self.mirror / "upstream.lock").write_text(
            f"# skill  upstream-commit  synced-on\n{self.SKILL} 0000000 2026-01-01\n",
            encoding="utf-8")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.upstream), *args], check=True,
                       capture_output=True, text=True)

    def commit(self, message):
        self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "commit", "-q", "-m", message)

    def sync(self):
        return subprocess.run(
            ["sh", str(self.mirror / "scripts" / "sync-from-upstream.sh"),
             str(self.upstream), self.SKILL],
            capture_output=True, text=True, cwd=str(self.mirror))

    def test_a_licensed_skill_syncs(self):
        proc = self.sync()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.mirror / self.SKILL / "LICENSE").is_file())

    def test_a_body_example_does_not_block_the_sync(self):
        """The same confusion on the write path, from the other side.

        Measured before the fix: an unlicensed skill carrying a fenced YAML
        example in its body made the sync exit 2 with nothing wrong. Raised in
        review of public-skills#1.
        """
        self.assertEqual(self.sync().returncode, 0, "precondition: a clean first sync")
        skill = self.upstream / self.SKILL / "SKILL.md"
        text = skill.read_text(encoding="utf-8").replace("license: MIT-0\n", "")
        text += "\nExample only:\n\n```yaml\nlicense: MIT-0\n```\n"
        skill.write_text(text, encoding="utf-8")
        (self.upstream / self.SKILL / "LICENSE").unlink()
        self.commit("unlicensed, but documents frontmatter in its body")

        proc = self.sync()
        self.assertEqual(proc.returncode, 0,
                         f"a body example blocked an unlicensed skill\n{proc.stderr}")

    def test_a_quoted_declaration_is_refused_too(self):
        # `"license": MIT-0` is valid YAML. The old grep matched only the bare
        # key, so a real declaration without a licence file went through.
        self.assertEqual(self.sync().returncode, 0, "precondition: a clean first sync")
        skill = self.upstream / self.SKILL / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8")
                         .replace("license: MIT-0", '"license": MIT-0'), encoding="utf-8")
        (self.upstream / self.SKILL / "LICENSE").unlink()
        self.commit("quoted key, no licence file")

        proc = self.sync()
        self.assertEqual(proc.returncode, 2, "a quoted declaration was not recognised")
        self.assertIn("refusing to sync", proc.stderr)

    def mirror_state(self):
        """Every file under the mirror, with contents and the lock file.

        The earlier version of the test below compared one file — the licence —
        and called that "nothing was written". A refused sync must leave the
        whole tree alone, so the whole tree is what gets compared.
        """
        state = {}
        for path in sorted(self.mirror.rglob("*")):
            if path.is_file():
                state[str(path.relative_to(self.mirror))] = path.read_bytes()
        return state

    def assert_refused_without_touching(self, before, code=2):
        proc = self.sync()
        self.assertEqual(proc.returncode, code, f"the sync must refuse\n{proc.stderr}")
        self.assertNotIn("synced", proc.stdout, "it wrote despite refusing")
        after = self.mirror_state()
        self.assertEqual(after, before, "the refused sync changed files")
        return proc

    def test_undecidable_frontmatter_is_refused_before_any_write(self):
        """The sync-side guard, exercised directly.

        Senox measured the gap: removing `unreadable_frontmatter` from the sync
        preflight left every test green, because only the check path was
        covered. Each shape below is a real declaration or a shape the parser
        cannot read, and each must stop the sync with the mirror untouched.
        """
        shapes = {
            "value on the next line": "name: demo-skill\nlicense:\n  MIT-0\n",
            "explicit key": "name: demo-skill\n? license\n: MIT-0\n",
            "escaped key": 'name: demo-skill\n"\\u006cicense": MIT-0\n',
            "flow map": "{name: demo-skill, license: MIT-0}\n",
            "indented root map": "  name: demo-skill\n  license: MIT-0\n",
        }
        for label, frontmatter in shapes.items():
            with self.subTest(shape=label):
                self.assertEqual(self.sync().returncode, 0, "precondition: a clean sync")
                before = self.mirror_state()
                root = self.upstream / self.SKILL
                (root / "SKILL.md").write_text(f"---\n{frontmatter}---\n\n# demo-skill\n",
                                               encoding="utf-8")
                (root / "LICENSE").unlink()
                self.commit(f"synthetic: {label}")

                proc = self.sync()
                self.assertEqual(proc.returncode, 2, f"{label} did not stop the sync")
                self.assertIn("cannot read", proc.stderr)
                self.assertEqual(self.mirror_state(), before, f"{label} changed the mirror")
                self.assertTrue((self.mirror / self.SKILL / "LICENSE").is_file(),
                                f"{label} deleted the mirrored licence")

                # Restore for the next shape.
                (root / "SKILL.md").write_text(self.SKILL_MD, encoding="utf-8")
                (root / "LICENSE").write_text(LICENCE_TEXT, encoding="utf-8")
                self.commit(f"restore after {label}")

    def test_a_supported_unlicensed_skill_still_syncs(self):
        # Positive control for the five refusals above: a parser that called
        # everything undecidable would satisfy them all and mirror nothing.
        self.assertEqual(self.sync().returncode, 0, "precondition: a clean sync")
        root = self.upstream / self.SKILL
        (root / "SKILL.md").write_text(
            '---\nname: demo-skill\ndescription: |\n  {"mode": "read-only"}\n'
            "---\n\n# demo-skill\n", encoding="utf-8")
        (root / "LICENSE").unlink()
        self.commit("unlicensed, JSON inside a block scalar")

        proc = self.sync()
        self.assertEqual(proc.returncode, 0,
                         f"a valid unlicensed skill was refused\n{proc.stderr}")

    def test_a_declaration_without_a_licence_file_is_refused_before_any_write(self):
        self.assertEqual(self.sync().returncode, 0, "precondition: a clean first sync")
        before = self.mirror_state()

        (self.upstream / self.SKILL / "LICENSE").unlink()
        self.commit("licence removed upstream, declaration left behind")

        proc = self.assert_refused_without_touching(before)
        self.assertIn("refusing to sync", proc.stderr)

    def test_no_refusal_path_writes_anything(self):
        """Every way the sync can abort must leave the mirror untouched.

        Senox asked for "abgewiesener Sync → keine Dateien verändert" as a
        general rule, not only for the licence case. Each branch below aborts
        for a different reason; all of them are checked against the full tree.
        """
        self.assertEqual(self.sync().returncode, 0, "precondition: a clean first sync")
        before = self.mirror_state()

        with self.subTest(reason="declared licence without the file"):
            (self.upstream / self.SKILL / "LICENSE").unlink()
            self.commit("licence gone")
            self.assert_refused_without_touching(before)
            (self.upstream / self.SKILL / "LICENSE").write_text(LICENCE_TEXT, encoding="utf-8")
            self.commit("licence back")

        with self.subTest(reason="dirty upstream checkout"):
            (self.upstream / self.SKILL / "SKILL.md").write_text(
                self.SKILL_MD + "\nuncommitted\n", encoding="utf-8")
            self.assert_refused_without_touching(before)
            self.commit("tidy up")

        with self.subTest(reason="named skill missing upstream"):
            proc = subprocess.run(
                ["sh", str(self.mirror / "scripts" / "sync-from-upstream.sh"),
                 str(self.upstream), "no-such-skill"],
                capture_output=True, text=True, cwd=str(self.mirror))
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(self.mirror_state(), before)

        with self.subTest(reason="upstream is not a git checkout"):
            plain = self.tmp / "plain"
            (plain / self.SKILL).mkdir(parents=True)
            (plain / self.SKILL / "SKILL.md").write_text(self.SKILL_MD, encoding="utf-8")
            proc = subprocess.run(
                ["sh", str(self.mirror / "scripts" / "sync-from-upstream.sh"),
                 str(plain), self.SKILL],
                capture_output=True, text=True, cwd=str(self.mirror))
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(self.mirror_state(), before)

    def test_an_accepted_sync_does_write(self):
        # Positive control for the rule above: a gate that refuses everything
        # would satisfy every subTest and never mirror anything.
        before = self.mirror_state()
        proc = self.sync()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("synced", proc.stdout)
        self.assertNotEqual(self.mirror_state(), before, "a clean sync wrote nothing")


class TestThisRepositoryIsInSync(unittest.TestCase):
    """What is committed here is a release artefact — keep it true."""

    def test_repo_check_is_green(self):
        proc = run(SCRIPT, "--check")
        self.assertEqual(proc.returncode, 0,
                         f"run `sh scripts/sync-from-upstream.sh <upstream>`\n{proc.stderr}")


if __name__ == "__main__":
    unittest.main()
