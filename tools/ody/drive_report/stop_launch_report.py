# Brake hold, openpilot stops and launches across drives: what the van actually does at the ends of a stop.
# usage: stop_launch_report.py <route prefix> [<route prefix> ...]
#  - brake hold: when CarState.brakeHoldActive turns on, and whether openpilot long was active then
#  - stops: openpilot-long stops to standstill: decel in the last 1.5 s, peak jerk, how long "stopping" ran
#  - launches: openpilot-long launches from standstill: delay to move, accel in the first 3 s, and what comma's
#    green-light launch (better-green-lights) would have asked for from the recorded model plan
import glob
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from openpilot.tools.lib.logreader import LogReader

T_IDXS_MPC = np.array([10.0 * (i / 32) ** 2 for i in range(33)])  # model plan times (ModelConstants.T_IDXS)
LAUNCH_DISARM_SPEED = 2.0
LAUNCH_COMMIT_T = 3.5
LAUNCH_MOVING_SPEED = 1.2
LAUNCH_MAX_ACCEL = 1.5


def green_light_accel(model_v, model_a, v_ego, should_stop):
  """comma better-green-lights: skip the model's slow creep, take its accel from where it is moving."""
  if should_stop or np.interp(LAUNCH_COMMIT_T, T_IDXS_MPC, model_v) <= LAUNCH_DISARM_SPEED:
    return None
  moving = np.argmax(model_v > LAUNCH_MOVING_SPEED) if np.any(model_v > LAUNCH_MOVING_SPEED) else len(model_v) - 1
  t_cut = min(float(T_IDXS_MPC[moving]), LAUNCH_COMMIT_T)
  a_shifted = np.interp(T_IDXS_MPC + t_cut, T_IDXS_MPC, model_a)
  # get_accel_from_plan at action_t ~ actuator delay: approximate with the shifted accel just ahead
  a_launch = float(np.interp(0.5, T_IDXS_MPC, a_shifted))
  return min(a_launch, float(np.interp(v_ego, [LAUNCH_MOVING_SPEED, LAUNCH_DISARM_SPEED], [LAUNCH_MAX_ACCEL, 0.0])))


def read_route_seg(fn):
  rows, model = [], None
  cc = {"long": False, "lcs": "", "accel": 0.0}
  ss = {"enabled": False, "exp": False}
  plan_a = 0.0
  try:
    for m in LogReader(fn):
      w = m.which()
      t = m.logMonoTime * 1e-9
      if w == "carControl":
        cc = {"long": m.carControl.longActive, "lcs": str(m.carControl.actuators.longControlState), "accel": m.carControl.actuators.accel}
      elif w == "selfdriveState":
        ss = {"enabled": m.selfdriveState.enabled, "exp": m.selfdriveState.experimentalMode}
      elif w == "longitudinalPlan":
        plan_a = m.longitudinalPlan.aTarget
      elif w == "modelV2" and len(m.modelV2.velocity.x) == 33:
        model = (np.array(m.modelV2.velocity.x), np.array(m.modelV2.acceleration.x), bool(m.modelV2.action.shouldStop))
      elif w == "carState":
        cs = m.carState
        rows.append((t, cs.vEgo, cs.aEgo, cs.standstill, bool(getattr(cs, "brakeHoldActive", False)), cs.brakePressed,
                     cs.gasPressed, cc["long"], cc["lcs"], cc["accel"], plan_a, ss["exp"], model))
  except Exception as e:
    print(f"  ! {fn}: {type(e).__name__}: {e}"[:160])
  return rows


