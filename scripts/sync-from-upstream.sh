#!/bin/sh
# Mirror skills from the canonical source, or verify the mirror.
#
# The source of truth for every skill in this repository is a private
# upstream repository. Nothing inside a mirrored skill directory is
# edited here: a change is made, reviewed and merged upstream, then pulled in
# by this script, which records in upstream.lock the upstream commit each skill
# was taken from.
#
# Usage:
#   scripts/sync-from-upstream.sh <upstream-checkout> [skill ...]
#       Copy the named skills (default: every skill in upstream.lock) from the
#       checkout, verbatim, and rewrite upstream.lock. The checkout must be
#       clean under the copied paths, so the recorded commit is the truth.
#   scripts/sync-from-upstream.sh --check [<upstream-checkout>]
#       Verify the mirror. Without a checkout: every skill directory has a
#       SKILL.md, is listed in upstream.lock, carries a licence text if it
#       declares one, and its installed copies under .claude/skills/ and
#       .agents/skills/ match the skill root and contain nothing else. With a
#       checkout: additionally, every mirrored skill is byte-identical to the
#       checkout. Exit 1 on any difference.
set -eu

repo_root=$(cd "$(dirname "$0")/.." && pwd)
lock="$repo_root/upstream.lock"
status=0

# What an installed copy may contain, and nothing else. The check used to walk
# a hard-coded list of directories, so a loose file beside SKILL.md — LICENSE
# above all — was invisible: both copies could declare `license: MIT-0` and
# ship no terms while --check stayed green. The copies are what people install
# and what gets published, so they are the artefact a licence claim has to be
# true of. Same class of hole as the one reviewed upstream in claude-skills#36.
resource_files="LICENSE"
resource_dirs="references agents scripts templates"

fail() { echo "FAIL: $*" >&2; status=1; }

# The YAML frontmatter of a SKILL.md: the lines between the opening `---` and
# the next one. Empty when the file does not start with a fence.
#
# Trailing whitespace and CR are stripped before the fence is matched. A first
# line of `--- ` or a CRLF file would otherwise look like "no frontmatter at
# all", and a skill declaring a licence would sail past the check — fail-open,
# and invisible, because the file still renders correctly everywhere else.
frontmatter() { # $1 = SKILL.md
  [ -f "$1" ] || return 0
  awk '
    { sub(/\r$/, "") }
    NR == 1 { if ($0 !~ /^---[[:space:]]*$/) exit; next }
    /^---[[:space:]]*$/ { exit }
    { print }
  ' "$1"
}

# Does this skill declare a licence? Read from the frontmatter alone, and only
# at its top level.
#
# Both checks used to grep the whole file, so a fenced YAML example in the body
# — the kind a skill writes to explain frontmatter — made an unlicensed skill
# look licensed and blocked its sync. The reverse was open too: a quoted key
# (`"license": MIT-0`) is valid YAML and was not recognised at all.
#
# The anchor is deliberate: an indented `license:` nested under another key
# (`metadata:` say) is a different field with a different meaning, and reading
# it as the skill's licence would demand a LICENSE file nobody promised.
declares_license() { # $1 = SKILL.md
  frontmatter "$1" |
    grep -Eq '^("license"|'"'"'license'"'"'|license)[[:space:]]*:[[:space:]]*[^[:space:]]'
}

# Every entry directly inside a directory, one per line, including dotfiles and
# broken symlinks. `for e in "$d"/*` misses both: the glob skips names starting
# with a dot, and `[ -e ]` is false for a symlink whose target is gone.
entries_in() { # $1 = directory
  [ -d "$1" ] || return 0
  ( cd "$1" && find . -mindepth 1 -maxdepth 1 -print | sed 's|^\./||' )
}

# Skills recorded in upstream.lock, one per line.
locked_skills() {
  if [ -f "$lock" ]; then awk 'NF && $1 !~ /^#/ { print $1 }' "$lock"; fi
}

