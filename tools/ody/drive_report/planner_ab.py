# Replay plannerd from this checkout on recorded segments twice: with the highway-following changes and with them
# switched off. Compare aTarget between the two replays, and report where the lane-change gap / catch-up fired.
# usage: planner_ab.py <segment dir> [...]
import os
import sys

import numpy as np
import openpilot.selfdrive.controls.lib.longitudinal_planner as lp
from openpilot.selfdrive.test.process_replay.process_replay import replay_process_with_name
from openpilot.tools.lib.logreader import LogReader

MPH = 2.23694


def recorded_params(lr):
  """Params the replay needs to match the drive: replays start from defaults, which leave DEC off, so without
  this the planner runs plain Experimental mode instead of what the van ran."""
  dec = any(m.longitudinalPlanSP.dec.active for m in lr if m.which() == "longitudinalPlanSP")
  return {"DynamicExperimentalControl": dec}


def replay(lr, enabled):
  if enabled:
    lp.LaneChangeGap, lp.catchup_accel = ORIG
  else:
    class Off:
      def update(self, t_follow, *args):
        return t_follow
    lp.LaneChangeGap, lp.catchup_accel = Off, (lambda *a: 0.0)
  out = replay_process_with_name("plannerd", lr, disable_progress=True, custom_params=recorded_params(lr))
  return np.array([m.longitudinalPlan.aTarget for m in out if m.which() == "longitudinalPlan"])


ORIG = (lp.LaneChangeGap, lp.catchup_accel)
for seg in sys.argv[1:]:
  lr = list(LogReader(os.path.join(seg, "rlog.zst")))
  base, new = replay(lr, False), replay(lr, True)
  n = min(len(base), len(new))
  d = new[:n] - base[:n]
  lc = [m.modelV2.meta.laneChangeState.raw for m in lr if m.which() == "modelV2"]
  v = [m.carState.vEgo for m in lr if m.which() == "carState"]
  lon = np.mean([m.carControl.longActive for m in lr if m.which() == "carControl"])
  print(f"{os.path.basename(seg)}: long active {100 * lon:.0f}% | {np.mean(v) * MPH:4.1f} mph | lane change active " +
        f"{100 * np.mean([s in (1, 2) for s in lc]):.0f}% of model frames | aTarget new-base: mean {d.mean():+.3f} " +
        f"max {d.max():+.3f} min {d.min():+.3f} | changed (>0.02) in {100 * np.mean(np.abs(d) > 0.02):.1f}% of plans")
