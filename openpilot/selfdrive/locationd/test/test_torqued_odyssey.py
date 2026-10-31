"""Odyssey 3840 steering range: the torque learner keeps sampling and fitting at the stock 2560 count scale (brikowski
ef598cd282, 'preserved physical learning'); tests 1-2 adapted from his test_torqued.py."""
import numpy as np

from opendbc.car import gen_empty_fingerprint
from opendbc.car.honda.interface import CarInterface as HondaInterface
from opendbc.car.honda.values import CAR
from openpilot.cereal import messaging
from openpilot.common.params import Params
from openpilot.common.test import OpenpilotTestCase
from openpilot.selfdrive.locationd.torqued import TorqueEstimator, VERSION


def odyssey():
  return HondaInterface.get_params(CAR.HONDA_ODYSSEY_5G_MMR, gen_empty_fingerprint(), [], True, False, False)


class TestTorquedOdysseyScale(OpenpilotTestCase):
  def test_expanded_range_preserves_physical_learning_samples_and_fit(self):
    current = odyssey()
    stock = current.as_reader().as_builder()
    stock.carFingerprint = 'mock'
    stock.lateralTuning.torque.latAccelFactor = .9
    stock.lateralTuning.torque.friction = .2
    baseline, candidate = (TorqueEstimator(cp) for cp in (stock, current))
    rng = np.random.default_rng(42)
    for torque, noise in zip(np.linspace(-.8, .8, 20000), rng.normal(0., .03, 20000), strict=True):
      response = .9 * torque + .1 * np.sign(torque) + noise
      baseline.filtered_points.add_point(torque, response)
      candidate.filtered_points.add_point(torque / 1.5, response)
    assert baseline.filtered_points.is_valid() and candidate.filtered_points.is_valid()
    for old, new in zip(baseline.filtered_points.buckets.values(), candidate.filtered_points.buckets.values(), strict=True):
      np.testing.assert_allclose(old.arr[:, 0], new.arr[:, 0] * 1.5, atol=1e-14)
      np.testing.assert_array_equal(old.arr[:, 1:], new.arr[:, 1:])
    baseline.filtered_points._rng = np.random.default_rng(1)
    candidate.filtered_points._rng = np.random.default_rng(1)
    factor, offset, friction = baseline.estimate_params()
    np.testing.assert_allclose(candidate.estimate_params(), [factor * 1.5, offset, friction / 1.5], atol=1e-14)

  def test_minimum_learning_torque_remains_in_physical_counts(self):
    cp = odyssey()
    for count in (-52, -50, 50, 52):
      est = TorqueEstimator(cp)
      for key in ('carControl_t', 'carOutput_t', 'carState_t'):
        est.raw_points[key].extend(np.linspace(0., 5., est.hist_len))
      est.raw_points['lat_active'].extend([True] * est.hist_len)
      est.raw_points['steer_override'].extend([False] * est.hist_len)
      est.raw_points['vego'].extend([20.] * est.hist_len)
      est.raw_points['steer_torque'].extend([count / 3840] * est.hist_len)
      event = messaging.new_message('deviceMotion').deviceMotion
      event.timestamp = 5_000_000_000
      event.inputsOK = event.sensorsOK = event.posenetOK = True
      for name in ('orientationNED', 'velocityDevice', 'accelerationDevice', 'angularVelocityDevice'):
        value = getattr(event, name)
        value.z = .01 if name == 'angularVelocityDevice' else 0.
        value.xStd = value.yStd = value.zStd = .01
        value.valid = True
      est.handle_log(5., 'deviceMotion', event)
      # 51.2 counts at 3840 = 0.02 x 2560 = STEER_MIN_THRESHOLD: 50 is below it, 52 above
      assert len(est.filtered_points) == int(abs(count) == 52)

  def test_fit_from_before_the_scaling_is_not_restored(self):
    # a cache written by the unscaled learner (version VERSION) must not come back on the Odyssey
    cp = odyssey()
    assert TorqueEstimator(cp).version == VERSION + 1
    params = Params()
    params.put("CarParamsPrevRoute", cp.to_bytes(), block=True)
    msg = messaging.new_message('lateralTorqueParameters')
    msg.lateralTorqueParameters.version = VERSION
    msg.lateralTorqueParameters.valid = True
    msg.lateralTorqueParameters.latAccelFactorFiltered = cp.lateralTuning.torque.latAccelFactor * 1.1
    msg.lateralTorqueParameters.frictionCoefficientFiltered = cp.lateralTuning.torque.friction * 1.1
    params.put("LiveTorqueParameters", msg.to_bytes(), block=True)
    est = TorqueEstimator(cp)
    assert est.filtered_params['latAccelFactor'].x == cp.lateralTuning.torque.latAccelFactor

  def test_other_cars_unchanged(self):
    cp = HondaInterface.get_params(CAR.HONDA_CIVIC, gen_empty_fingerprint(), [], False, False, False)
    est = TorqueEstimator(cp)
    assert est.torque_scale == 1.0 and est.version == VERSION
