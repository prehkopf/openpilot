#!/usr/bin/env python3
"""Every LFS pointer at HEAD must exist on the LFS host in .lfsconfig, or the device installer 404s on checkout.

usage: lfs_host.py [REPO] [REV]
"""
import configparser
import json
import re
import subprocess
import sys
import urllib.request

POINTER = re.compile(r"version https://git-lfs\.github\.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize (\d+)\n")


def git(repo: str, *args: str, data: bytes | None = None) -> bytes:
  return subprocess.run(("git", "-C", repo, *args), input=data, check=True, capture_output=True).stdout


def pointers(repo: str, rev: str) -> dict[str, tuple[str, int]]:
  # LFS pointers are ~130 bytes; read only the small blobs
  small = {}
  for line in git(repo, "ls-tree", "-r", "-l", "-z", rev).decode().split("\0"):
    if not line:
      continue
    meta, path = line.split("\t", 1)
    _, kind, sha, size = meta.split()
    if kind == "blob" and size != "-" and 100 <= int(size) <= 200:
      small[sha] = path
  out = git(repo, "cat-file", "--batch", data="\n".join(small).encode() + b"\n").decode("utf-8", "replace")
  found = {}
  for header, body in re.findall(r"^([0-9a-f]{40} blob \d+)\n(.*?)(?=^[0-9a-f]{40} blob |\Z)", out, re.S | re.M):
    m = POINTER.match(body)
    if m:
      found[small[header.split()[0]]] = (m.group(1), int(m.group(2)))
  return found


def missing(url: str, objs: list[tuple[str, int]]) -> set[str]:
  bad = set()
  for i in range(0, len(objs), 100):
    req = urllib.request.Request(
      url.rstrip("/") + "/objects/batch",
      data=json.dumps({"operation": "download", "transfers": ["basic"],
                       "objects": [{"oid": o, "size": s} for o, s in objs[i:i + 100]]}).encode(),
      headers={"Accept": "application/vnd.git-lfs+json", "Content-Type": "application/vnd.git-lfs+json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
      bad |= {o["oid"] for o in json.load(r)["objects"] if "actions" not in o}
  return bad


def main() -> int:
  repo = sys.argv[1] if len(sys.argv) > 1 else "."
  rev = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
  cfg = configparser.ConfigParser()
  cfg.read_string(git(repo, "show", f"{rev}:.lfsconfig").decode())
  url = cfg["lfs"]["url"].strip()
  ptrs = pointers(repo, rev)
  bad = missing(url, sorted(set(ptrs.values())))
  print(f"{len(ptrs)} LFS pointers at {rev}, host {url}")
  for path, (oid, _) in sorted(ptrs.items()):
    if oid in bad:
      print(f"MISSING {path} ({oid[:12]})")
  if bad:
    print("Store these in git (see .gitattributes) or point them at objects the host has.")
  return int(bool(bad))


if __name__ == "__main__":
  sys.exit(main())
