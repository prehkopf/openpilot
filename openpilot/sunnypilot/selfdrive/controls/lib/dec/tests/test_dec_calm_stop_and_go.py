"""RehkopfPilot: DEC holds blended until a slowdown has really cleared, then lets the speed back up gently.

Route 24 (2026-10-25, stop-and-go uphill into a rail crossing): DEC switched every ~6 s, ACC accelerating at up to +1.0 m/s^2
between blended stretches braking at -1.0 m/s^2.
"""
from types import SimpleNamespace

import openpilot.sunnypilot.selfdrive.controls.lib.dec.dec as dec_module
from openpilot.sunnypilot.selfdrive.controls.lib.dec.dec import DynamicExperimentalController, TRAJECTORY_SIZE

V_KPH = 30.0  # expects an 86 m path at this speed
CLEAR, SLOWING, BAND, STOP = 200.0, 60.0, 79.0, 10.0  # path end x (m): urgency ~0, ~0.6, ~0.17 (between release and trigger), >0.7


class Params:
  def get_bool(self, name):
    return True


def sm(endpoint_x, v_kph=V_KPH, standstill=False, experimental=True):
  xs = [endpoint_x * i / (TRAJECTORY_SIZE - 1) for i in range(TRAJECTORY_SIZE)]
  return {
    'carState': SimpleNamespace(vEgo=v_kph / 3.6, vCruise=80.0, standstill=standstill),
    'radarState': SimpleNamespace(leadOne=SimpleNamespace(present=0.0)),
    'modelV2': SimpleNamespace(position=SimpleNamespace(x=xs), orientation=SimpleNamespace(x=xs, z=[0.0] * TRAJECTORY_SIZE)),
    'selfdriveState': SimpleNamespace(experimentalMode=experimental),
  }


def controller():
  return DynamicExperimentalController(SimpleNamespace(radarUnavailable=True), SimpleNamespace(crash_cnt=0), params=Params())


def run(c, s, n):
  for _ in range(n):
    c.update(s)
  return c.mode()


def slowed_down(c):
  assert run(c, sm(SLOWING), 60) == 'blended' and c.reason() == 'slowing'


def test_slowdown_holds_blended_until_the_path_has_been_clear():
  c = controller()
  slowed_down(c)
  first_clear = None
  for frame in range(400):
    c.update(sm(CLEAR))
    if first_clear is None and c._urgency < dec_module.RELEASE_URGENCY:
      first_clear = frame
    if c.mode() == 'acc':
      break
  assert first_clear is not None and c.mode() == 'acc'
  assert frame - first_clear >= dec_module.RELEASE_HOLD_FRAMES - 1


def test_band_between_release_and_trigger_keeps_blended_but_not_forever():
  c = controller()
  slowed_down(c)
  # the old single threshold switched to ACC here: urgency ~0.17 is under the 0.24 trigger
  assert run(c, sm(BAND), 60) == 'blended'
  # ... but not forever: within 8 s (hold limit 5 s + switching) DEC is back in ACC
  assert run(c, sm(BAND), 160) == 'acc'


def test_emergency_stop_still_switches_as_fast_as_before():
  # the urgency filter takes 4 frames (0.2 s) to cross the emergency level, with or without the hold
  c = controller()
  assert run(c, sm(CLEAR), 40) == 'acc'
  assert run(c, sm(STOP, v_kph=50.0), 4) == 'blended' and c.reason() == 'stopAhead'


def test_pulling_away_from_a_stop_is_not_held():
  c = controller()
  # waiting at a red light: stopped, short path ahead
  assert run(c, sm(STOP, v_kph=0.0, standstill=True), 60) == 'blended' and c.reason() == 'stopped'
  # green: rolling with a clear path. Back to ACC in 25 frames as before the change (holding would take ~36)
  assert run(c, sm(CLEAR, v_kph=8.0), 30) == 'acc'


def _after_slowdown():
  c = controller()
  slowed_down(c)
  while c.mode() == 'blended':
    c.update(sm(CLEAR))
  return c


def test_gentle_acceleration_for_a_few_seconds_after_a_slowdown():
  c = _after_slowdown()
  assert c.accel_cap() == dec_module.POST_SLOWDOWN_ACCEL_MAX
  run(c, sm(CLEAR), dec_module.POST_SLOWDOWN_FRAMES)
  assert c.accel_cap() == float('inf')


def test_no_cap_at_highway_speed_or_standstill_or_when_dec_is_off():
  c = _after_slowdown()
  c.update(sm(CLEAR, v_kph=60.0))  # 16.7 m/s, above POST_SLOWDOWN_SPEEDS
  assert c.accel_cap() == float('inf')
  c = _after_slowdown()
  c.update(sm(CLEAR, v_kph=3.0))  # pulling away from a stop
  assert c.accel_cap() == float('inf')
  c = _after_slowdown()
  c.update(sm(CLEAR, experimental=False))  # DEC inactive: behaves exactly as without it
  assert c.accel_cap() == float('inf')


def test_no_cap_without_a_slowdown():
  c = controller()
  assert run(c, sm(CLEAR), 200) == 'acc'
  assert c.accel_cap() == float('inf')
  # a stop isn't a slowdown episode: pulling away keeps full acceleration
  run(c, sm(CLEAR, v_kph=0.0, standstill=True), 40)
  run(c, sm(CLEAR), 30)
  assert c.mode() == 'acc' and c.accel_cap() == float('inf')
