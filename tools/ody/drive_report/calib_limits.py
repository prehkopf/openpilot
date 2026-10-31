# What would comma's stock limits have done on our drives?
#  locationd: replays LocationEstimator + the bad-input counter exactly as locationd.main does, for INPUT_INVALID_LIMIT 10
#             (MVL's widened value) and 2 (comma's). inputsOK false -> locationdTemporaryError -> soft disable. The limit-10 replay
#             must match the recorded deviceMotion.inputsOK (honesty check).
#  calibrationd: recorded rpyCalibSpread vs comma's 2 deg yaw / 4 deg pitch while calibrated (a reset + recalibrating).
# usage: tools/ody/drive_report/calib_limits.py <rlogs dir> [route ...]   (all pulled routes: ~7 min on 8 cores)
import glob
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from openpilot.cereal.services import SERVICE_LIST
from openpilot.tools.lib.logreader import LogReader
from openpilot.selfdrive.locationd.locationd import (LocationEstimator, HandleLogResult, INPUT_INVALID_RECOVERY,
                                                      calculate_invalid_input_decay)

CRIT = ["accelerometer", "gyroscope", "cameraOdometry"]
LIMITS = {"ours": 10.0, "comma": 2.0}  # "ours" = MVL's widened value, which we ran until Ideal
USED = {"accelerometer", "gyroscope", "carState", "extrinsicsCalibration", "cameraOdometry"}
YAW, PITCH = np.radians(2), np.radians(4)


def seg_files(rlogs, route):
  return sorted(glob.glob(os.path.join(rlogs, f"{route}--*", "rlog.zst")), key=lambda f: int(os.path.basename(os.path.dirname(f)).rsplit("--", 1)[1]))


def run_route(job):
  rlogs, route = job
  est = LocationEstimator(False)
  lim = {k: {s: round(v * SERVICE_LIST[s].frequency / 20.) for s in CRIT} for k, v in LIMITS.items()}
  thr = {k: {s: lim[k][s] - 0.5 for s in CRIT} for k in LIMITS}
  dec = {k: {s: calculate_invalid_input_decay(lim[k][s], INPUT_INVALID_RECOVERY, SERVICE_LIST[s].frequency) for s in CRIT}
         for k in LIMITS}
  cnt = {k: defaultdict(float) for k in LIMITS}
  seen, last_valid = set(), {}
  initialized = False
  engaged = False
  v_ego = 0.0
  bad = dict.fromkeys(LIMITS, 0)          # cameraOdometry frames (20 Hz) with inputsOK false
  bad_eng = dict.fromkeys(LIMITS, 0)
  onsets = {k: [] for k in LIMITS}      # (t into route, engaged, mph, worst service)
  prev_ok = dict.fromkeys(LIMITS, True)
  rec_ok, match, compared = None, 0, 0
  frames = 0
  peak = dict.fromkeys(CRIT, 0.0)  # highest counter / comma threshold, after the first 10 s
  invalid_obs = dict.fromkeys(CRIT, 0)
  t0 = None
  max_spread = np.zeros(3)
  over_cal = 0  # extrinsicsCalibration msgs over comma spread while calibrated
  cal_msgs = 0
  for fn in seg_files(rlogs, route):
    try:
      lr = list(LogReader(fn))
    except Exception:
      continue
    lr.sort(key=lambda m: m.logMonoTime)
    for m in lr:
      w = m.which()
      t = m.logMonoTime * 1e-9
      if w == "selfdriveState":
        engaged = m.selfdriveState.enabled
      elif w == "carControl":
        engaged = engaged or m.carControl.latActive
      elif w == "deviceMotion":
        rec_ok = m.deviceMotion.inputsOK
      if w == "extrinsicsCalibration":
        ec = m.extrinsicsCalibration
        if str(ec.calStatus) == "calibrated" and len(ec.rpyCalibSpread) == 3:
          sp = np.abs(np.array(ec.rpyCalibSpread))
          max_spread = np.maximum(max_spread, sp)
          cal_msgs += 1
          over_cal += int(sp[1] > PITCH or sp[2] > YAW)
      if w not in USED:
        continue
      if w == "carState":
        v_ego = m.carState.vEgo
        if t0 is None:
          t0 = t
      seen.add(w)
      last_valid[w] = m.valid
      if not initialized:
        initialized = USED <= seen
        if not initialized:
          continue
      if m.valid:
        res = est.handle_log(t, w, getattr(m, w))
        if w in CRIT:
          for k in LIMITS:
            if res in (HandleLogResult.TIMING_INVALID, HandleLogResult.INPUT_INVALID):
              cnt[k][w] += 1
              invalid_obs[w] += k == "comma"
            elif res == HandleLogResult.SUCCESS:
              cnt[k][w] *= dec[k][w]
      if w == "cameraOdometry":
        frames += 1
        if frames > 200:
          for s_ in CRIT:
            peak[s_] = max(peak[s_], cnt["comma"][s_] / thr["comma"][s_])
        all_valid = all(last_valid.get(s, False) for s in ("carState", "extrinsicsCalibration", "cameraOdometry"))
        for k in LIMITS:
          ok = all_valid and all(cnt[k][s] < thr[k][s] for s in CRIT)
          if not ok:
            bad[k] += 1
            bad_eng[k] += int(engaged)
            if prev_ok[k]:
              worst = max(CRIT, key=lambda s: cnt[k][s] / thr[k][s])
              onsets[k].append(((t - (t0 or t)) / 60, engaged, v_ego * 2.237, worst))
          prev_ok[k] = ok
        if rec_ok is not None:
          compared += 1
          match += int(rec_ok == prev_ok["ours"])
  return {"route": route, "peak": peak, "invalid_obs": invalid_obs, "frames": frames, "bad": bad, "bad_eng": bad_eng, "onsets": onsets,
          "match": match, "compared": compared,
              "max_spread": np.degrees(max_spread), "over_cal": over_cal, "cal_msgs": cal_msgs}


