"""RehkopfPilot: a blinker with recent braking is a turn, not a lane change (desire_helper TURN_INTENT_BRAKE_WINDOW)."""
from types import SimpleNamespace

from openpilot.cereal import log
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper, TURN_INTENT_BRAKE_WINDOW

LaneChangeState = log.LaneChangeState
MPH = 0.44704


def cs(v_mph=35, left=False, brake=False, torque=0.0):
  return SimpleNamespace(vEgo=v_mph * MPH, leftBlinker=left, rightBlinker=False, brakePressed=brake,
                         steeringPressed=torque != 0, steeringTorque=torque, leftBlindspot=False, rightBlindspot=False)


def run(dh, c, seconds):
  for _ in range(round(seconds / DT_MDL)):
    dh.update(c, True, 1.0)
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
