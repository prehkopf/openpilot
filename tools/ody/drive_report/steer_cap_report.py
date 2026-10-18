# How often does steering hit the Odyssey caps (2560 normal, 3840 opened), by speed band, and how far off the
# planned curve is the van while capped? Only routes logged by our builds (carOutput.actuatorsOutput.torqueOutputCan).
# usage: steer_cap_report.py <route prefix> [<route prefix> ...]
import glob
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from openpilot.tools.lib.logreader import LogReader

CAP_LKA, CAP_MAX = 2560, 3840
BANDS = [(0, 34, "<34 mph"), (34, 55, "34-55"), (55, 74, "55-74"), (74, 200, ">74 mph")]


def read_seg(fn):
  out = []
  v, lat, pressed, desired, actual = 0.0, False, False, 0.0, 0.0
  try:
    for m in LogReader(fn):
      w = m.which()
      if w == "carState":
        v, pressed = m.carState.vEgo, m.carState.steeringPressed
      elif w == "carControl":
        lat = m.carControl.latActive
      elif w == "controlsState":
        desired, actual = m.controlsState.desiredCurvature, m.controlsState.curvature
      elif w == "carOutput" and lat and not pressed:
        out.append((v * 2.237, abs(m.carOutput.actuatorsOutput.torqueOutputCan), (desired - actual) * v * v))
  except Exception as e:
    print(f"  ! {fn}: {type(e).__name__}"[:120])
  return out


def main():
  files = [f for p in sys.argv[1:] for f in glob.glob(f"{p}--*/rlog.zst")]
  with ProcessPoolExecutor() as ex:
    rows = [r for seg in ex.map(read_seg, files) for r in seg]
  print(f"steering frames (engaged, hands off): {len(rows)} ({len(rows) / 100 / 60:.0f} min)")
  if not rows:
    return
  t = np.array([r[1] for r in rows])
  print(f"max command {t.max():.0f} | p99 {np.percentile(t, 99):.0f} | p99.9 {np.percentile(t, 99.9):.0f}")
  stats = defaultdict(lambda: [0, 0, 0, []])
  for mph, tq, err in rows:
    band = next(name for lo, hi, name in BANDS if lo <= mph < hi)
    s = stats[band]
    s[0] += 1
    if CAP_LKA - 15 <= tq <= CAP_LKA + 15:
      s[1] += 1
      s[3].append(abs(err))
    if tq > CAP_LKA + 15:
      s[2] += 1
  for _, _, name in BANDS:
    n, at_lka, above, errs = stats[name]
    if n:
      e = f"| lateral error while capped median {np.median(errs):.2f}, max {max(errs):.2f} m/s^2" if errs else ""
      print(f"  {name:8s} {n / 100 / 60:6.1f} min | at 2560 cap {at_lka / 100:6.1f} s ({100 * at_lka / n:.2f}%) | " +
            f"opened past 2560 {above / 100:5.1f} s {e}")


if __name__ == "__main__":
  main()
