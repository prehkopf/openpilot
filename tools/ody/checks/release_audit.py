#!/usr/bin/env python3
"""Release audit: what changed between the published branch and this build that unit tests miss.

usage: release_audit.py <repo root> <base ref, e.g. origin/ody-test>

FAIL (exit 1):
  - a params key that exists on both sides changed type in params_keys.h. Upstream cherry-picks can do this
    (comma #39079 turned LastGPSPosition from JSON text into bytes and broke sunnypilot's map features).
    Every reader of that key is listed so they can be checked.
  - a commit in either repo (openpilot, or opendbc between the old and new pin) authored as root or with an
    empty email: the WSL git identity was not set for that repo.
WARN (exit 0): params keys added or removed.
"""
import re
import subprocess
import sys

KEY_RE = re.compile(r'\{"(\w+)",\s*\{([^}]*)\}')


def git(repo, *args):
  return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def param_types(repo, ref):
  src = git(repo, "show", f"{ref}:openpilot/common/params_keys.h")
  types = {}
  for key, attrs in KEY_RE.findall(src):
    kinds = [a.strip() for a in attrs.split(",")]
    types[key] = kinds[1] if len(kinds) > 1 else "STRING"
  return types


def bad_authors(repo, rev_range):
  out = git(repo, "log", "--format=%h%x09%an%x09%ae%x09%s", rev_range)
  bad = []
  for line in out.splitlines():
    sha, name, email, subject = line.split("\t", 3)
    if name == "root" or not email or email.startswith("root@"):
      bad.append(f"{sha} {name} <{email}> {subject}")
  return bad


def main():
  root, base = sys.argv[1], sys.argv[2]
  fails, warns = [], []

  old, new = param_types(root, base), param_types(root, "HEAD")
  for key in sorted(old.keys() & new.keys()):
    if old[key] != new[key]:
      readers = git(root, "grep", "-n", key, "HEAD", "--", "*.py", "*.cc", "*.h").strip().splitlines()
      fails.append(f"param {key} changed type {old[key]} -> {new[key]}; check every reader:\n    " +
                   "\n    ".join(r.split(":", 1)[1] for r in readers[:20]))
  added, removed = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
  if added:
    warns.append(f"params added: {', '.join(added)}")
  if removed:
    warns.append(f"params removed: {', '.join(removed)}")

  for author in bad_authors(root, f"{base}..HEAD"):
    fails.append(f"openpilot commit with no real author identity: {author}")
  old_pin = git(root, "rev-parse", f"{base}:opendbc_repo").strip()
  new_pin = git(root, "rev-parse", "HEAD:opendbc_repo").strip()
  if old_pin != new_pin:
    try:
      for author in bad_authors(f"{root}/opendbc_repo", f"{old_pin}..{new_pin}"):
        fails.append(f"opendbc commit with no real author identity: {author}")
    except subprocess.CalledProcessError:
      warns.append(f"opendbc author check skipped: {old_pin[:9]}..{new_pin[:9]} not in {root}/opendbc_repo")

  for w in warns:
    print(f"WARN {w}")
  for f in fails:
    print(f"FAIL {f}")
  print(f"{len(fails)} failures, {len(warns)} warnings")
  return 1 if fails else 0


if __name__ == "__main__":
  sys.exit(main())
