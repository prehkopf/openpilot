import time

import numpy as np

from openpilot.cereal import log, custom
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.sunnypilot.selfdrive.controls.lib.auto_lane_change import AutoLaneChangeController, AutoLaneChangeMode
from openpilot.sunnypilot.selfdrive.controls.lib.lane_turn_desire import LaneTurnController

LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection
TurnDirection = custom.ModelDataV2SP.TurnDirection

LANE_CHANGE_SPEED_MIN = 20 * CV.MPH_TO_MS
LANE_CHANGE_TIME_MAX = 10.
LANE_CHANGE_START_TIME = 0.5
# RehkopfPilot: a blinker while braking (or within this long after braking) means a turn, not a lane change.
# Without this, steering into an intersection turn counts as the lane-change nudge in "nudge" mode.
# Scored on four Odyssey drives: blocks 82% of intersection turns at steer-in, keeps 96% of lane changes.
TURN_INTENT_BRAKE_WINDOW = 2.0  # s
# RehkopfPilot: on a navigation route, a turn coming up on the blinker side is also a turn (idea from StarPilot's
# desire_helper). It catches the turns taken on the gas, which the brake rule misses: 4 of 34 lane changes on the
# 2026-10-23 drives started in a turn at 45-67 mph with no braking. "Slight" maneuvers (exits, forks) stay lane changes.
NAV_TURN_MODIFIERS = {"left": True, "sharp left": True, "right": False, "sharp right": False}  # value: is left
NAV_TURN_LEAD_TIME = 12.0  # s of travel before the maneuver
NAV_TURN_BASE_DISTANCE = 15.0  # m
NAV_TURN_MIN_DISTANCE = 30.0  # m
NAV_TURN_MAX_DISTANCE = 250.0  # m
NAV_INSTRUCTION_MAX_AGE = 2.5  # s; navd publishes at 1 Hz

TURN_DESIRES = {
  TurnDirection.none: log.Desire.none,
  TurnDirection.turnLeft: log.Desire.turnLeft,
  TurnDirection.turnRight: log.Desire.turnRight,
}

def fresh_nav_instruction(sm):
  """The latest navInstruction if navd sent a valid one recently, else None."""
  if not sm.valid['navInstruction'] or time.monotonic() - sm.recv_time['navInstruction'] > NAV_INSTRUCTION_MAX_AGE:
    return None
  return sm['navInstruction']


def nav_turn_on_blinker_side(carstate, nav_instruction) -> bool:
  """A navigation turn matching the blinker is within ~12 s of travel."""
  if nav_instruction is None or carstate.leftBlinker == carstate.rightBlinker:
    return False
  is_left = NAV_TURN_MODIFIERS.get(str(nav_instruction.maneuverModifier).strip().lower())
  if is_left is None or is_left != carstate.leftBlinker:
    return False
  distance = float(nav_instruction.maneuverDistance)
  reach = float(np.clip(NAV_TURN_BASE_DISTANCE + max(carstate.vEgo, 0.0) * NAV_TURN_LEAD_TIME,
                        NAV_TURN_MIN_DISTANCE, NAV_TURN_MAX_DISTANCE))
  return 0.0 <= distance <= reach


