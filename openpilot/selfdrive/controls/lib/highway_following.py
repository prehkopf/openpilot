"""RehkopfPilot: highway following ideas from StarPilot (firestar5683/StarPilot, starpilot_following.py and
lead_behavior.py), adapted to this planner, where the MPC follows leads and cruise is a separate candidate.

- Lane-change close-gap: while signalling out of the lane, shorten the follow time so the van accelerates into
  the pass instead of braking behind the car it is leaving.
- Tracked-lead catch-up: on the highway, below set speed, with a lead well beyond the target gap, let the
  cruise candidate accelerate a little harder so the van closes the gap sooner. The MPC still holds the gap.
"""
from openpilot.cereal import log
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import get_safe_obstacle_distance, get_stopped_equivalence_factor

LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection

LANE_CHANGE_ACTIVE_STATES = (LaneChangeState.preLaneChange, LaneChangeState.laneChangeStarting)
LANE_CHANGE_T_FOLLOW = 0.75  # s; StarPilot's default is 0.6, its floor 0.25
LANE_CHANGE_MIN_SPEED = 20 * CV.MPH_TO_MS  # same as the lane-change minimum
LANE_CHANGE_GAP_RAMP_IN = 0.6  # s of headway per s, toward the shorter gap
LANE_CHANGE_GAP_RAMP_OUT = 4.0  # s of headway per s, back to the normal gap
LANE_CHANGE_ABORT_LEAD_BRAKE = 0.8  # m/s^2 of lead braking that cancels the shorter gap

CATCHUP_MIN_SPEED = 45 * CV.MPH_TO_MS
CATCHUP_FULL_SPEED = 52 * CV.MPH_TO_MS
CATCHUP_CRUISE_ERROR_FULL = 1.5  # m/s below set speed for full effect
CATCHUP_MARGIN_START, CATCHUP_MARGIN_FULL = 0.40, 0.70  # s of headway beyond the target gap
CATCHUP_FADE_ABSOLUTE = (2.75, 3.10)  # s of total headway where a far lead stops counting
CATCHUP_MAX_LATERAL = (0.9, 1.6)  # m off our path where the lead fades out
CATCHUP_EXTRA_ACCEL = 0.3  # m/s^2 added to the cruise ceiling at full effect
# With openpilot longitudinal the Odyssey's radar is silenced, so every lead is vision-only (radar=False on all
# 2026-10-23 drives). Accept a vision lead the model is sure of; StarPilot uses the same 0.7 for vision leads.
CATCHUP_MIN_MODEL_PROB = 0.7


def smoothstep(value: float, start: float, end: float) -> float:
  f = min(1.0, max(0.0, (value - start) / max(end - start, 1e-3)))
  return f * f * (3.0 - 2.0 * f)


class LaneChangeGap:
  def __init__(self):
    self.t_follow = None

  def update(self, t_follow: float, v_ego: float, standstill: bool, lane_change_state, lane_change_direction,
             left_blindspot: bool, right_blindspot: bool, lead) -> float:
    """The follow time to use this cycle: never longer than t_follow, shorter while a lane change is under way."""
    target = t_follow
    blindspot = ((lane_change_direction == LaneChangeDirection.left and left_blindspot) or
                 (lane_change_direction == LaneChangeDirection.right and right_blindspot))
    lead_braking = lead.present and -lead.aLeadK >= LANE_CHANGE_ABORT_LEAD_BRAKE
    if (lane_change_state in LANE_CHANGE_ACTIVE_STATES and not standstill and v_ego >= LANE_CHANGE_MIN_SPEED and
        not blindspot and not lead_braking):
      target = min(t_follow, LANE_CHANGE_T_FOLLOW)

    if self.t_follow is None:
      self.t_follow = t_follow
    if target < self.t_follow:
      self.t_follow = max(target, self.t_follow - LANE_CHANGE_GAP_RAMP_IN * DT_MDL)
    elif lead_braking or blindspot:
      self.t_follow = target  # snap back when the safety gate trips
    else:
      self.t_follow = min(target, self.t_follow + LANE_CHANGE_GAP_RAMP_OUT * DT_MDL)
    return min(t_follow, self.t_follow)


def catchup_accel(v_ego: float, v_cruise: float, t_follow: float, lead) -> float:
  """Extra cruise acceleration (m/s^2) while a tracked lead sits well beyond the target gap."""
  if not (lead.present and (lead.radar or lead.modelProb >= CATCHUP_MIN_MODEL_PROB)) or v_ego < 1.0:
    return 0.0
  desired_gap = get_safe_obstacle_distance(v_ego, t_follow) - get_stopped_equivalence_factor(lead.vLead)  # the MPC's gap
  if lead.dRel <= desired_gap:
    return 0.0
  desired_hw = desired_gap / v_ego
  margin = lead.dRel / v_ego - desired_hw
  closing_speed = max(0.0, v_ego - lead.vLead)
  factor = (smoothstep(v_ego, CATCHUP_MIN_SPEED, CATCHUP_FULL_SPEED) *
            smoothstep(v_cruise - v_ego, 0.0, CATCHUP_CRUISE_ERROR_FULL) *
            smoothstep(margin, CATCHUP_MARGIN_START, CATCHUP_MARGIN_FULL) *
            (1.0 - smoothstep(margin, max(0.75, CATCHUP_FADE_ABSOLUTE[0] - desired_hw), max(1.05, CATCHUP_FADE_ABSOLUTE[1] - desired_hw))) *
            (1.0 - smoothstep(closing_speed, max(1.75, 0.08 * v_ego), max(2.5, 0.12 * v_ego))) *
            (1.0 - smoothstep(abs(lead.yRel), *CATCHUP_MAX_LATERAL)))
  return CATCHUP_EXTRA_ACCEL * factor
