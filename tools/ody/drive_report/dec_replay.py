#!/usr/bin/env python3
# Replay this checkout's Dynamic Experimental Control (DEC) over a recorded route: the real DEC code, fed the recorded
# carState, modelV2, radarState and selfdriveState, one step per modelV2 frame (20 Hz). Replayed from segment 0 it
# reproduces what the van's DEC decided (--validate compares with the recorded longitudinalPlanSP.dec), so a DEC change
# can be judged on real drives without the van. A/B a constant in dec.py with --set NAME=VALUE.
# usage: dec_replay.py <rlogs dir> <route> [--validate] [--set NAME=VALUE ...] [--trace FROM_MIN TO_MIN] [--switches FROM_MIN TO_MIN]
#   e.g. dec_replay.py ~/rlogs 00000024--b9109612c2 --validate --trace 97.8 98.6
import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace

import numpy as np
import openpilot.sunnypilot.selfdrive.controls.lib.dec.dec as dec_module
from openpilot.tools.lib.logreader import LogReader

MPH = 2.23694
MODES = {"acc": 0, "blended": 1}
FIELDS = ("t", "v", "v_cruise", "standstill", "lead", "exp", "n_pos", "n_ori", "end_x", "yaw", "rec_state", "rec_active",
          "a_target", "fcw", "cmd", "gas", "brake", "lon")


def extract_segment(path):
  """One row per modelV2 frame with the latest value of everything DEC reads, plus what the van recorded."""
  rows = []
  cs = SimpleNamespace(vEgo=0.0, vCruise=0.0, standstill=False, gasPressed=False, brakePressed=False)
  lead, exp, cmd, fcw, lon = False, False, 0.0, False, False
  for m in LogReader(path):
    w = m.which()
    if w == "carState":
      cs = m.carState
    elif w == "radarState":
      lead = m.radarState.leadOne.present
    elif w == "selfdriveState":
      exp = m.selfdriveState.experimentalMode
    elif w == "carControl":
      cmd = m.carControl.actuators.accel
      lon = m.carControl.longActive
    elif w == "modelV2":
      md = m.modelV2
      n_pos, n_ori = len(md.position.x), len(md.orientation.x)
      end_x = md.position.x[32] if n_pos == 33 else np.nan
      yaw = md.orientation.z[32] if len(md.orientation.z) == 33 else 0.0
      rows.append([m.logMonoTime / 1e9, cs.vEgo, cs.vCruise, cs.standstill, lead, exp, n_pos, n_ori, end_x, yaw, -1, False,
                   0.0, fcw, cmd, cs.gasPressed, cs.brakePressed, lon])
    elif w == "longitudinalPlan" and rows:
      rows[-1][12] = m.longitudinalPlan.aTarget
      rows[-1][13] = m.longitudinalPlan.fcw
      fcw = m.longitudinalPlan.fcw
    elif w == "longitudinalPlanSP" and rows:
      dec = m.longitudinalPlanSP.dec  # published right after the modelV2 frame it was computed from
      rows[-1][10] = dec.state.raw
      rows[-1][11] = dec.active
  return np.array(rows, dtype=np.float64).reshape(-1, len(FIELDS))


def load_route(rlogs, route):
  files = sorted(glob.glob(os.path.join(rlogs, f"{route}--*", "rlog.zst")), key=lambda f: int(f.split("--")[-1].split(os.sep)[0].split("/")[0]))
  with ProcessPoolExecutor(min(16, os.cpu_count() or 4)) as ex:
    arrays = list(ex.map(extract_segment, files))
  data = np.concatenate([a for a in arrays if len(a)])
  d = {f: data[:, i] for i, f in enumerate(FIELDS)}
  d["t0"] = next(iter(LogReader(files[0]))).logMonoTime / 1e9  # route start, so minutes match the other drive reports
  return d


class FakeParams:
  def get_bool(self, key):
    return True


def run_dec(d):
  """Step the real DEC through the route. Returns per-frame mode, reason and the internals worth plotting."""
  mpc = SimpleNamespace(crash_cnt=0)
  dec = dec_module.DynamicExperimentalController(SimpleNamespace(radarUnavailable=True), mpc, FakeParams())
  n = len(d["t"])
  out = {k: np.zeros(n) for k in ("mode", "urgency", "slow_down", "standstill_count", "expected")}
  reasons = []
  for i in range(n):
    mpc.crash_cnt = 3 if d["fcw"][i] else 0
    pos = [0.0] * 32 + [d["end_x"][i]] if d["n_pos"][i] == 33 else [0.0] * int(d["n_pos"][i])
    ori = [0.0] * int(d["n_ori"][i])
    ori_z = [0.0] * 32 + [d["yaw"][i]] if d["n_ori"][i] == 33 else []
    sm = {"carState": SimpleNamespace(vEgo=d["v"][i], vCruise=d["v_cruise"][i], standstill=bool(d["standstill"][i])),
          "radarState": SimpleNamespace(leadOne=SimpleNamespace(present=bool(d["lead"][i]))),
          "modelV2": SimpleNamespace(position=SimpleNamespace(x=pos), orientation=SimpleNamespace(x=ori, z=ori_z)),
          "selfdriveState": SimpleNamespace(experimentalMode=bool(d["exp"][i]))}
    dec.update(sm)
    out["mode"][i] = MODES[dec.mode()]
    out["urgency"][i] = dec._urgency
    out["slow_down"][i] = dec._has_slow_down
    out["standstill_count"][i] = dec._standstill_count
    out["expected"][i] = dec._expected_distance
    reasons.append(dec.reason())
  out["reason"] = np.array(reasons)
  return out


