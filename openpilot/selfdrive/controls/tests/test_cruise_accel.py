from types import SimpleNamespace

import numpy as np

from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.longitudinal_planner import A_CRUISE_MAX_BP, J_CRUISE_VALS, get_cruise_accel

CP = SimpleNamespace(steerRatio=16.0, wheelbase=3.0)


def jerk_step(v_ego):
  return float(np.interp(v_ego, A_CRUISE_MAX_BP, J_CRUISE_VALS)) * DT_MDL


def cruise_accel(a_cruise_prev, a_target_prev, v_cruise=20.0, v_ego=25.0, e2e=True):
  return get_cruise_accel(e2e, v_cruise, v_ego, a_cruise_prev, 0.0, CP, DT_MDL, -0.3, True, a_target_prev)


def test_lowered_set_speed_starts_from_lower_planner_output():
  # comma #39127: a_cruise sat at +0.5 while the planner was already braking for a lead (-0.3). Lowering the
  # set speed must continue from -0.3, not spend ~1 s ramping a_cruise down from +0.5 first.
  j = jerk_step(25.0)
  assert abs(cruise_accel(0.5, -0.3) - max(-0.5, -0.3 - j)) < 1e-6


def test_rise_rate_still_limited_from_a_cruise():
  # the upper bound is unchanged: speeding up is still jerk-limited from a_cruise itself
  out = cruise_accel(-0.2, -0.4, v_cruise=30.0, v_ego=20.0)
  assert out <= -0.2 + jerk_step(20.0) + 1e-6


def test_higher_planner_output_does_not_relax_the_lower_bound():
  j = jerk_step(25.0)
  assert abs(cruise_accel(0.0, 0.8) - (0.0 - j)) < 1e-6
