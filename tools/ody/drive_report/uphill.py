# ruff: noqa
# Uphill under-delivery on brikowski's Odyssey controller: shortfall vs grade, and gas used vs headroom.
# usage: uphill.py <ext.json> [<ext.json> ...]
import json, sys, numpy as np
G = 9.81
rows = []
for path in sys.argv[1:]:
  D = json.load(open(path))
  cs = np.array([r[:5] for r in D['cs']], dtype=float)   # t vEgo aEgo gasPressed brakePressed
  cc = D['cc']                                           # t enabled latActive longActive accel torque lcs pitch
  co = np.array([(r[0], r[4], r[5]) for r in D['co']], dtype=float)  # t gas brake
  ct = np.array([r[0] for r in cc])
  cacc = np.array([r[4] for r in cc]); cpitch = np.array([r[7] for r in cc])
  clong = np.array([r[3] for r in cc], dtype=bool); clcs = np.array([r[6] == 'pid' for r in cc])
  # 0.5 s low-pass on pitch like the controller; compare aEgo against the request 0.5 s earlier (actuator delay)
  dt = np.median(np.diff(ct))
  k = max(1, int(0.5 / dt))
  pf = np.convolve(cpitch, np.ones(k) / k, mode='same')
  for j in range(k, len(ct), 5):
    t = ct[j]
    i = min(np.searchsorted(cs[:, 0], t), len(cs) - 1)
    o = min(np.searchsorted(co[:, 0], t), len(co) - 1)
    window = slice(j - k, j + 1)
    if not (clong[window].all() and clcs[window].all()):
      continue
    v, a_ego, gas_p, brk_p = cs[i, 1:5]
    if gas_p or brk_p or v < 12:
      continue
    req = cacc[j - k]                       # request ~0.5 s ago
    steady = np.ptp(cacc[window]) < 0.15
    if not steady:
      continue
    rows.append((path, t, v, req, a_ego, pf[j], co[o, 1], co[o, 2]))

R = np.array([r[1:] for r in rows], dtype=float)
t, v, req, aego, pitch, gas, brake = R.T
grade = G * np.sin(pitch)
err = req - aego
print(f"samples {len(R)}  (steady, engaged, pid, no pedals, >12 m/s)")
print("gas output range", np.percentile(gas, [5, 50, 95, 100]).round(1))
print("\ngrade_deg   n   req    aEgo   short   gas_med  gas_p95   (-0.3 < req < 0.3: hold / gentle)")
pos = (req > -0.30) & (req < 0.30)
for lo, hi in [(-3, -1), (-1, -0.3), (-0.3, 0.3), (0.3, 1), (1, 1.5), (1.5, 2), (2, 2.5), (2.5, 4)]:
  m = pos & (np.degrees(pitch) >= lo) & (np.degrees(pitch) < hi)
  if m.sum() < 5:
    continue
  print(f"{lo:+4.1f}..{hi:+4.1f} {m.sum():5d} {req[m].mean():+.2f}  {aego[m].mean():+.2f}  {err[m].mean():+.3f}  {np.median(gas[m]):7.0f}  {np.percentile(gas[m], 95):7.0f}")

m = pos
A = np.vstack([np.ones(m.sum()), grade[m]]).T
coef, *_ = np.linalg.lstsq(A, err[m], rcond=None)
print(f"\nshortfall ~= {coef[0]:+.3f} + {coef[1]:.3f} * g*sin(pitch)   (req>0)")
up = pos & (pitch > np.radians(1.0))
print(f"uphill (>1 deg) samples {up.sum()}, gas at 2000 cap: {(gas[up] >= 1990).mean()*100:.0f}%, brake>0: {(brake[up] > 0).mean()*100:.0f}%")

print("\nby request band, uphill > 1.5 deg vs level |grade| < 0.3 deg:")
for lo, hi in [(-0.3, -0.1), (-0.1, 0.1), (0.1, 0.3), (0.3, 0.8)]:
  for name, gm in [("level", np.abs(np.degrees(pitch)) < 0.3), ("uphill", np.degrees(pitch) > 1.5)]:
    m = gm & (req >= lo) & (req < hi)
    if m.sum() >= 5:
      print(f"  req {lo:+.1f}..{hi:+.1f} {name:6s} n={m.sum():4d} req {req[m].mean():+.2f} aEgo {aego[m].mean():+.2f} short {err[m].mean():+.3f} gas {np.median(gas[m]):4.0f}")
