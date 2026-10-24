# Every lane change openpilot actually started (laneChangeState -> laneChangeStarting) in a drive: was it a real
# lane change or a turn? Heading swing over the next 20 s from the pose yaw rate (turn >= 45 deg, lane < 20 deg),
# plus speed and brake in the 2 s before. This openpilot has no finishing state: starting -> off when done.
# usage: lane_change_check.py <route prefix> [...]
import glob
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from openpilot.cereal import log
from openpilot.tools.lib.logreader import LogReader

MPH = 2.23694
STARTING = int(log.LaneChangeState.laneChangeStarting)


def seg_files(prefix):
  return sorted(glob.glob(f"{prefix}--*/rlog.zst"), key=lambda f: int(f.split("--")[-1].split("/")[0]))


def read_seg(fn):
  lc, cs, yaw = [], [], []
  for m in LogReader(fn):
    t = m.logMonoTime * 1e-9
    w = m.which()
    if w == "modelV2":
      lc.append((t, m.modelV2.meta.laneChangeState.raw))
    elif w == "carState":
      cs.append((t, m.carState.vEgo, m.carState.brakePressed))
    elif w == "deviceMotion":
      yaw.append((t, m.deviceMotion.angularVelocityDevice.z))
  return lc, cs, yaw


def analyse(prefix):
  with ProcessPoolExecutor(18) as ex:
    parts = list(ex.map(read_seg, seg_files(prefix)))
  lc, cs, y = (np.array([r for p in parts for r in p[k]], dtype=float) for k in range(3))
  t0 = cs[0, 0]
  ycum = np.concatenate([[0.0], np.cumsum(y[1:, 1] * np.diff(y[:, 0]))])
  st = lc[:, 1]
  starts = np.flatnonzero((st[1:] == STARTING) & (st[:-1] != STARTING)) + 1
  print(f"\n=== {prefix.split('/')[-1]}: {len(starts)} lane changes started")
  kinds = []
  for i in starts:
    ts = lc[i, 0]
    w = (y[:, 0] >= ts) & (y[:, 0] <= ts + 20)
    h = np.degrees(ycum[w] - ycum[w][0]) if w.any() else np.zeros(1)
    swing = float(np.abs(h).max())
    kind = "TURN" if swing >= 45 else "LANE" if swing < 20 else "?"
    kinds.append(kind)
    k = min(np.searchsorted(cs[:, 0], ts), len(cs) - 1)
    pre = (cs[:, 0] >= ts - 2) & (cs[:, 0] <= ts)
    flag = "  <-- started in a turn" if kind == "TURN" else ""
    print(f"  {(ts-t0)/60:6.1f} min  {cs[k,1]*MPH:5.1f} mph  heading {swing:5.0f} deg  {kind:4s}  brake before {cs[pre,2].mean():.1f}{flag}")
  return kinds


if __name__ == "__main__":
  allk = [k for p in sys.argv[1:] for k in analyse(p.rstrip("/"))]
  print(f"\nTotal {len(allk)}: LANE {allk.count('LANE')}, TURN {allk.count('TURN')}, unclear {allk.count('?')}")
