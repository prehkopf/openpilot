"""RehkopfPilot: DEC publishes why it chose blended mode (dec.reason())."""
from types import SimpleNamespace

from openpilot.sunnypilot.selfdrive.controls.lib.dec.dec import DynamicExperimentalController, TRAJECTORY_SIZE, CURVE_YAW


class Params:
  def get_bool(self, name):
    return True


def sm(v_kph=50.0, standstill=False, lead=False, endpoint_x=200.0, end_yaw=0.0):
  xs = [endpoint_x * i / (TRAJECTORY_SIZE - 1) for i in range(TRAJECTORY_SIZE)]
  yaws = [end_yaw * i / (TRAJECTORY_SIZE - 1) for i in range(TRAJECTORY_SIZE)]
  return {
    'carState': SimpleNamespace(vEgo=v_kph / 3.6, vCruise=80.0, standstill=standstill),
    'radarState': SimpleNamespace(leadOne=SimpleNamespace(present=1.0 if lead else 0.0)),
    'modelV2': SimpleNamespace(position=SimpleNamespace(x=xs), orientation=SimpleNamespace(x=xs, z=yaws)),
    'selfdriveState': SimpleNamespace(experimentalMode=True),
  }


def controller(crash_cnt=0):
  return DynamicExperimentalController(SimpleNamespace(radarUnavailable=False), SimpleNamespace(crash_cnt=crash_cnt), params=Params())


def run(c, s, n=40):
  for _ in range(n):
    c.update(s)
  return c.mode(), c.reason()


def test_acc_has_no_reason():
  assert run(controller(), sm()) == ('acc', 'none')


def test_short_straight_path_is_stop_ahead():
  # path ends at 10 m while ~130 m is expected at 50 km/h: a stop or light ahead
  assert run(controller(), sm(endpoint_x=10.0)) == ('blended', 'stopAhead')


def test_short_turning_path_is_curve():
  assert run(controller(), sm(endpoint_x=10.0, end_yaw=CURVE_YAW + 0.2)) == ('blended', 'curve')


def test_standstill_is_stopped():
  assert run(controller(), sm(v_kph=0.0, standstill=True, endpoint_x=200.0)) == ('blended', 'stopped')


def test_fcw_is_collision():
  assert run(controller(crash_cnt=1), sm(), n=2) == ('blended', 'collision')


def test_reason_clears_when_back_in_acc():
  c = controller()
  run(c, sm(endpoint_x=10.0))
  mode, reason = run(c, sm(lead=True), n=200)
  assert (mode, reason) == ('acc', 'none')
