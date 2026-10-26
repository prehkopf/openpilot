#!/usr/bin/env python3
# Replay plannerd from this checkout over consecutive recorded segments twice: with the calmer stop-and-go DEC
# (hold blended until the path is clear, gentle speed-up after a slowdown) and with both switched off (old behavior).
# Reports what the planner would have asked for: accel extremes, accel-then-brake lurches, and how often old and new differ
# (DEC's own switches aren't in the plannerd replay output; dec_replay.py counts those).
# Open loop: the van's recorded motion is replayed, so this shows the requests, not how the van would have moved.
# usage: dec_planner_ab.py <rlogs dir> <route> <first seg> <last seg> [--trace FROM_MIN TO_MIN]
import os
import sys

import numpy as np
import openpilot.sunnypilot.selfdrive.controls.lib.dec.dec as dec_module
from openpilot.selfdrive.test.process_replay.process_replay import replay_process_with_name
from openpilot.tools.lib.logreader import LogReader

MPH = 2.23694
NEW = {k: getattr(dec_module, k) for k in ("RELEASE_HOLD_FRAMES", "POST_SLOWDOWN_FRAMES")}
OLD = {"RELEASE_HOLD_FRAMES": 0, "POST_SLOWDOWN_FRAMES": 0}


def lurches(t, a, on, swing=0.5, window=4.0):
  """accel >= +swing followed within `window` s by <= -swing, while openpilot long is active."""
  n, i = 0, 0
  while i < len(t):
    if on[i] and a[i] >= swing:
      j = np.flatnonzero((t > t[i]) & (t <= t[i] + window) & on & (a <= -swing))
      if len(j):
        n += 1
        i = j[0]
    i += 1
  return n


def replay(lr, consts):
  for k, v in consts.items():
    setattr(dec_module, k, v)
  out = replay_process_with_name("plannerd", lr, disable_progress=True, custom_params={"DynamicExperimentalControl": True})
  return np.array([(m.logMonoTime / 1e9, m.longitudinalPlan.aTarget) for m in out if m.which() == "longitudinalPlan"])


def load(rlogs, route, first, last):
  lr = []
  for s in range(first, last + 1):
    lr += list(LogReader(os.path.join(rlogs, f"{route}--{s}", "rlog.zst")))
  return lr


def main(rlogs, route, first, last, trace=None):
  lr = load(rlogs, route, first, last)
  cc = [(m.logMonoTime / 1e9, m.carControl.longActive) for m in lr if m.which() == "carControl"]
  ct, con = np.array([c[0] for c in cc]), np.array([c[1] for c in cc])
  v = np.array([m.carState.vEgo for m in lr if m.which() == "carState"])
  print(f"{route} segments {first}-{last}: {len(v) / 6000:.1f} min, {v.mean() * MPH:.0f} mph average, " +
        f"op long active {100 * con.mean():.0f}%")
  plans = {}
  for name, consts in (("old", OLD), ("new", NEW)):
    plan = replay(lr, consts)
    t, a = plan[:, 0], plan[:, 1]
    on = np.interp(t, ct, con.astype(float)) > 0.5
    plans[name] = (t, a, on)
    print(f"  {name}: accel asked while op long: max {a[on].max():+.2f} min {a[on].min():+.2f}, " +
          f"time above +0.5: {0.05 * np.sum(on & (a > 0.5)):4.1f} s | lurches {lurches(t, a, on)}")
  for k, v in NEW.items():
    setattr(dec_module, k, v)
  (t, a_old, on), (_, a_new, _) = plans["old"], plans["new"]
  n = min(len(a_old), len(a_new))
  diff = np.abs(a_new[:n] - a_old[:n]) > 0.05
  print(f"  new differs from old (> 0.05 m/s^2) in {100 * diff.mean():.1f}% of plans, {100 * diff[on[:n]].mean() if on[:n].any() else 0:.1f}% " +
        f"while op long; largest change {np.abs(a_new[:n] - a_old[:n]).max():.2f}")
  t0 = next(iter(LogReader(os.path.join(rlogs, f"{route}--0", "rlog.zst")))).logMonoTime / 1e9
  mins = (t[:n] - t0) / 60
  d = a_new[:n] - a_old[:n]
  for i in np.argsort(-np.abs(d))[:5]:
    if abs(d[i]) > 0.05:
      what = 'new brakes more' if d[i] < 0 else 'new accelerates less' if a_old[i] > 0 else 'new brakes less'
      print(f"    largest: {mins[i]:7.2f} min  old {a_old[i]:+5.2f}  new {a_new[i]:+5.2f}  ({what}){'  op long' if on[i] else ''}")
  if trace:
    for i in np.flatnonzero((mins >= trace[0]) & (mins <= trace[1]))[::10]:
      print(f"    {mins[i]:7.2f} min  old {a_old[i]:+5.2f}  new {a_new[i]:+5.2f}  {'op long' if on[i] else ''}")


if __name__ == "__main__":
  if len(sys.argv) not in (5, 8):
    sys.exit("usage: dec_planner_ab.py <rlogs dir> <route> <first seg> <last seg> [--trace FROM_MIN TO_MIN]")
  main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]),
       (float(sys.argv[6]), float(sys.argv[7])) if len(sys.argv) == 8 else None)
