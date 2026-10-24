# One line per route across many drives: build, start time, length, how much openpilot drove, how each
# longitudinal engagement ended, launches, DEC/Experimental share, battery, bookmarks, and the alerts that fired.
# usage: route_overview.py <route prefix> [<route prefix> ...]
import collections
import datetime
import glob
import sys
from concurrent.futures import ProcessPoolExecutor
from zoneinfo import ZoneInfo

import numpy as np
from openpilot.tools.lib.logreader import LogReader

MPH = 2.23694
ET = ZoneInfo("America/New_York")
DISABLE_FLAGS = ("userDisable", "softDisable", "immediateDisable")


def seg_files(prefix):
  return sorted(glob.glob(f"{prefix}--*/rlog.zst"), key=lambda f: int(f.split("--")[-1].split("/")[0]))


def read_seg(fn):
  out = {"init": None, "wall": None, "cs": [], "cc": [], "sd": [], "dec": [], "ev": [], "volt": [], "bm": 0, "oplong": None}
  for m in LogReader(fn):
    t = m.logMonoTime * 1e-9
    w = m.which()
    if w == "carState":
      c = m.carState
      out["cs"].append((t, c.vEgo, c.gasPressed, c.brakePressed, c.cruiseState.enabled, c.standstill))
    elif w == "carControl":
      out["cc"].append((t, m.carControl.latActive, m.carControl.longActive))
    elif w == "selfdriveState":
      s = m.selfdriveState
      out["sd"].append((t, s.experimentalMode, s.personality.raw))
    elif w == "longitudinalPlanSP":
      d = m.longitudinalPlanSP.dec
      out["dec"].append((t, d.active, d.state.raw))
    elif w in ("onroadEvents", "onroadEventsSP"):
      obj = getattr(m, w)
      for e in (obj.events if hasattr(obj, "events") else obj):
        flags = tuple(k for k in DISABLE_FLAGS + ("noEntry", "warning", "permanent") if getattr(e, k, False))
        out["ev"].append((t, str(e.name), flags))
    elif w == "peripheralState":
      out["volt"].append(m.peripheralState.voltage / 1000)
    elif w in ("userBookmark", "userFlag"):
      out["bm"] += 1
    elif w == "initData" and out["init"] is None:
      out["init"] = (m.initData.gitBranch, m.initData.gitCommit[:8], m.initData.version)
    elif w == "carParams" and out["oplong"] is None:
      out["oplong"] = m.carParams.openpilotLongitudinalControl
    elif w in ("gpsLocation", "gpsLocationExternal") and out["wall"] is None:
      g = getattr(m, w)
      if g.hasFix and g.unixTimestampMillis > 0:
        out["wall"] = (t, g.unixTimestampMillis / 1000)
  return out


def runs(mask):
  """[(start, end)] index ranges where mask is True."""
  d = np.diff(np.r_[0, mask.astype(int), 0])
  return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1, strict=True))


def at(arr, times, col):
  idx = np.clip(np.searchsorted(arr[:, 0], times, side="right") - 1, 0, len(arr) - 1)
  return arr[idx, col]


def summarize(prefix, parts):
  cs = np.array([r for p in parts for r in p["cs"]], dtype=float)
  cc = np.array([r for p in parts for r in p["cc"]], dtype=float)
  if len(cs) < 100 or len(cc) < 100:
    return None, None
  sd = np.array([r for p in parts for r in p["sd"]], dtype=float)
  dec = np.array([r for p in parts for r in p["dec"]], dtype=float)
  ev = [r for p in parts for r in p["ev"]]
  volt = [v for p in parts for v in p["volt"]]
  init = next((p["init"] for p in parts if p["init"]), ("?", "?", "?"))
  wall = next((p["wall"] for p in parts if p["wall"]), None)
  oplong = next((p["oplong"] for p in parts if p["oplong"] is not None), None)

  t, v = cs[:, 0], cs[:, 1]
  gas, brake = cs[:, 2] > 0, cs[:, 3] > 0
  dt = np.r_[np.diff(t), 0].clip(0, 0.1)
  lat, lon = at(cc, t, 1) > 0, at(cc, t, 2) > 0
  moving = v > 1
  start = datetime.datetime.fromtimestamp(wall[1] - (wall[0] - t[0]), ET).strftime("%a %m-%d %H:%M") if wall else "no gps"
  moving_time = max(dt[moving].sum(), 1)
  r = {"route": prefix.split("/")[-1], "build": f"{init[2]} {init[1]}", "start": start, "mins": (t[-1] - t[0]) / 60,
       "miles": float((v * dt).sum() / 1609.34), "oplong": oplong,
       "lat": float(dt[lat & moving].sum() / moving_time), "lon": float(dt[lon & moving].sum() / moving_time),
       "bm": sum(p["bm"] for p in parts), "v0": volt[0] if volt else np.nan, "v1": volt[-1] if volt else np.nan}
  r["exp"] = float((at(sd, t, 1) > 0)[lon].mean()) if len(sd) and lon.any() else np.nan
  r["pers"] = int(np.bincount(at(sd, t, 2)[lon].astype(int)).argmax()) if len(sd) and lon.any() else -1
  r["dec"] = float(dec[:, 1].mean()) if len(dec) else np.nan

  # how each longitudinal engagement ended (ignore the last one if it runs to the end of the log)
  ends = collections.Counter()
  for _, e in runs(lon):
    if e >= len(t) - 2:
      ends["log end"] += 1
      continue
    k = min(e + 1, len(t) - 1)
    near = {n for (te, n, f) in ev if t[k] - 0.6 <= te <= t[k] + 0.3 and set(f) & set(DISABLE_FLAGS)}
    why = "gas" if gas[k] or gas[e] else "brake" if brake[k] or brake[e] else "cruise off" if not cs[k, 4] else ",".join(sorted(near)) or "other"
    ends[why] += 1
  r["ends"] = ends
  r["neng"] = sum(ends.values())

  # launches: long active, stopped >= 1 s, then moving
  stopped = v < 0.3
  r["launch"] = sum(1 for s, e in runs(stopped) if t[e] - t[s] >= 1 and e + 1 < len(t) and lon[e + 1])
  r["gas_lon"] = float(gas[lon & (v > 3)].mean()) if (lon & (v > 3)).any() else np.nan

  # alerts: count onsets (a new name after >= 1 s of silence), keep anything that disengaged or warned
  last, onsets = {}, collections.Counter()
  for te, n, f in ev:
    if te - last.get(n, -9) > 1.0:
      onsets[(n, f)] += 1
    last[n] = te
  return r, onsets


