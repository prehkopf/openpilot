"""RehkopfPilot green-light launch: raises the model's accel only for a committed launch from a stop."""
import numpy as np
import pytest

from openpilot.selfdrive.controls.lib.launch_boost import LAUNCH_DISARM_SPEED, LAUNCH_MAX_ACCEL, GreenLightLaunch
from openpilot.selfdrive.modeld.constants import ModelConstants

T = np.array(ModelConstants.T_IDXS)
ACTION_T = 0.55  # Odyssey actuator delay 0.5 s + one model step


def plan(creep_s=1.0, accel=1.0):
  """Model plan that creeps (stays still) for creep_s, then accelerates at `accel`."""
  v = np.clip((T - creep_s) * accel, 0.0, None)
  a = np.where(T >= creep_s, accel, 0.0)
  return v.tolist(), a.tolist()


def armed_launch():
  g = GreenLightLaunch()
  v, a = plan()
  g.update(True, 0.0, True, 0.1, False, v, a, ACTION_T)  # stopped: arms
  return g, v, a


def test_not_armed_without_a_stop():
  g = GreenLightLaunch()
  v, a = plan()
  assert g.update(False, 0.5, True, 0.2, False, v, a, ACTION_T) == 0.2
  assert not g.active


def test_launch_raises_model_accel_within_cap():
  g, v, a = armed_launch()
  out = g.update(False, 0.3, True, 0.2, False, v, a, ACTION_T)
  assert 0.2 < out <= LAUNCH_MAX_ACCEL
  assert out > 0.8  # the shifted plan is already accelerating at 1.0 m/s^2
  assert g.active


@pytest.mark.parametrize("is_e2e, should_stop", [(False, False), (True, True)])
def test_no_launch_when_not_model_mode_or_model_wants_to_stop(is_e2e, should_stop):
  g, v, a = armed_launch()
  assert g.update(False, 0.3, is_e2e, 0.2, should_stop, v, a, ACTION_T) == 0.2
  assert not g.active


def test_no_launch_when_model_does_not_plan_to_move():
  g = GreenLightLaunch()
  v, a = plan(creep_s=3.0, accel=0.5)  # 0.25 m/s by 3.5 s: not committed
  g.update(True, 0.0, True, 0.0, False, v, a, ACTION_T)
  assert g.update(False, 0.1, True, 0.05, False, v, a, ACTION_T) == 0.05


def test_cap_fades_to_zero_at_disarm_speed():
  g, v, a = armed_launch()
  assert g.update(False, LAUNCH_DISARM_SPEED, True, 0.2, False, v, a, ACTION_T) == 0.2
  g2, v, a = armed_launch()
  slow = g2.update(False, 1.2, True, 0.0, False, v, a, ACTION_T)
  g3, v, a = armed_launch()
  faster = g3.update(False, 1.8, True, 0.0, False, v, a, ACTION_T)
  assert slow > faster >= 0.0


def test_disarms_above_disarm_speed_until_next_stop():
  g, v, a = armed_launch()
  g.update(False, LAUNCH_DISARM_SPEED + 0.5, True, 0.2, False, v, a, ACTION_T)
  # slowing back down without stopping does not re-arm
  assert g.update(False, 0.5, True, 0.2, False, v, a, ACTION_T) == 0.2
  g.update(True, 0.0, True, 0.0, False, v, a, ACTION_T)
  assert g.update(False, 0.3, True, 0.2, False, v, a, ACTION_T) > 0.2


def test_never_lowers_the_model_accel():
  g, v, a = armed_launch()
  assert g.update(False, 0.3, True, 1.9, False, v, a, ACTION_T) == 1.9


def test_malformed_model_output_is_ignored():
  g, _, _ = armed_launch()
  assert g.update(False, 0.3, True, 0.2, False, [0.0] * 5, [0.0] * 5, ACTION_T) == 0.2
