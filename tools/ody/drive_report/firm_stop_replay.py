# ruff: noqa
"""FirmStops (Jasper) over recorded engaged stops, open loop: what it would have asked for at each moment of the real stop.

usage: firm_stop_replay.py <route prefix> [<route prefix> ...]
  e.g. firm_stop_replay.py ~/rlogs/00000086--791f5e1d12      (reads <prefix>--<n>/rlog.zst)

For every stop openpilot long handled below 2.5 m/s, prints the logged command next to FirmStop's, the latched stop
point, and the constant deceleration that point needed. Open loop: the van's logged motion is used as is, so this shows
how firm the finish would have been, not where the van would have ended up (the unit test's closed loop covers that).
"""
import glob
import os
import sys

import numpy as np

from openpilot.tools.lib.logreader import LogReader
from openpilot.selfdrive.controls.lib.firm_stop import FirmStop, model_stop_distance

DT_MDL = 0.05


def segments(prefix):
  segn = lambda f: int(os.path.basename(os.path.dirname(f)).split("--")[-1])
  return sorted(glob.glob(f"{prefix}--*/rlog.zst"), key=segn)


def replay(prefix):
  fs = FirmStop(DT_MDL)
  cs = cc = sd = md = None
  event = None
  prev_v = None
  for fn in segments(prefix):
    seg = os.path.basename(os.path.dirname(fn))
    for m in LogReader(fn):
      w = m.which()
      if w == 'carState':
        cs = m.carState
      elif w == 'carControl':
        cc = m.carControl
      elif w == 'selfdriveState':
        sd = m.selfdriveState
      elif w == 'longitudinalPlan' and cs is not None and cc is not None and sd is not None and md is not None:
        lp = m.longitudinalPlan
        v = cs.vEgo
        is_e2e = bool(sd.experimentalMode)
        a_model, stop_model = md.action.desiredAcceleration, md.action.shouldStop
        a_fs, stop_fs = fs.update(True, is_e2e, cc.longActive, cs.standstill, v, a_model, stop_model,
                                  md.velocity.x, md.position.x)
        if event is None and cc.longActive and prev_v is not None and prev_v >= 2.5 > v:
          event = dict(seg=seg, rows=[])
        if event is not None:
          d = model_stop_distance(md.velocity.x, md.position.x)
          event['rows'].append((v, cc.actuators.accel, lp.aTarget, str(lp.longitudinalPlanSource), a_model, a_fs, stop_fs,
                                fs.remaining, d, cs.brakePressed))
          end = cs.brakePressed or cs.gasPressed or not cc.longActive or v < 0.05 or v > 3.5
          if end:
            yield event
            event = None
        prev_v = v
      elif w == 'modelV2':
        md = m.modelV2


def main():
  for prefix in sys.argv[1:]:
    for ev in replay(prefix):
      rows = ev['rows']
      print(f"== {ev['seg']}: {len(rows) * DT_MDL:.1f} s from 2.5 m/s, ended {'by driver brake' if rows[-1][9] else 'without the driver'}")
      print("   v mph  logged cmd  plan src  model  firm   shouldStop(firm)  latched m  model stop m  needs")
      for i, (v, cmd, at, src, a_model, a_fs, stop_fs, rem, d, brk) in enumerate(rows):
        if i % 5 and i != len(rows) - 1:
          continue
        need = -(v ** 2) / (2 * max(rem + 0.7, 0.3)) if rem is not None else float('nan')
        print(f"   {v * 2.237:5.2f}  {cmd:+.2f}       {src[:5]:5s}    {a_model:+.2f}  {a_fs:+.2f}  {int(stop_fs)}"
              f"                 {'%.2f' % rem if rem is not None else '  -  '}      {'%.2f' % d if d is not None else '  -  '}         {need:+.2f}")
      firm = [r for r in rows if r[5] < r[4] - 1e-6]
      if firm:
        print(f"   firm for {len(firm) * DT_MDL:.2f} s, up to {max(r[4] - r[5] for r in firm):.2f} m/s^2 below the model")


if __name__ == "__main__":
  main()
