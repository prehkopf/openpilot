from types import SimpleNamespace

from openpilot.cereal import log
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.highway_following import (CATCHUP_EXTRA_ACCEL, LANE_CHANGE_T_FOLLOW, LaneChangeGap,
                                                                catchup_accel)

LCS = log.LaneChangeState
LCD = log.LaneChangeDirection
MPH = CV.MPH_TO_MS
T_AGGRESSIVE = 1.25


def lead(d=40.0, v=30.0, a=0.0, y=0.0, present=True, radar=False, prob=0.95):
  # vision-only by default: with openpilot longitudinal the Odyssey's radar is silenced
  return SimpleNamespace(dRel=d, vLead=v, aLeadK=a, yRel=y, present=present, radar=radar, modelProb=prob)


def run_gap(gap, seconds, state=LCS.preLaneChange, direction=LCD.left, v=70 * MPH, standstill=False,
            left_bsm=False, right_bsm=False, ld=None):
  t = None
  for _ in range(round(seconds / DT_MDL)):
    t = gap.update(T_AGGRESSIVE, v, standstill, state, direction, left_bsm, right_bsm, ld or lead())
  return t


class TestLaneChangeGap:
  def test_no_lane_change_keeps_personality_gap(self):
    assert run_gap(LaneChangeGap(), 2.0, state=LCS.off) == T_AGGRESSIVE

  def test_ramps_in_while_signalling_and_out_after(self):
    gap = LaneChangeGap()
    halfway = run_gap(gap, 0.4)
    assert LANE_CHANGE_T_FOLLOW < halfway < T_AGGRESSIVE  # ramped, not a step
    assert abs(run_gap(gap, 1.0, state=LCS.laneChangeStarting) - LANE_CHANGE_T_FOLLOW) < 1e-6
    back = run_gap(gap, 0.05, state=LCS.off)
    assert LANE_CHANGE_T_FOLLOW < back < T_AGGRESSIVE
    assert run_gap(gap, 0.5, state=LCS.off) == T_AGGRESSIVE

  def test_blindspot_lead_braking_slow_or_stopped_block_it(self):
    for kwargs in ({"left_bsm": True}, {"ld": lead(a=-1.0)}, {"v": 15 * MPH}, {"standstill": True}):
      assert run_gap(LaneChangeGap(), 2.0, **kwargs) == T_AGGRESSIVE, kwargs
    # the blind spot on the other side does not matter
    assert abs(run_gap(LaneChangeGap(), 2.0, right_bsm=True) - LANE_CHANGE_T_FOLLOW) < 1e-6

  def test_safety_gate_snaps_back(self):
    gap = LaneChangeGap()
    run_gap(gap, 2.0)
    assert run_gap(gap, DT_MDL, ld=lead(a=-1.2)) == T_AGGRESSIVE

  def test_never_longer_than_the_personality_gap(self):
    gap = LaneChangeGap()
    for _ in range(50):
      assert gap.update(0.6, 30.0, False, LCS.preLaneChange, LCD.left, False, False, lead()) <= 0.6


class TestCatchup:
  def test_full_effect_when_lead_hangs_far_beyond_the_gap(self):
    # 70 mph, set 80, lead at our speed ~2.0 s ahead with a 1.25 s target
    v = 70 * MPH
    assert abs(catchup_accel(v, 80 * MPH, T_AGGRESSIVE, lead(d=2.0 * v + 6, v=v)) - CATCHUP_EXTRA_ACCEL) < 0.02

  def test_off_cases(self):
    v = 70 * MPH
    far = lead(d=2.0 * v + 6, v=v)
    assert catchup_accel(v, v, T_AGGRESSIVE, far) == 0.0  # at set speed
    assert catchup_accel(35 * MPH, 80 * MPH, T_AGGRESSIVE, lead(d=2.0 * 35 * MPH + 6, v=35 * MPH)) == 0.0  # city
    assert catchup_accel(v, 80 * MPH, T_AGGRESSIVE, lead(d=1.3 * v + 6, v=v)) == 0.0  # at the target gap
    assert catchup_accel(v, 80 * MPH, T_AGGRESSIVE, lead(d=4.0 * v, v=v)) == 0.0  # too far to count
    assert catchup_accel(v, 80 * MPH, T_AGGRESSIVE, lead(d=2.0 * v + 6, v=v - 4)) == 0.0  # already closing fast
    assert catchup_accel(v, 80 * MPH, T_AGGRESSIVE, lead(d=2.0 * v + 6, v=v, y=2.0)) == 0.0  # not in our path
    assert catchup_accel(v, 80 * MPH, T_AGGRESSIVE, lead(d=2.0 * v + 6, v=v, prob=0.5)) == 0.0  # unsure vision lead
    assert catchup_accel(v, 80 * MPH, T_AGGRESSIVE, lead(present=False)) == 0.0

  def test_radar_lead_counts_even_with_low_model_prob(self):
    v = 70 * MPH
    assert catchup_accel(v, 80 * MPH, T_AGGRESSIVE, lead(d=2.0 * v + 6, v=v, radar=True, prob=0.2)) > 0.0

  def test_bounded(self):
    for d in range(10, 300, 5):
      for dv in (-5, -2, 0, 2, 5):
        out = catchup_accel(30.0, 36.0, T_AGGRESSIVE, lead(d=float(d), v=30.0 + dv))
        assert 0.0 <= out <= CATCHUP_EXTRA_ACCEL
