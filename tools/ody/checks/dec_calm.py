#!/usr/bin/env python3
# Prepush check: calmer stop-and-go DEC (Gwinnett SP1). Replays this build's DEC over route 24 (2026-10-25), which has
# the uphill stop-and-go into the Acworth rail crossing where DEC cycled every ~6 s.
#   1. With the new hold switched off, the replay must reproduce the van's recorded DEC exactly (the harness is honest).
#   2. With it on, short stays (< 2 s in a mode) must drop by at least half.
#   3. The planner on the stop-and-go stretch must spend at most half the time asking for more than +0.5 m/s^2.
# usage: dec_calm.py <rlogs dir>
import os
import sys

import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "drive_report"))
import dec_replay
import dec_planner_ab

ROUTE = "00000024--b9109612c2"
STRETCH = (96, 99)  # segments of the stop-and-go stretch


def short_stays(r, d):
  return sum(1 for _, dur in dec_replay.stays(r["mode"], d["t"])[1:-1] if dur < 2.0)


def main(rlogs):
  if not os.path.exists(os.path.join(rlogs, f"{ROUTE}--{STRETCH[1]}", "rlog.zst")):
    print(f"  SKIP {ROUTE} not pulled")
    return 0
  d = dec_replay.load_route(rlogs, ROUTE)
  fails = []
  hold = dec_replay.dec_module.RELEASE_HOLD_FRAMES
  dec_replay.dec_module.RELEASE_HOLD_FRAMES = 0
  old = dec_replay.run_dec(d)
  dec_replay.dec_module.RELEASE_HOLD_FRAMES = hold
  new = dec_replay.run_dec(d)
  ok = d["rec_state"] >= 0
  match = 100 * np.mean(old["mode"][ok] == d["rec_state"][ok])
  s_old, s_new = short_stays(old, d), short_stays(new, d)
  print(f"  old DEC matches the van's recording {match:.1f}%; stays under 2 s: old {s_old}, new {s_new}")
  if match < 99.9:
    fails.append(f"replay matches the recording only {match:.1f}%: the harness or DEC's inputs changed")
  if s_new > 0.5 * s_old:
    fails.append(f"short stays {s_old} -> {s_new}, want at most half")

  lr = dec_planner_ab.load(rlogs, ROUTE, *STRETCH)
  above = {}
  for name, consts in (("old", dec_planner_ab.OLD), ("new", dec_planner_ab.NEW)):
    plan = dec_planner_ab.replay(lr, consts)
    above[name] = 0.05 * np.sum(plan[:, 1] > 0.5)
  for k, v in dec_planner_ab.NEW.items():
    setattr(dec_replay.dec_module, k, v)
  print(f"  stop-and-go stretch: time asking for more than +0.5 m/s^2: old {above['old']:.1f} s, new {above['new']:.1f} s")
  if above["new"] > 0.5 * above["old"]:
    fails.append(f"hard speed-ups {above['old']:.1f} s -> {above['new']:.1f} s, want at most half (gentle speed-up after a slowdown)")
  for f in fails:
    print(f"  FAIL {f}")
  return 1 if fails else 0


if __name__ == "__main__":
  if len(sys.argv) != 2:
    sys.exit("usage: dec_calm.py <rlogs dir>")
  sys.exit(main(sys.argv[1]))