def main(rlogs, routes):
  if not routes:
    routes = sorted({os.path.basename(d).rsplit("--", 1)[0] for d in glob.glob(os.path.join(rlogs, "*--*--*"))})
  with ProcessPoolExecutor(8) as ex:
    res = list(ex.map(run_route, [(rlogs, r) for r in routes]))
  print("route                 min   replay=recorded  inputsOK false (s): ours / comma   engaged: ours / comma" +
        "   max spread pitch/yaw deg   over 4/2 deg")
  tot = defaultdict(float)
  for r in res:
    if not r["frames"]:
      continue
    m = 100 * r["match"] / r["compared"] if r["compared"] else float("nan")
    print(f"{r['route']}  {r['frames'] / 20 / 60:5.0f}   {m:6.2f}%          {r['bad']['ours'] / 20:7.1f} / {r['bad']['comma'] / 20:7.1f}" +
          f"       {r['bad_eng']['ours'] / 20:6.1f} / {r['bad_eng']['comma'] / 20:6.1f}" +
          f"        {r['max_spread'][1]:4.2f} / {r['max_spread'][2]:4.2f}        {r['over_cal']}")
    for k in ("frames", "match", "compared", "over_cal", "cal_msgs"):
      tot[k] += r[k]
    for k in LIMITS:
      tot[f"bad_{k}"] += r["bad"][k]
      tot[f"eng_{k}"] += r["bad_eng"][k]
  print(f"\nTOTAL {tot['frames'] / 20 / 3600:.1f} h; replay matches recorded inputsOK {100 * tot['match'] / max(tot['compared'], 1):.2f}%")
  for k in LIMITS:
    ons = [(r["route"], o) for r in res for o in r["onsets"][k]]
    eng = [x for x in ons if x[1][1]]
    print(f"limit {LIMITS[k]:4.0f} ({k}): inputsOK false {tot[f'bad_{k}'] / 20:.0f} s total, {tot[f'eng_{k}'] / 20:.0f} s while engaged;" +
          f" {len(ons)} onsets, {len(eng)} while engaged")
    for route, (tm, e, mph, worst) in ons[:40]:
      print(f"    {route} {tm:6.1f} min  {'ENGAGED' if e else 'not engaged'}  {mph:4.0f} mph  {worst}")
  for r in res:
    if r["frames"]:
      print(f"  {r['route']}: bad inputs " + ", ".join(f"{s} {r['invalid_obs'][s]}" for s in CRIT) +
            " | peak counter vs comma threshold " + ", ".join(f"{s} {100 * r['peak'][s]:.0f}%" for s in CRIT))
  print(f"calibration: {tot['over_cal']:.0f} of {tot['cal_msgs']:.0f} calibrated messages over comma's 4 deg pitch / 2 deg yaw spread")


if __name__ == "__main__":
  main(sys.argv[1], sys.argv[2:])