def stays(mode, t):
  """(mode, seconds) for each uninterrupted stay in a mode."""
  change = np.flatnonzero(np.diff(mode) != 0) + 1
  bounds = np.concatenate([[0], change, [len(mode)]])
  return [(int(mode[a]), t[min(b, len(t) - 1)] - t[a]) for a, b in zip(bounds[:-1], bounds[1:], strict=True)]


def summarize(name, d, r, validate):
  minutes = (d["t"][-1] - d["t"][0]) / 60
  s = stays(r["mode"], d["t"])
  switches = len(s) - 1
  short = sum(1 for _, dur in s[1:-1] if dur < 2.0)
  blended = 100 * np.mean(r["mode"] == 1)
  on = d["lon"] > 0
  on_min = on.sum() * 0.05 / 60
  sw_on = int(np.sum((np.diff(r["mode"]) != 0) & on[1:]))
  line = (f"{name}: {minutes:5.1f} min | switches {switches:4d} ({switches / minutes:4.1f}/min) | stays < 2 s: {short:3d} | " +
          f"blended {blended:4.1f}% | op long {on_min:4.1f} min, switches {sw_on}")
  if validate:
    ok = d["rec_state"] >= 0
    agree = 100 * np.mean(r["mode"][ok] == d["rec_state"][ok])
    line += f" | matches recorded DEC {agree:5.1f}%"
  print(line)


def trace(d, r, t_from, t_to):
  t = (d["t"] - d["t0"]) / 60
  print(f"{'min':>7} {'mph':>5} {'mode':>5} {'rec':>5} {'reason':<9} {'urg':>5} {'slow':>4} {'end_x':>6} {'need':>5} {'stst':>4} {'a_tgt':>6}")
  for i in np.flatnonzero((t >= t_from) & (t <= t_to))[::2]:
    print(f"{t[i]:7.3f} {d['v'][i] * MPH:5.1f} {'BLEND' if r['mode'][i] else 'acc':>5} {'BLEND' if d['rec_state'][i] == 1 else 'acc':>5} " +
          f"{r['reason'][i]:<9} {r['urgency'][i]:5.2f} {int(r['slow_down'][i]):4d} {d['end_x'][i]:6.1f} {r['expected'][i]:5.1f} " +
          f"{int(r['standstill_count'][i]):4d} {d['a_target'][i]:+6.2f}")


def switches(d, r, t_from, t_to):
  """Every mode switch in the window, with what DEC saw when it happened."""
  t = (d["t"] - d["t0"]) / 60
  print(f"{'min':>8} {'to':>7} {'after s':>7} {'mph':>5} {'urg':>5} {'slow':>4} {'stst':>4} {'reason':<9} {'end_x':>6} {'need':>5}")
  last = 0
  for i in np.flatnonzero(np.diff(r["mode"]) != 0) + 1:
    if t_from <= t[i] <= t_to:
      print(f"{t[i]:8.3f} {'BLEND' if r['mode'][i] else 'acc':>7} {d['t'][i] - d['t'][last]:7.2f} {d['v'][i] * MPH:5.1f} {r['urgency'][i]:5.2f} " +
            f"{int(r['slow_down'][i]):4d} {int(r['standstill_count'][i]):4d} {r['reason'][i]:<9} {d['end_x'][i]:6.1f} {r['expected'][i]:5.1f}")
    last = i


def main(argv):
  args = [a for a in argv if not a.startswith("--") and "=" not in a]
  if len(args) < 2:
    sys.exit(__doc__)
  rlogs, route = args[:2]
  for i, a in enumerate(argv):
    if a == "--set":
      k, v = argv[i + 1].split("=")
      setattr(dec_module, k, type(getattr(dec_module, k))(float(v)) if not isinstance(getattr(dec_module, k), bool) else v == "1")
  d = load_route(rlogs, route)
  r = run_dec(d)
  summarize(route, d, r, "--validate" in argv)
  if "--switches" in argv:
    i = argv.index("--switches")
    switches(d, r, float(argv[i + 1]), float(argv[i + 2]))
  if "--trace" in argv:
    i = argv.index("--trace")
    trace(d, r, float(argv[i + 1]), float(argv[i + 2]))


if __name__ == "__main__":
  main(sys.argv[1:])