class DesireHelper:
  def __init__(self):
    self.lane_change_state = LaneChangeState.off
    self.lane_change_direction = LaneChangeDirection.none
    self.lane_change_timer = 0.0
    self.prev_one_blinker = False
    self.desire = log.Desire.none
    self.alc = AutoLaneChangeController(self)
    self.lane_turn_controller = LaneTurnController(self)
    self.lane_turn_direction = TurnDirection.none
    self.time_since_brake = TURN_INTENT_BRAKE_WINDOW
    self.turn_intent_held = False  # blinker came on (or stayed on) during a turn intent; offer the lane change once it clears

  @staticmethod
  def get_lane_change_direction(CS):
    return LaneChangeDirection.left if CS.leftBlinker else LaneChangeDirection.right

  def update(self, carstate, lateral_active, lane_change_prob, left_edge_detected=False, right_edge_detected=False,
             nav_instruction=None):
    self.alc.update_params()
    self.lane_turn_controller.update_params()
    v_ego = carstate.vEgo
    one_blinker = carstate.leftBlinker != carstate.rightBlinker
    below_lane_change_speed = v_ego < LANE_CHANGE_SPEED_MIN
    self.time_since_brake = 0.0 if carstate.brakePressed else min(self.time_since_brake + DT_MDL, TURN_INTENT_BRAKE_WINDOW)
    turn_intent = self.time_since_brake < TURN_INTENT_BRAKE_WINDOW or nav_turn_on_blinker_side(carstate, nav_instruction)
    if not one_blinker:
      self.turn_intent_held = False

    # Lane turn controller update
    self.lane_turn_controller.update_lane_turn(blindspot_left=carstate.leftBlindspot, blindspot_right=carstate.rightBlindspot,
                                               left_blinker=carstate.leftBlinker, right_blinker=carstate.rightBlinker, v_ego=v_ego)
    self.lane_turn_direction = self.lane_turn_controller.get_turn_direction()

    if not lateral_active or self.lane_change_timer > LANE_CHANGE_TIME_MAX or self.alc.lane_change_set_timer == AutoLaneChangeMode.OFF:
      self.lane_change_state = LaneChangeState.off
      self.lane_change_direction = LaneChangeDirection.none
      self.lane_change_timer = 0.0
    else:
      if self.lane_change_state == LaneChangeState.off and one_blinker and (not self.prev_one_blinker or self.turn_intent_held) \
         and not below_lane_change_speed and turn_intent:
        self.turn_intent_held = True
      elif self.lane_change_state == LaneChangeState.off and one_blinker and (not self.prev_one_blinker or self.turn_intent_held) \
           and not below_lane_change_speed:
        self.turn_intent_held = False
        self.lane_change_state = LaneChangeState.preLaneChange
        self.lane_change_timer = 0.0
        # Initialize lane change direction to prevent UI alert flicker
        self.lane_change_direction = self.get_lane_change_direction(carstate)

      elif self.lane_change_state == LaneChangeState.preLaneChange:
        # Update lane change direction
        self.lane_change_direction = self.get_lane_change_direction(carstate)

        torque_applied = carstate.steeringPressed and \
                         ((carstate.steeringTorque > 0 and self.lane_change_direction == LaneChangeDirection.left) or
                          (carstate.steeringTorque < 0 and self.lane_change_direction == LaneChangeDirection.right))

        blindspot_detected = (((carstate.leftBlindspot or left_edge_detected) and self.lane_change_direction == LaneChangeDirection.left) or
                              ((carstate.rightBlindspot or right_edge_detected) and self.lane_change_direction == LaneChangeDirection.right))

        self.alc.update_lane_change(blindspot_detected, carstate.brakePressed)

        if not one_blinker or below_lane_change_speed:
          self.lane_change_state = LaneChangeState.off
          self.lane_change_direction = LaneChangeDirection.none
          self.lane_change_timer = 0.0
        elif turn_intent:
          # braking with the blinker on: this is a turn. Drop the prompt and don't treat steering as a nudge.
          self.lane_change_state = LaneChangeState.off
          self.lane_change_direction = LaneChangeDirection.none
          self.lane_change_timer = 0.0
          self.turn_intent_held = True
        elif (torque_applied or self.alc.auto_lane_change_allowed) and not blindspot_detected:
          self.lane_change_state = LaneChangeState.laneChangeStarting
          self.lane_change_timer = 0.0

      elif self.lane_change_state == LaneChangeState.laneChangeStarting:
        self.lane_change_timer += DT_MDL

        if lane_change_prob < 0.02 and self.lane_change_timer >= LANE_CHANGE_START_TIME:
          self.lane_change_timer = 0.0
          if one_blinker:
            self.lane_change_state = LaneChangeState.preLaneChange
            self.lane_change_direction = self.get_lane_change_direction(carstate)
          else:
            self.lane_change_state = LaneChangeState.off
            self.lane_change_direction = LaneChangeDirection.none

    self.prev_one_blinker = one_blinker and lateral_active

    if self.lane_turn_direction != TurnDirection.none:
      self.desire = TURN_DESIRES[self.lane_turn_direction]
    else:
      self.desire = log.Desire.none
      if self.lane_change_state == LaneChangeState.laneChangeStarting:
        if self.lane_change_direction == LaneChangeDirection.left:
          self.desire = log.Desire.laneChangeLeft
        elif self.lane_change_direction == LaneChangeDirection.right:
          self.desire = log.Desire.laneChangeRight

    self.alc.update_state()
