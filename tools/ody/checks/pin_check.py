#!/usr/bin/env python3
# Does our tinygrad submodule contain the tinygrad commit comma's current master pins? (informational)
# comma's model code expects its own pin; pairing newer comma model code with an older tinygrad crashed
# the models on the device once. Prints OK / WARN lines; never fails the run.
import json
import subprocess
import urllib.request

TG = "tinygrad_repo"


def comma_pin(path: str) -> str | None:
  url = f"https://api.github.com/repos/commaai/openpilot/contents/{path}?ref=master"
  try:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"}), timeout=15) as r:
      return json.load(r).get("sha")
  except Exception as e:
    print(f"WARN could not read comma master's {path} pin: {e}")
    return None


def git(*args, cwd=None) -> subprocess.CompletedProcess:
  return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


ours = git("ls-tree", "HEAD", TG).stdout.split()[2]
pin = comma_pin(TG)
if pin:
  if git("cat-file", "-e", f"{pin}^{{commit}}", cwd=TG).returncode != 0:
    for url in ("https://github.com/tinygrad/tinygrad.git", "https://github.com/commaai/tinygrad.git"):
      git("fetch", "-q", "--filter=tree:0", url, pin, cwd=TG)
      if git("cat-file", "-e", f"{pin}^{{commit}}", cwd=TG).returncode == 0:
        break
  if git("cat-file", "-e", f"{pin}^{{commit}}", cwd=TG).returncode != 0:
    print(f"WARN tinygrad: could not fetch comma's pin {pin[:9]} to compare")
  elif git("merge-base", "--is-ancestor", pin, ours, cwd=TG).returncode == 0:
    print(f"OK   tinygrad {ours[:9]} contains comma master's pin {pin[:9]}")
  else:
    print(f"WARN tinygrad {ours[:9]} does NOT contain comma master's pin {pin[:9]}: "
          + "don't fold in comma model code (modeld/dmonitoringmodeld) without moving tinygrad too")
for sub in ("msgq_repo", "rednose_repo", "panda"):
  p = comma_pin(sub)
  mine = git("ls-tree", "HEAD", sub).stdout.split()
  if p and mine:
    same = "same as" if mine[2] == p else "differs from"
    print(f"info {sub:12s} {mine[2][:9]} {same} comma master {p[:9]}")
