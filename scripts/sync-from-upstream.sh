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

# Licence status of a skill, read from its frontmatter alone.
#
#   0 = declares a licence
#   1 = declares none
#   2 = the frontmatter uses a shape this script cannot read with confidence
#
# The third answer is the point. An earlier version knew only yes and no, and
# answered "no" to every syntax it did not match — so `license:` with the value
# on the next line, an indented root map, or a flow map `{name: x, license: y}`
# all counted as unlicensed, and a skill declaring MIT-0 without shipping the
# text sailed through the preflight. All three are valid YAML and a real parser
# reads MIT-0 from each.
#
# This is POSIX sh with no YAML parser available, so instead of guessing, the
# unreadable shapes are named and refused. Fail-closed beats a wrong "no".
license_status() { # $1 = SKILL.md
  fm=$(frontmatter "$1")
  [ -n "$fm" ] || return 1

  # A flow map holds the whole mapping on one line; the line-oriented checks
  # below cannot see into it.
  if printf '%s\n' "$fm" | grep -Eq '^[[:space:]]*\{'; then return 2; fi
  # An indented first key means the whole root map is nested one level in, and
  # every anchor below would miss it.
  if printf '%s\n' "$fm" | grep -Eq '^[[:space:]]+[^[:space:]#-]' &&
     ! printf '%s\n' "$fm" | grep -Eq '^[^[:space:]#]'; then return 2; fi
  # `license:` with nothing after it: the value is on a following line, or the
  # key is empty. Both are readable by YAML and not by this grep.
  if printf '%s\n' "$fm" |
       grep -Eq '^("license"|'"'"'license'"'"'|license)[[:space:]]*:[[:space:]]*$'; then
    return 2
  fi
  if printf '%s\n' "$fm" |
       grep -Eq '^("license"|'"'"'license'"'"'|license)[[:space:]]*:[[:space:]]*[^[:space:]]'; then
    return 0
  fi
  return 1
}

# True when the skill declares a licence. Callers must handle status 2 (an
# unreadable frontmatter) separately — treating it as "no licence" is exactly
# the bug this replaced.
declares_license() { # $1 = SKILL.md
  license_status "$1"
  [ "$?" -eq 0 ]
}

unreadable_frontmatter() { # $1 = SKILL.md
  license_status "$1"
  [ "$?" -eq 2 ]
}

# How many entries directly inside $1 are NOT one of the allowed names, and a
# printable listing of them.
#
# Counted by find itself rather than by reading its output line by line. A
# newline is a legal character in a POSIX filename, and a single file called
# "LICENSE<LF>references" arrived at a `while read` loop as two records, both
# of them allowed names — so one forbidden entry read as two permitted ones and
# the gate said "mirror ok". The previous glob caught that case; the line-based
# rewrite lost it. Counting never splits.
stray_count() { # $1 = directory, rest: allowed names
  dir=$1; shift
  [ -d "$dir" ] || { echo 0; return 0; }
  set -- "$@"
  exclude=""
  for allowed in "$@"; do
    exclude="$exclude ! -name $allowed"
  done
  # shellcheck disable=SC2086 — the expansion is the point: one -name per word.
  find "$dir" -mindepth 1 -maxdepth 1 $exclude -exec printf 'x\n' \; | wc -l | tr -d ' '
}

stray_listing() { # $1 = directory, rest: allowed names — for the message only
  dir=$1; shift
  exclude=""
  for allowed in "$@"; do
    exclude="$exclude ! -name $allowed"
  done
  # shellcheck disable=SC2086
  find "$dir" -mindepth 1 -maxdepth 1 $exclude -print0 | tr '\0' '\n'
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
    if unreadable_frontmatter "$repo_root/$s/SKILL.md"; then
      fail "$s: SKILL.md frontmatter uses a YAML shape this script cannot read (flow map, indented root map, or a key whose value is on the next line) — its licence status is undecidable, so it is refused rather than assumed unlicensed"
    elif declares_license "$repo_root/$s/SKILL.md" && [ ! -f "$repo_root/$s/LICENSE" ]; then
      fail "$s: SKILL.md frontmatter declares a license but $s/LICENSE is missing"
    fi
    for copy in "$repo_root/$s/.claude/skills/$s" "$repo_root/$s/.agents/skills/$s"; do
      [ -d "$copy" ] || continue
      for part in SKILL.md $resource_files $resource_dirs; do
        # `-e` alone is false for a symlink whose target is gone, so a dangling
        # link carrying an allowed name used to be invisible in both branches:
        # the source had no counterpart, and the copy "did not exist" either.
        # It is an entry, and it does not belong there.
        if [ -e "$repo_root/$s/$part" ] || [ -L "$repo_root/$s/$part" ]; then
          if ! diff -r -x __pycache__ "$repo_root/$s/$part" "$copy/$part" >/dev/null 2>&1; then
            fail "$s: ${copy#"$repo_root"/}/$part differs from the skill root"
          fi
        elif [ -e "$copy/$part" ] || [ -L "$copy/$part" ]; then
          fail "$s: ${copy#"$repo_root"/}/$part has no counterpart in the skill root"
        fi
      done
      # Nothing in a copy that the skill root does not account for. Without
      # this, the loop above only ever looks at names it already knows.
      #
      # Counted by find, never read line by line: a newline inside a filename
      # would otherwise split one forbidden entry into two allowed names.
      n_stray=$(stray_count "$copy" SKILL.md $resource_files $resource_dirs)
      if [ "$n_stray" -gt 0 ]; then
        fail "$s: ${copy#"$repo_root"/} holds $n_stray entr$([ "$n_stray" = 1 ] && echo y || echo ies) not part of the skill root:"
        stray_listing "$copy" SKILL.md $resource_files $resource_dirs | sed 's/^/         /' >&2
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
    if unreadable_frontmatter "$up/$s/SKILL.md"; then
      echo "refusing to sync $s: its SKILL.md frontmatter uses a YAML shape this script cannot read (flow map, indented root map, or a key whose value is on the next line). The licence status is undecidable and assuming 'unlicensed' would mirror a skill whose terms nobody checked — nothing was written" >&2
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