# Top-level directories that carry a SKILL.md.
present_skills() {
  for d in "$repo_root"/*/; do
    if [ -f "$d/SKILL.md" ]; then basename "$d"; fi
  done
}

check_self() {
  for s in $(present_skills); do
    if ! grep -q "^$s " "$lock" 2>/dev/null; then
      fail "$s is not recorded in upstream.lock"
    fi
    # A declared licence with no licence text is a claim the artefact does not
    # carry. Checked at the skill root; the copies inherit it through the diff.
    if declares_license "$repo_root/$s/SKILL.md" && [ ! -f "$repo_root/$s/LICENSE" ]; then
      fail "$s: SKILL.md frontmatter declares a license but $s/LICENSE is missing"
    fi
    for copy in "$repo_root/$s/.claude/skills/$s" "$repo_root/$s/.agents/skills/$s"; do
      [ -d "$copy" ] || continue
      for part in SKILL.md $resource_files $resource_dirs; do
        if [ -e "$repo_root/$s/$part" ]; then
          if ! diff -r -x __pycache__ "$repo_root/$s/$part" "$copy/$part" >/dev/null 2>&1; then
            fail "$s: ${copy#"$repo_root"/}/$part differs from the skill root"
          fi
        elif [ -e "$copy/$part" ]; then
          fail "$s: ${copy#"$repo_root"/}/$part has no counterpart in the skill root"
        fi
      done
      # Nothing in a copy that the skill root does not account for. Without
      # this, the loop above only ever looks at names it already knows.
      #
      # Read from a real listing, not a glob: dotfiles and broken symlinks used
      # to slip through both, because `*` skips names beginning with a dot and
      # `[ -e ]` is false for a symlink whose target is gone. Compared name by
      # name rather than as a substring of a joined string, which had accepted
      # a file literally called "LICENSE references".
      stray=$(entries_in "$copy" | while IFS= read -r base; do
        [ -n "$base" ] || continue
        known=no
        for allowed in SKILL.md $resource_files $resource_dirs; do
          if [ "$base" = "$allowed" ]; then known=yes; break; fi
        done
        if [ "$known" = no ]; then printf '%s\n' "$base"; fi
      done)
      # Reported out here, in the current shell, so `fail` reaches `status`.
      # A `fail` inside the pipeline above would run in a subshell and its
      # exit code would be thrown away — the classic way a gate reports a
      # problem and still ends green.
      if [ -n "$stray" ]; then
        printf '%s\n' "$stray" | while IFS= read -r base; do
          echo "FAIL: $s: ${copy#"$repo_root"/}/$base is not part of the skill root" >&2
        done
        status=1
      fi
    done
  done
  for s in $(locked_skills); do
    if [ ! -f "$repo_root/$s/SKILL.md" ]; then
      fail "$s is in upstream.lock but has no SKILL.md here"
    fi
  done
}

check_upstream() { # $1 = upstream checkout
  for s in $(locked_skills); do
    if [ ! -d "$1/$s" ]; then
      fail "$s does not exist in the upstream checkout $1"
      continue
    fi
    if ! diff -r -x __pycache__ -x .DS_Store "$1/$s" "$repo_root/$s" >/dev/null 2>&1; then
      fail "$s differs from upstream — run the sync, or the mirror was edited"
    fi
  done
}

sync() { # $1 = upstream checkout, rest = skills
  up=$1; shift
  if [ ! -d "$up/.git" ]; then echo "not a git checkout: $up" >&2; exit 2; fi
  command -v rsync >/dev/null || { echo "rsync is required to sync" >&2; exit 2; }
  head=$(git -C "$up" rev-parse HEAD)
  today=$(date -u +%Y-%m-%d)
  skills=${*:-$(locked_skills)}
  if [ -z "$skills" ]; then
    echo "nothing to sync: upstream.lock is empty and no skill was named" >&2; exit 2
  fi
  # PREFLIGHT — every named skill is checked before any of them is written.
  # The licence rule belongs here and not only in --check: a sync that copies a
  # skill declaring `license:` without a LICENSE file leaves the mirror in a
  # state its own gate then reports as broken, after the fact. Measured on a
  # throwaway tree: upstream drops the licence file but keeps the declaration,
  # the sync copies it happily, and only the next --check complains. Same shape
  # as the write-before-validation hole reviewed in claude-skills#36.
  for s in $skills; do
    if [ ! -f "$up/$s/SKILL.md" ]; then echo "no skill at $up/$s" >&2; exit 2; fi
    if [ -n "$(git -C "$up" status --porcelain -- "$s")" ]; then
      echo "upstream checkout is dirty under $s — commit or stash first; the lock must name a real commit" >&2
      exit 2
    fi
    if declares_license "$up/$s/SKILL.md" && [ ! -f "$up/$s/LICENSE" ]; then
      echo "refusing to sync $s: its SKILL.md frontmatter declares a license but $up/$s/LICENSE is missing — nothing was written" >&2
      exit 2
    fi
  done
  for s in $skills; do
    mkdir -p "$repo_root/$s"
    rsync -a --delete --exclude __pycache__ --exclude .DS_Store "$up/$s/" "$repo_root/$s/"
    echo "synced  $s  @ $head"
  done
  tmp="$lock.tmp"
  {
    echo "# skill  upstream-commit  synced-on   — generated by scripts/sync-from-upstream.sh"
    { locked_skills; for s in $skills; do echo "$s"; done; } | sort -u | while read -r s; do
      case " $skills " in
        *" $s "*) echo "$s $head $today" ;;
        *) grep "^$s " "$lock" ;;
      esac
    done
  } > "$tmp"
  mv "$tmp" "$lock"
  echo "wrote   upstream.lock"
}

case ${1:-} in
  --check)
    shift
    check_self
    if [ $# -gt 0 ]; then check_upstream "$1"; fi
    if [ "$status" -eq 0 ]; then echo "mirror ok"; fi
    ;;
  ""|-h|--help)
    sed -n '2,/^set -eu/{/^set -eu/!s/^# \{0,1\}//p;}' "$0"
    exit 2
    ;;
  *)
    sync "$@"
    ;;
esac
exit "$status"
