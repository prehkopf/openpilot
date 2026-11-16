"""RehkopfPilot (Jasper): finish a model (e2e) stop at the stop point instead of creeping past it.

Param FirmStops, default off (off = the planner as before; this class then returns its inputs unchanged).

Why: on 00000086--791f5e1d12--24 (red light, Experimental mode, no lead) the driving model planned an exponential
finish: its planned stop point kept moving ahead of the van (2.5 m at 4.3 mph, still 0.7 m at 1.9 mph) and its
acceleration faded with speed (-0.98, -0.63, -0.38 m/s^2 over the last 3 s). shouldStop needs vEgo < 0.3 m/s, so
long control never reached its stopping state; the van rolled past the stop line and the driver braked at 1.3 mph.

What it does, only while the model's plan ends in a stop and the van is below ARM_SPEED:
- latches the model's planned stop point and never lets it recede (it may only move closer);
- asks for the constant deceleration that stops AIM_PAST_MODEL beyond it: v^2 / (2 * (distance + AIM_PAST_MODEL)).
  The model's planned stop at walking pace sits short of where a clean stop ends: on 00000006--387f6e3153--22 (an
  e2e stop nobody had to correct) the latched point was 3.45 m ahead at 2.5 m/s and the van stopped at 4.13 m.
  On the creeping stop the latched point was 2.59 m ahead and the van was still rolling at 4.34 m;
- takes that only when it is firmer than the model, at most MAX_EXTRA_DECEL firmer, never below MIN_ACCEL, and
  ramps it in at MAX_JERK;
- asserts shouldStop below STOP_SPEED (0.5 m/s instead of 0.3) so long control's stopping state holds the van.
It disarms as soon as the model stops planning a stop for RELEASE_T (light turned green) or the van is stopped.
It only ever lowers the model candidate; the planner still takes the minimum with the MPC and cruise targets.
"""
import numpy as np

ARM_SPEED = 4.0  # m/s (~9 mph); above this the model's own approach is left alone
MODEL_STOP_V = 0.3  # m/s; where the model's planned velocity counts as stopped
MAX_STOP_DIST = 25.0  # m; a planned stop further than this is not latched
AIM_PAST_MODEL = 0.7  # m; aim this far past the latched model stop point (its walking-pace bias, see above)
MIN_DIST = 0.3  # m; the remaining distance used for the required deceleration never drops below this
MIN_ACCEL = -1.5  # m/s^2; firmest finish this asks for
MAX_EXTRA_DECEL = 1.0  # m/s^2; at most this much firmer than the model
MAX_JERK = 2.0  # m/s^3; how fast the extra deceleration ramps in
STOP_SPEED = 0.5  # m/s; shouldStop below this while finishing a stop
RELEASE_T = 0.5  # s; the model must stop planning a stop for this long to disarm


def model_stop_distance(velocity_x, position_x) -> float | None:
  """Distance along the model plan to the first point slower than MODEL_STOP_V, or None if the plan doesn't stop."""
  if len(velocity_x) == 0 or len(velocity_x) != len(position_x):
    return None
  v = np.asarray(velocity_x, dtype=float)
  slow = np.flatnonzero(v < MODEL_STOP_V)
  if len(slow) == 0:
    return None
  return max(float(position_x[slow[0]]), 0.0)


class FirmStop:
  def __init__(self, dt: float):
    self.dt = dt
    self.enabled = False
    self.reset()

  def reset(self):
    self.remaining = None  # m to the latched stop point, or None when not armed
    self.no_stop_t = 0.0
    self.extra = 0.0  # m/s^2 of deceleration added below the model, >= 0
    self.active = False

  def update(self, enabled: bool, is_e2e: bool, long_active: bool, standstill: bool, v_ego: float,
             a_e2e: float, should_stop_e2e: bool, velocity_x, position_x) -> tuple[float, bool]:
    """Returns the model (e2e) accel target and shouldStop, firmed up while finishing a stop."""
    self.enabled = enabled
    self.active = False
    if not (enabled and is_e2e and long_active) or standstill:
      self.reset()
      return a_e2e, should_stop_e2e

    # dead-reckon the latched point, then let a closer model stop point pull it in (never push it out)
    if self.remaining is not None:
      self.remaining -= max(v_ego, 0.0) * self.dt
    d_model = model_stop_distance(velocity_x, position_x)
    if d_model is None or d_model > MAX_STOP_DIST:
      # the model no longer plans a stop: add nothing now, and drop the latch once that has lasted RELEASE_T
      self.no_stop_t += self.dt
      self.extra = 0.0
      if self.no_stop_t >= RELEASE_T - 1e-6:
        self.reset()
      return a_e2e, should_stop_e2e
    else:
      self.no_stop_t = 0.0
      if self.remaining is not None:
        self.remaining = min(self.remaining, d_model)
      elif v_ego < ARM_SPEED:
        self.remaining = d_model

    if self.remaining is None:
      return a_e2e, should_stop_e2e

    dist = max(self.remaining + AIM_PAST_MODEL, MIN_DIST)
    a_need = max(-(v_ego ** 2) / (2.0 * dist), MIN_ACCEL)
    extra_target = float(np.clip(a_e2e - a_need, 0.0, MAX_EXTRA_DECEL))
    # ramp extra deceleration in at MAX_JERK; let it go immediately
    self.extra = min(extra_target, self.extra + MAX_JERK * self.dt)
    a_out = max(a_e2e - self.extra, MIN_ACCEL) if self.extra > 0.0 else a_e2e
    a_out = min(a_out, a_e2e)
    self.active = a_out < a_e2e
    should_stop = should_stop_e2e or (v_ego < STOP_SPEED and a_out < 0.1)
    return float(a_out), bool(should_stop)
