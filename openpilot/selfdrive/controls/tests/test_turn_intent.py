"""RehkopfPilot: a blinker with recent braking, or with a navigation turn on that side coming up, is a turn, not a
lane change (desire_helper TURN_INTENT_BRAKE_WINDOW, nav_turn_on_blinker_side)."""
import time
from types import SimpleNamespace

from openpilot.cereal import log
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.desire_helper import (DesireHelper, NAV_INSTRUCTION_MAX_AGE, TURN_INTENT_BRAKE_WINDOW,
                                                            fresh_nav_instruction, nav_turn_on_blinker_side)

LaneChangeState = log.LaneChangeState
MPH = 0.44704


def cs(v_mph=35, left=False, brake=False, torque=0.0):
  return SimpleNamespace(vEgo=v_mph * MPH, leftBlinker=left, rightBlinker=False, brakePressed=brake,
                         steeringPressed=torque != 0, steeringTorque=torque, leftBlindspot=False, rightBlindspot=False)


def nav(modifier, distance, maneuver_type='turn'):
  return SimpleNamespace(maneuverModifier=modifier, maneuverDistance=distance, maneuverType=maneuver_type)


def run(dh, c, seconds, nav_instruction=None):
  for _ in range(round(seconds / DT_MDL)):
    dh.update(c, True, 1.0, nav_instruction=nav_instruction)
  return dh.lane_change_state


class TestTurnIntent:
  def test_steady_lane_change_unchanged(self):
    dh = DesireHelper()
    run(dh, cs(), 0.5)
    assert run(dh, cs(left=True), 0.2) == LaneChangeState.preLaneChange
    assert run(dh, cs(left=True, torque=200), 0.1) == LaneChangeState.laneChangeStarting

  def test_blinker_while_braking_is_a_turn(self):
    dh = DesireHelper()
    run(dh, cs(), 0.5)
    # slowing for a turn: no prompt, and steering into the turn is not a nudge
    assert run(dh, cs(left=True, brake=True), 1.0) == LaneChangeState.off
    assert run(dh, cs(left=True, brake=True, torque=200), 0.5) == LaneChangeState.off
    assert dh.desire == log.Desire.none

  def test_brake_after_prompt_cancels_it(self):
    dh = DesireHelper()
    run(dh, cs(), 0.5)
    assert run(dh, cs(left=True), 0.3) == LaneChangeState.preLaneChange
    assert run(dh, cs(left=True, brake=True), 0.1) == LaneChangeState.off
    # still within the window after releasing the brake: steering is not a nudge
    assert run(dh, cs(left=True, torque=200), TURN_INTENT_BRAKE_WINDOW / 2) == LaneChangeState.off

  def test_lane_change_offered_once_braking_is_over(self):
    dh = DesireHelper()
    run(dh, cs(), 0.5)
    run(dh, cs(left=True, brake=True), 0.5)
    # brake released, blinker still on: after the window the lane change is offered again
    assert run(dh, cs(left=True), TURN_INTENT_BRAKE_WINDOW + 0.2) == LaneChangeState.preLaneChange
    assert run(dh, cs(left=True, torque=200), 0.1) == LaneChangeState.laneChangeStarting

  def test_blinker_off_resets(self):
    dh = DesireHelper()
    run(dh, cs(), 0.5)
    run(dh, cs(left=True, brake=True), 0.5)
    run(dh, cs(), 0.5)
    assert not dh.turn_intent_held
    # a fresh blinker at steady speed long after braking behaves like stock
    run(dh, cs(), TURN_INTENT_BRAKE_WINDOW)
    assert run(dh, cs(left=True), 0.1) == LaneChangeState.preLaneChange


class FakeSubMaster:
  def __init__(self, msg, valid=True, age=0.0):
    self.msg = msg
    self.valid = {"navInstruction": valid}
    self.recv_time = {"navInstruction": time.monotonic() - age}

  def __getitem__(self, key):
    return self.msg


class TestNavTurnIntent:
  def test_turn_on_the_gas_with_a_route_is_not_a_lane_change(self):
    # the 2026-10-23 pattern: 45 mph, on the gas, blinker for a left turn 150 m ahead, steering into it
    dh = DesireHelper()
    turn = nav("left", 150)
    run(dh, cs(45), 0.5, turn)
    assert run(dh, cs(45, left=True), 0.5, turn) == LaneChangeState.off
    assert run(dh, cs(45, left=True, torque=200), 0.5, turn) == LaneChangeState.off
    assert dh.desire == log.Desire.none

  def test_lane_change_offered_after_the_turn_clears(self):
    dh = DesireHelper()
    run(dh, cs(45), 0.5, nav("left", 150))
    run(dh, cs(45, left=True), 0.5, nav("left", 150))
    # the route moves on to a far maneuver: the held lane change is offered again
    assert run(dh, cs(45, left=True), 0.2, nav("right", 2000)) == LaneChangeState.preLaneChange
    assert run(dh, cs(45, left=True, torque=200), 0.1, nav("right", 2000)) == LaneChangeState.laneChangeStarting

  def test_other_side_far_or_slight_maneuvers_keep_lane_changes(self):
    for instruction in (nav("right", 150), nav("left", 600), nav("slight left", 100, "off ramp"), nav("straight", 50), None):
      dh = DesireHelper()
      run(dh, cs(60), 0.5, instruction)
      assert run(dh, cs(60, left=True), 0.2, instruction) == LaneChangeState.preLaneChange, instruction
      assert run(dh, cs(60, left=True, torque=200), 0.1, instruction) == LaneChangeState.laneChangeStarting, instruction

  def test_reach_grows_with_speed_and_is_bounded(self):
    left = cs(0, left=True)
    assert nav_turn_on_blinker_side(left, nav("left", 29))
    assert not nav_turn_on_blinker_side(left, nav("left", 31))
    fast = cs(80, left=True)  # 15 + 35.8 m/s * 12 s = 444 m, capped at 250 m
    assert nav_turn_on_blinker_side(fast, nav("sharp left", 249))
    assert not nav_turn_on_blinker_side(fast, nav("left", 251))
    assert not nav_turn_on_blinker_side(fast, nav("left", -5))
    assert not nav_turn_on_blinker_side(cs(45), nav("left", 50))  # no blinker

  def test_stale_or_invalid_instruction_is_ignored(self):
    msg = nav("left", 100)
    assert fresh_nav_instruction(FakeSubMaster(msg)) is msg
    assert fresh_nav_instruction(FakeSubMaster(msg, age=NAV_INSTRUCTION_MAX_AGE + 0.5)) is None
    assert fresh_nav_instruction(FakeSubMaster(msg, valid=False)) is None
