#!/usr/bin/env python3
# Prepush check: replay this checkout's DesireHelper over recorded drives and compare lane-change starts with what
# the build that drove them actually did. Blinker episodes above 20 mph are labelled from what the van did next
# (heading swing over 20 s from the pose yaw rate): TURN >= 45 deg, LANE < 20 deg.
# FAIL if this build starts a lane change in more TURNs than the recorded build, or in fewer than 90% of the LANEs
# the recorded build started. Recorded navInstruction is fed in when the drive was on a route.
# usage: turn_lane_change.py <rlogs dir> [route ...]   (default: the 3 newest routes with >= 30 segments)
import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from openpilot.cereal import log
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper
from openpilot.tools.lib.logreader import LogReader

MPH = 2.23694
STARTING = int(log.LaneChangeState.laneChangeStarting)
LANE_KEEP_MIN = 0.9


def seg_files(prefix):
  return sorted(glob.glob(f"{prefix}--*/rlog.zst"), key=lambda f: int(f.split("--")[-1].split("/")[0]))


def default_routes(rlogs, n=3, min_segs=30):
  routes = {}
  for d in glob.glob(os.path.join(rlogs, "*--*--*")):
    routes.setdefault(d.rsplit("--", 1)[0], []).append(d)
  long_routes = sorted(r for r, segs in routes.items() if len(segs) >= min_segs)
  return long_routes[-n:]


class CS:
  __slots__ = ("vEgo", "leftBlinker", "rightBlinker", "brakePressed", "steeringPressed", "steeringTorque",
               "leftBlindspot", "rightBlindspot")


class Nav:
  __slots__ = ("maneuverModifier", "maneuverDistance", "maneuverType")


def read_seg(fn):
  """Per modelV2 tick: carState fields, latActive, lane-change prob, recorded state, latest fresh nav; plus yaw."""
  ticks, yaw = [], []
  cs, lat, nav, nav_t = None, False, None, -1e9
  for m in LogReader(fn):
    w, t = m.which(), m.logMonoTime * 1e-9
    if w == "carState":
      c = m.carState
      cs = (c.vEgo, c.leftBlinker, c.rightBlinker, c.brakePressed, c.steeringPressed, c.steeringTorque,
            c.leftBlindspot, c.rightBlindspot)
    elif w == "carControl":
      lat = m.carControl.latActive
    elif w == "navInstruction":
      n = m.navInstruction
      nav, nav_t = ((n.maneuverModifier, n.maneuverDistance, n.maneuverType) if m.valid else None), t
    elif w == "modelV2" and cs is not None:
      ds = m.modelV2.meta.desireState
      prob = (ds[log.Desire.laneChangeLeft] + ds[log.Desire.laneChangeRight]) if len(ds) > int(log.Desire.laneChangeRight) else 0.0
      ticks.append((t, cs, lat, prob, m.modelV2.meta.laneChangeState.raw, nav if t - nav_t < 2.5 else None))
    elif w == "deviceMotion":
      yaw.append((t, m.deviceMotion.angularVelocityDevice.z))
  return ticks, yaw


def replay_states(ticks):
  dh, c, out = DesireHelper(), CS(), np.zeros(len(ticks), dtype=int)
  for k, (_, cs, lat, prob, _, nav) in enumerate(ticks):
    (c.vEgo, c.leftBlinker, c.rightBlinker, c.brakePressed, c.steeringPressed, c.steeringTorque,
     c.leftBlindspot, c.rightBlindspot) = cs
    n = None
    if nav is not None:
      n = Nav()
      n.maneuverModifier, n.maneuverDistance, n.maneuverType = nav
    dh.update(c, bool(lat), prob, nav_instruction=n)
    out[k] = dh.lane_change_state
  return out


def check_route(route):
  with ProcessPoolExecutor(min(os.cpu_count() or 4, 16)) as ex:
    parts = list(ex.map(read_seg, seg_files(route)))
  ticks = [x for p in parts for x in p[0]]
  y = np.array([x for p in parts for x in p[1]], dtype=float)
  if len(ticks) < 100 or len(y) < 100:
    return None
  t = np.array([x[0] for x in ticks])
  v = np.array([x[1][0] for x in ticks])
  blink = np.array([x[1][1] != x[1][2] for x in ticks])
  recorded = np.array([x[4] for x in ticks])
  replayed = replay_states(ticks)
  head = np.degrees(np.interp(t, y[:, 0], np.concatenate([[0.0], np.cumsum(y[1:, 1] * np.diff(y[:, 0]))])))
  counts = {("TURN", "rec"): 0, ("TURN", "new"): 0, ("LANE", "rec"): 0, ("LANE", "new"): 0, "TURN": 0, "LANE": 0}
  i = 1
  while i < len(t):
    if blink[i] and not blink[i - 1] and v[i] > 20 / MPH:
      j = i
      while j < len(t) and blink[j]:
        j += 1
      w = (t >= t[i]) & (t <= t[i] + 20)
      swing = float(np.abs(head[w] - head[i]).max())
      kind = "TURN" if swing >= 45 else "LANE" if swing < 20 else None
      if kind:
        counts[kind] += 1
        counts[(kind, "rec")] += bool((recorded[i:j] == STARTING).any())
        counts[(kind, "new")] += bool((replayed[i:j] == STARTING).any())
      i = j
    i += 1
  return counts


def main(args):
  if not args:
    sys.exit("usage: turn_lane_change.py <rlogs dir> [route ...]")
  routes = [os.path.join(args[0], r) for r in args[1:]] or default_routes(args[0])
  if not routes:
    print("WARN no recorded routes with >= 30 segments, nothing to check")
    return 0
  total = {}
  for r in routes:
    c = check_route(r)
    if c is None:
      print(f"{os.path.basename(r)}: too little data")
      continue
    print(f"{os.path.basename(r)}: TURN {c['TURN']} (lane change started: recorded {c[('TURN', 'rec')]}, this build " +
          f"{c[('TURN', 'new')]}) | LANE {c['LANE']} (recorded {c[('LANE', 'rec')]}, this build {c[('LANE', 'new')]})")
    for k, n in c.items():
      total[k] = total.get(k, 0) + n
  if not total:
    return 0
  fail = []
  if total[("TURN", "new")] > total[("TURN", "rec")]:
    fail.append(f"more lane changes started in turns ({total[('TURN', 'new')]} vs recorded {total[('TURN', 'rec')]})")
  if total[("LANE", "new")] < LANE_KEEP_MIN * total[("LANE", "rec")]:
    fail.append(f"lane changes lost ({total[('LANE', 'new')]} vs recorded {total[('LANE', 'rec')]})")
  print("FAIL " + "; ".join(fail) if fail else "OK")
  return 1 if fail else 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
