# public-skills

Public mirror of selected skills for Claude Code and Codex.

Every skill here is copied verbatim from its canonical source, a private
upstream repository. Changes are made and reviewed there and
then pulled into this repository; [`upstream.lock`](upstream.lock) records, per
skill, the upstream commit the copy was taken from. Nothing inside a skill
directory is edited here, so a pull request against one cannot be merged —
open an issue instead and the change will be made upstream and synced.

## Skills

| Skill | Runtime | What it does |
|---|---|---|
| [`first-principles-reduction`](first-principles-reduction/) | Claude Code / Codex | Applies the five-step reduction algorithm — question requirements, delete, simplify, accelerate, automate — in that fixed order to any subject (a process, a ruleset, code, an architecture, a document, a personal workflow) and classifies every element `DELETE` / `MERGE` / `KEEP` / `PROVE` with the evidence that justifies it. Read-only: it recommends, it never changes anything. Ships an acceptance fixture and an evaluator so that different agents can be checked for agreement wherever a hard rule decides. |

## Install

A skill is a folder with a `SKILL.md`. Copy it into your personal skills
directory:

```bash
cp -R first-principles-reduction ~/.claude/skills/   # Claude Code
cp -R first-principles-reduction ~/.codex/skills/    # Codex
```

Or symlink it so that `git pull` keeps it current:

```bash
ln -s "$(pwd)/first-principles-reduction" ~/.claude/skills/first-principles-reduction
```

Restart Claude Code. The skill then appears in the skills list and is used
when its `description` matches the request, or explicitly via
`/first-principles-reduction`.

Each skill directory also carries installed copies under
`.claude/skills/<name>/` and `.agents/skills/<name>/`, matching the upstream
layout, so the directory can serve as a project-level skill root as it is.

## Tests

`first-principles-reduction/tests/` pins the skill's contract and proves that
its acceptance evaluator can fail. `tests/` does the same for the mirror gate
itself: it deletes and corrupts files in a throwaway skeleton and requires
`sync-from-upstream.sh --check` to go red. A gate that cannot be made to fail
is not evidence that the mirror is true. CI runs all of it on every push:

```bash
sh scripts/sync-from-upstream.sh --check
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s first-principles-reduction/tests -v
```

## Updating from upstream

For maintainers with a checkout of the source repository:

```bash
scripts/sync-from-upstream.sh ../claude-skills                 # every skill in upstream.lock
scripts/sync-from-upstream.sh ../claude-skills some-new-skill  # add a skill
scripts/sync-from-upstream.sh --check ../claude-skills         # verify; exit 1 on drift
```

## License

Not chosen yet. Until a license file is added, no reuse rights are granted
beyond what GitHub's terms allow for public repositories.
