#!/usr/bin/env python3
# Fit a longitudinal response model of the van from recorded drives (Odyssey gas units, 0..1600 counts):
#   aEgo(t + d) = c_gas * gas(t) + c0 + c_v2 * v^2 - b * g * sin(pitch)
# over engaged, pedal-free gas samples, and pick the delay d with the lowest error.
# usage: fit_plant.py <segment dir> [...]   e.g. fit_plant.py ~/rlogs/00000007--* ~/rlogs/00000008--*
# The empty-van fit from routes 7 and 8 is the plant in opendbc/car/honda/tests/odyssey_load_sim.py.
# Fit a loaded drive the same way and compare c_gas and b to calibrate the van-load presets.
import os
import sys
import numpy as np
from openpilot.tools.lib.logreader import LogReader

G = 9.81


def load(paths):
  rows = []  # t, gas, aEgo, v, pitch, longActive, gasPressed, brakePressed
  for p in paths:
    fn = os.path.join(p, "rlog.zst") if os.path.isdir(p) else p
    cs = cc = None
    for m in LogReader(fn):
      w = m.which()
      if w == "carState":
        cs = m.carState
      elif w == "carControl":
        cc = m.carControl
      elif w == "carOutput" and cs is not None and cc is not None:
        pitch = cc.orientationNED[1] if len(cc.orientationNED) == 3 else float("nan")
        rows.append((m.logMonoTime * 1e-9, m.carOutput.actuatorsOutput.gas, cs.aEgo, cs.vEgo, pitch,
                     cc.longActive, cs.gasPressed, cs.brakePressed))
  return np.array(rows, dtype=float)


def fit(d, dt, delay_s):
  t, gas, aego, v, pitch, act, gp, bp = d.T
  k = int(round(delay_s / dt))
  idx = np.arange(len(d) - k)
  ok = ((act[idx] > 0) & (gp[idx] == 0) & (bp[idx] == 0) & (gas[idx] > 0) & np.isfinite(pitch[idx]) &
        (v[idx] > 3) & (np.abs(t[idx + k] - t[idx] - delay_s) < 0.05))
  i = idx[ok]
  X = np.column_stack([gas[i], np.ones(len(i)), v[i] ** 2, -G * np.sin(pitch[i])])
  y = aego[i + k]
  coef, *_ = np.linalg.lstsq(X, y, rcond=None)
  return coef, np.sqrt(np.mean((y - X @ coef) ** 2)), len(i)


def main(paths):
  if not paths:
    sys.exit("usage: fit_plant.py <segment dir or rlog.zst> [...]")
  d = load(sorted(paths))
  print(f"{len(paths)} segments, {len(d)} samples, {d[:, 5].mean() * 100:.0f}% longActive")
  dt = np.median(np.diff(d[:, 0]))
  best = None
  for delay in np.arange(0.2, 1.21, 0.1):
    coef, rmse, n = fit(d, dt, delay)
    print(f"delay {delay:.1f}s: rmse {rmse:.3f}  n={n}  c_gas={coef[0] * 1000:.3f}/1000cnt c0={coef[1]:.3f} " +
          f"c_v2={coef[2] * 1000:.4f}e-3 b={coef[3]:.2f}")
    if best is None or rmse < best[1]:
      best = (delay, rmse, coef, n)
  delay, rmse, coef, n = best
  print(f"BEST delay {delay:.1f}s rmse {rmse:.3f} n={n}")
  print("PLANT", ",".join(f"{x:.6g}" for x in (delay, *coef)))


if __name__ == "__main__":
  main(sys.argv[1:])