def main(prefixes):
  jobs = [(p, f) for p in prefixes for f in seg_files(p)]
  with ProcessPoolExecutor(18) as ex:
    res = list(ex.map(read_seg, [f for _, f in jobs], chunksize=2))
  by = collections.defaultdict(list)
  for (p, _), r in zip(jobs, res, strict=True):
    by[p].append(r)

  rows, all_onsets = [], collections.Counter()
  for p in prefixes:
    r, on = summarize(p, by[p])
    if r is None:
      print(f"{p.split('/')[-1]}: too little data")
      continue
    rows.append(r)
    all_onsets.update(on)
    r["on"] = on

  print(f"{'route':22s} {'start (ET)':15s} {'build':22s} {'min':>4s} {'mi':>5s} {'lat%':>5s} {'lon%':>5s} {'exp%':>5s} {'dec%':>5s} " +
        f"{'eng':>4s} {'launch':>6s} {'gas%':>5s} {'bm':>3s} {'V start>end':>12s}  ended by")
  for r in rows:
    ends = " ".join(f"{k}:{n}" for k, n in r["ends"].most_common())
    print(f"{r['route']:22s} {r['start']:15s} {r['build'][:22]:22s} {r['mins']:4.0f} {r['miles']:5.1f} {100*r['lat']:5.0f} {100*r['lon']:5.0f} " +
          f"{100*r['exp']:5.0f} {100*r['dec']:5.0f} {r['neng']:4d} {r['launch']:6d} {100*r['gas_lon']:5.1f} {r['bm']:3d} " +
          f"{r['v0']:5.2f}>{r['v1']:5.2f}  {ends}")
  tot_min, tot_mi = sum(r["mins"] for r in rows), sum(r["miles"] for r in rows)
  tot_ends = sum((r["ends"] for r in rows), collections.Counter())
  print(f"\nTotal: {len(rows)} routes, {tot_min/60:.1f} h, {tot_mi:.0f} mi, {sum(r['neng'] for r in rows)} long engagements, " +
        f"{sum(r['launch'] for r in rows)} launches, {sum(r['bm'] for r in rows)} bookmark msgs")
  print("Long engagements ended by: " + ", ".join(f"{k} {n}" for k, n in tot_ends.most_common()))
  print(f"Distance-weighted: lateral {100*sum(r['lat']*r['miles'] for r in rows)/tot_mi:.0f}%, " +
        f"longitudinal {100*sum(r['lon']*r['miles'] for r in rows)/tot_mi:.0f}% of moving time")
  print(f"Builds: {collections.Counter(r['build'] for r in rows)}")

  print("\nAlerts across all routes (onsets), disengaging or warning first:")
  ranked = sorted(all_onsets.items(), key=lambda kv: (not set(kv[0][1]) & set(DISABLE_FLAGS + ("warning",)), -kv[1]))
  for (n, f), k in ranked[:40]:
    where = [r["route"][:8] for r in rows if r["on"].get((n, f))]
    print(f"  {k:5d}  {n:34s} {'/'.join(f):28s} in {len(where)} routes")


if __name__ == "__main__":
  main([p.rstrip("/") for p in sys.argv[1:]])
