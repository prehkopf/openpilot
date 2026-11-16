"""FirmStops (Jasper): off changes nothing; on, a creeping model stop finishes at the latched stop point."""
import numpy as np

from openpilot.selfdrive.controls.lib import firm_stop
from openpilot.selfdrive.controls.lib.firm_stop import FirmStop, model_stop_distance

DT = 0.05
T_IDXS = np.array([10.0 * (i / 32) ** 2 for i in range(33)])  # same shape as ModelConstants.T_IDXS
TAU_CMD = 2.1  # s; the model's commanded finish on 00000086--791f5e1d12--24: a ~= -v / 2.1 over the last 3 s
TAU_PLAN = 1.6  # s; its planned stop point there: ~1.6 * (v - 0.3) ahead (2.5 m at 1.92 m/s, 1.5 m at 1.25 m/s)
VAN_LAG = 0.5  # s; the Odyssey's longitudinal response


def creeping_plan(v):
  """Fitted to the logged red-light finish: the plan says stop ~1.6 * (v - 0.3) ahead, but the commanded acceleration
  is weaker than that plan needs below ~1.5 m/s, so the stop point recedes as the van rolls toward it."""
  vx = v * np.exp(-T_IDXS / TAU_PLAN)
  px = v * TAU_PLAN * (1 - np.exp(-T_IDXS / TAU_PLAN))
  return vx, px, -v / TAU_CMD


def drive(enabled, v0=2.5, secs=8.0, plan=creeping_plan):
  fs = FirmStop(DT)
  x, v, a = 0.0, v0, -v0 / TAU_CMD
  latched = model_stop_distance(*plan(v0)[:2])  # where the model first planned to stop
  cmds = []
  for _ in range(int(secs / DT)):
    vx, px, a_model = plan(v)
    a_cmd, stop = fs.update(enabled, True, True, v < 0.01, v, a_model, False, vx, px)
    if stop:
      a_cmd = min(a_cmd, -1.0)  # long control's stopping state
    cmds.append((a_model, a_cmd, stop))
    a += (a_cmd - a) * DT / VAN_LAG
    v = max(v + a * DT, 0.0)
    x += v * DT
    if v == 0.0:
      break
  return x, v, latched, cmds


def test_design_values():
  # literals on purpose: a test that reads the constant can't catch a change to it
  assert firm_stop.ARM_SPEED == 4.0
  assert firm_stop.MIN_ACCEL == -1.5
  assert firm_stop.MAX_EXTRA_DECEL == 1.0
  assert firm_stop.MAX_JERK == 2.0
  assert firm_stop.STOP_SPEED == 0.5
  assert firm_stop.AIM_PAST_MODEL == 0.7


def test_off_returns_inputs_unchanged():
  fs = FirmStop(DT)
  for v in np.linspace(3.5, 0.2, 80):
    vx, px, a_model = creeping_plan(v)
    for should_stop in (False, True):
      assert fs.update(False, True, True, False, v, a_model, should_stop, vx, px) == (a_model, should_stop)
  assert fs.remaining is None and not fs.active


def test_not_e2e_or_not_long_active_is_unchanged():
  for is_e2e, long_active in ((False, True), (True, False)):
    fs = FirmStop(DT)
    vx, px, a_model = creeping_plan(1.5)
    assert fs.update(True, is_e2e, long_active, False, 1.5, a_model, False, vx, px) == (a_model, False)


def test_creeping_finish_overshoots_without_and_stops_short_with():
  x_off, v_off, latched_off, _ = drive(False)
  x_on, v_on, latched_on, cmds = drive(True)
  # without: the van rolls past where the model first planned to stop (1.3 m by the driver's brake on the logged drive;
  # this kinematic stand-in is milder)
  assert x_off - latched_off > 0.3
  # with: stopped no further than the aim point (latched + 0.7 m), and not far short of the latched point
  assert v_on == 0.0
  assert latched_on - 0.5 < x_on < latched_on + 0.7
  assert x_on < x_off - 0.3
  # never firmer than the model by more than 1.0, never below -1.5 before the stopping state
  for a_model, a_cmd, stop in cmds:
    if not stop:
      assert a_cmd <= a_model + 1e-9
      assert a_cmd >= min(a_model, max(a_model - 1.0, -1.5)) - 1e-9


def test_extra_deceleration_ramps_in_at_the_jerk_limit():
  fs = FirmStop(DT)
  prev_extra = 0.0
  for v in np.linspace(3.0, 1.0, 30):
    vx, px = creeping_plan(v)[:2]
    a_cmd, _ = fs.update(True, True, True, False, v, 0.0, False, vx, px * 0.2)  # stop point much closer than the model's accel says
    assert fs.extra - prev_extra <= 2.0 * DT + 1e-9
    prev_extra = fs.extra


def test_does_not_latch_above_arm_speed():
  fs = FirmStop(DT)
  vx, px, a_model = creeping_plan(6.0)
  assert fs.update(True, True, True, False, 6.0, a_model, False, vx, px) == (a_model, False)
  assert fs.remaining is None


def test_disarms_when_the_model_stops_planning_a_stop():
  fs = FirmStop(DT)
  vx, px, a_model = creeping_plan(2.0)
  fs.update(True, True, True, False, 2.0, a_model, False, vx, px)
  assert fs.remaining is not None
  go_vx, go_px = np.full(33, 3.0), 3.0 * T_IDXS  # light turned green: no stop in the plan
  for _ in range(int(0.5 / DT)):
    out = fs.update(True, True, True, False, 2.0, 0.5, False, go_vx, go_px)
  assert fs.remaining is None
  assert out == (0.5, False)


def test_should_stop_below_half_a_meter_per_second_when_armed():
  fs = FirmStop(DT)
  vx, px, a_model = creeping_plan(0.45)
  _, stop = fs.update(True, True, True, False, 0.45, a_model, False, vx, px)
  assert stop
  vx, px, a_model = creeping_plan(0.6)
  _, stop = FirmStop(DT).update(True, True, True, False, 0.6, a_model, False, vx, px)
  assert not stop


def test_stop_point_only_moves_closer():
  fs = FirmStop(DT)
  vx, px, a_model = creeping_plan(2.0)
  fs.update(True, True, True, False, 2.0, a_model, False, vx, px)
  first = fs.remaining
  fs.update(True, True, True, False, 2.0, a_model, False, vx, px * 3)  # model now says the stop is further away
  assert fs.remaining <= first


def test_model_stop_distance():
  assert model_stop_distance([], []) is None
  assert model_stop_distance([5.0, 4.0, 3.0], [0.0, 4.0, 8.0]) is None
  assert model_stop_distance([2.0, 1.0, 0.2, 0.0], [0.0, 1.0, 1.6, 1.7]) == 1.6
