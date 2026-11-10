"""Nothing this repository publishes may point into a tracker the reader cannot open.

The skills come from a private upstream, and review there leaves its traces in
comments: "raised in review of <repo>#<n>". Such a pointer is dead for every
reader of this mirror and names things that are not public. It slipped in twice
— once through a synced skill, once through this repository's own gate — each
time because the scan for it had been run once, before the review rounds that
wrote the comments.

The one tracker a reader *can* open is this repository's own, so
`public-skills#<n>` stays allowed. A bare "PR" plus number is refused as
ambiguous: write the qualified form.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

FOREIGN_REF = re.compile(r"(?<![\w.-])(?!public-skills#)[A-Za-z][\w.-]*#\d+\b")
BARE_PR = re.compile(r"\bPR\s*#\d+", re.I)


def pointers(text):
    return [m.group(0) for rx in (FOREIGN_REF, BARE_PR) for m in rx.finditer(text)]


def published_files():
    for path in sorted(REPO.rglob("*")):
        rel = path.relative_to(REPO)
        if not path.is_file() or ".git" in rel.parts or "__pycache__" in rel.parts:
            continue
        try:
            yield rel, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


class TestNoPointerIntoAPrivateTracker(unittest.TestCase):
    def test_every_published_file_is_clean(self):
        found = {}
        for rel, text in published_files():
            hits = pointers(text)
            if hits:
                found[str(rel)] = hits
        self.assertEqual(found, {}, "say what was learned, not where it was raised")

    def test_the_scan_can_fail(self):
        # Assembled at runtime so that this file does not contain what it forbids.
        hash_ = "#"
        for sample in ("reviewed in some-repo" + hash_ + "36",
                       "see org.tools" + hash_ + "7",
                       "raised in review of PR " + hash_ + "12"):
            self.assertTrue(pointers(sample), sample)

    def test_this_repository_s_own_tracker_stays_allowed(self):
        hash_ = "#"
        for sample in ("raised in review of public-skills" + hash_ + "1",
                       "## 3 — a heading", "colour " + hash_ + "1a2b3c", "&" + hash_ + "39;"):
            self.assertEqual(pointers(sample), [], sample)


if __name__ == "__main__":
    unittest.main()