def analyze(prefix):
  files = sorted(glob.glob(f"{prefix}--*/rlog.zst"), key=lambda f: int(f.split("--")[-1].split("/")[0]))
  with ProcessPoolExecutor() as ex:
    rows = [r for seg in ex.map(read_route_seg, files) for r in seg]
  if not rows:
    return [], [], []
  t0 = rows[0][0]
  holds, stops, launches = [], [], []
  prev = rows[0]
  for i, r in enumerate(rows[1:], 1):
    t, v, a, standstill, hold, brake, gas, long_on, lcs, acc, plan_a, exp, model = r
    if hold and not prev[4]:
      holds.append((t - t0, long_on, brake, standstill))
    # stop: openpilot long reaches standstill
    if standstill and not prev[3] and long_on:
      win = [x for x in rows[max(0, i - 400):i] if t - x[0] <= 1.5]
      if win:
        acc_e = np.array([x[2] for x in win])
        ts = np.array([x[0] for x in win])
        jerk = np.abs(np.diff(acc_e) / np.maximum(np.diff(ts), 1e-3)) if len(win) > 2 else np.array([0.0])
        stopping_s = sum(1 for x in rows[max(0, i - 600):i] if x[8] == "stopping") * 0.01
        stops.append((t - t0, float(acc_e.min()), float(acc_e[-1]), float(np.percentile(jerk, 95)), stopping_s,
                      any(x[5] for x in win), exp))
    # launch: leaving standstill with openpilot long, no gas
    if prev[3] and not standstill and long_on:
      win = [x for x in rows[i:i + 400] if x[0] - t <= 3.0]
      if win:
        acc_a = np.array([x[2] for x in win])
        cmd = np.array([x[9] for x in win])
        gas_used = any(x[6] for x in win)
        # what green-light launch would have asked for in the second before moving
        before = [x for x in rows[max(0, i - 200):i] if t - x[0] <= 1.0 and x[12] is not None]
        gl = [green_light_accel(x[12][0], x[12][1], x[1], x[12][2]) for x in before]
        gl = [g for g in gl if g is not None]
        speeds_3s = win[-1][1]
        launches.append((t - t0, float(acc_a.mean()), float(cmd.mean()), float(cmd.max()), speeds_3s * 2.237, gas_used,
                         max(gl) if gl else None, float(np.mean([x[10] for x in before])) if before else None, exp))
    prev = r
  return holds, stops, launches


def main():
  all_h, all_s, all_l = 0, [], []
  for prefix in sys.argv[1:]:
    holds, stops, launches = analyze(prefix)
    name = prefix.rsplit("/", 1)[-1]
    print(f"=== {name}: brake-hold-on events {len(holds)}, op stops {len(stops)}, op launches {len(launches)}")
    for h in holds:
      print(f"  brake hold on at {h[0] / 60:6.1f} min | op long {'ON' if h[1] else 'off'} | brake pressed {h[2]} | standstill {h[3]}")
    for s in stops:
      print(f"  stop  {s[0] / 60:6.1f} min | min aEgo {s[1]:5.2f} | aEgo at stop {s[2]:5.2f} | jerk p95 {s[3]:4.1f} m/s3 | " +
            f"stopping state {s[4]:3.1f}s | you braked {s[5]} | exp {s[6]}")
    for la in launches:
      gl = f"{la[6]:4.2f}" if la[6] is not None else "  - "
      pa = f"{la[7]:4.2f}" if la[7] is not None else "  - "
      print(f"  launch {la[0] / 60:6.1f} min | 3 s: aEgo {la[1]:4.2f} cmd mean {la[2]:4.2f} max {la[3]:4.2f} -> {la[4]:4.1f} mph | " +
            f"gas {la[5]} | plan before {pa} | green-light would ask {gl} | exp {la[8]}")
    all_h += len(holds)
    all_s += stops
    all_l += launches
  print(f"\nTOTAL brake-hold-on {all_h}, op stops {len(all_s)}, op launches {len(all_l)}")
  if all_s:
    print(f"  stops: median aEgo at stop {np.median([s[2] for s in all_s]):.2f}, median jerk p95 {np.median([s[3] for s in all_s]):.1f}, " +
          f"you braked in {sum(s[5] for s in all_s)}")
  if all_l:
    gl = [la[6] for la in all_l if la[6] is not None]
    print(f"  launches: median 3 s aEgo {np.median([la[1] for la in all_l]):.2f}, with gas {sum(la[5] for la in all_l)}, " +
          f"green-light would raise the ask in {len(gl)} (median {np.median(gl) if gl else 0:.2f})")


if __name__ == "__main__":
  main()
