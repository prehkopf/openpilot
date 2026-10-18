"""RehkopfPilot: green-light launch, ported from comma's better-green-lights branch (2026-07, not merged upstream).

From a stop, the driving model's plan starts with a slow creep before it commits to moving. Once the model plans to
be past LAUNCH_DISARM_SPEED by LAUNCH_COMMIT_T, skip ahead to the part of its plan where it is already moving and
take that acceleration instead, capped at LAUNCH_MAX_ACCEL and fading out by LAUNCH_DISARM_SPEED. It only ever raises
the model (e2e) candidate; the planner still takes the minimum with the lead-following MPC and cruise targets.

Differences from comma's version: gated on the DEC-aware is_e2e (DEC hands the model control at a stop), and the
model plan is interpolated here because this planner does not parse it.
On the 2026-10 Odyssey drives the plan asked 0.13-0.29 m/s^2 in the second before moving; this asks 1.44-1.50.
"""
import numpy as np

from openpilot.selfdrive.controls.lib.drive_helpers import get_accel_from_plan
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import T_IDXS as T_IDXS_MPC
from openpilot.selfdrive.modeld.constants import ModelConstants

LAUNCH_DISARM_SPEED = 2.0  # m/s; above this the launch is over
LAUNCH_COMMIT_T = 3.5  # s; the model must plan to be past LAUNCH_DISARM_SPEED by then
LAUNCH_MOVING_SPEED = 1.2  # m/s; where in the plan "moving" starts
LAUNCH_MAX_ACCEL = 1.5  # m/s^2 at LAUNCH_MOVING_SPEED, fading to 0 at LAUNCH_DISARM_SPEED


class GreenLightLaunch:
  def __init__(self):
    self.armed = False
    self.active = False

  def update(self, standstill: bool, v_ego: float, is_e2e: bool, a_e2e: float, should_stop_e2e: bool,
             model_v_x, model_a_x, action_t: float) -> float:
    """Returns the model (e2e) accel target, raised for a launch when one applies."""
    if standstill:
      self.armed = True
    elif v_ego > LAUNCH_DISARM_SPEED:
      self.armed = False

    self.active = False
    if not (self.armed and is_e2e and not should_stop_e2e):
      return a_e2e
    if len(model_v_x) != len(ModelConstants.T_IDXS) or len(model_a_x) != len(ModelConstants.T_IDXS):
      return a_e2e

    model_v = np.interp(T_IDXS_MPC, ModelConstants.T_IDXS, model_v_x)
    model_a = np.interp(T_IDXS_MPC, ModelConstants.T_IDXS, model_a_x)
    if np.interp(LAUNCH_COMMIT_T, T_IDXS_MPC, model_v) <= LAUNCH_DISARM_SPEED:
      return a_e2e

    moving = model_v > LAUNCH_MOVING_SPEED
    t_cut = min(float(T_IDXS_MPC[np.argmax(moving)]), LAUNCH_COMMIT_T) if moving.any() else LAUNCH_COMMIT_T
    t_shifted = T_IDXS_MPC + t_cut
    v_shifted = np.interp(t_shifted, T_IDXS_MPC, model_v)
    a_shifted = np.interp(t_shifted, T_IDXS_MPC, model_a)
    a_launch = get_accel_from_plan(v_shifted, a_shifted, T_IDXS_MPC, action_t=action_t)
    a_launch_max = float(np.interp(v_ego, [LAUNCH_MOVING_SPEED, LAUNCH_DISARM_SPEED], [LAUNCH_MAX_ACCEL, 0.]))
    boosted = max(a_e2e, min(a_launch, a_launch_max))
    self.active = boosted > a_e2e
    return boosted
