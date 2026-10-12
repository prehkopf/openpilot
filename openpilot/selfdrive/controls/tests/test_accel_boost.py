from types import SimpleNamespace
import unittest

from openpilot.selfdrive.controls.lib.accel_boost import ACCEL_BOOST_MAX, ACCEL_BOOST_PER_OVERRIDE, AccelBoost


def _sm(enabled=True, gas=False, v_ego=25.0, experimental=True):
  return {
    'selfdriveState': SimpleNamespace(enabled=enabled, experimentalMode=experimental),
    'carState': SimpleNamespace(gasPressed=gas, vEgo=v_ego),
  }


# e2e wants 0.0 while mpc/cruise would allow 1.0: the model is limiting
E2E, MPC, CRUISE = 0.0, 1.0, 1.0


class TestAccelBoost(unittest.TestCase):
  def _press(self, boost, frames=200, **kw):
    for _ in range(frames):
      out = boost.update(_sm(gas=True, **kw), E2E, MPC, CRUISE, kw.get('experimental', True))
    boost.update(_sm(gas=False, **kw), E2E, MPC, CRUISE, kw.get('experimental', True))
    return out

  def test_each_override_adds_at_most_per_override(self):
    boost = AccelBoost()
    boost.update(_sm(), E2E, MPC, CRUISE, True)  # latch eligibility before the press
    self._press(boost)
    self.assertAlmostEqual(boost.total_boost, ACCEL_BOOST_PER_OVERRIDE)

  def test_capped_at_max(self):
    boost = AccelBoost()
    boost.update(_sm(), E2E, MPC, CRUISE, True)
    for _ in range(10):
      self._press(boost)
    self.assertAlmostEqual(boost.total_boost, ACCEL_BOOST_MAX)
    self.assertAlmostEqual(boost.update(_sm(), E2E, MPC, CRUISE, True), E2E + ACCEL_BOOST_MAX)

  def test_resets_on_disengage(self):
    boost = AccelBoost()
    boost.update(_sm(), E2E, MPC, CRUISE, True)
    self._press(boost)
    boost.update(_sm(enabled=False), E2E, MPC, CRUISE, True)
    self.assertEqual(boost.total_boost, 0.0)

  def test_no_buildup_when_dec_is_in_acc_mode(self):
    # Experimental Mode on, but DEC picked ACC so the e2e plan is not a candidate
    boost = AccelBoost()
    boost.update(_sm(), E2E, MPC, CRUISE, False)
    for _ in range(5):
      for _ in range(200):
        boost.update(_sm(gas=True), E2E, MPC, CRUISE, False)
      boost.update(_sm(), E2E, MPC, CRUISE, False)
    self.assertEqual(boost.total_boost, 0.0)

  def test_defaults_to_experimental_mode(self):
    boost = AccelBoost()
    boost.update(_sm(experimental=False), E2E, MPC, CRUISE)
    for _ in range(200):
      boost.update(_sm(gas=True, experimental=False), E2E, MPC, CRUISE)
    self.assertEqual(boost.total_boost, 0.0)

  def test_no_boost_below_min_speed(self):
    boost = AccelBoost()
    boost.update(_sm(v_ego=3.0), E2E, MPC, CRUISE, True)
    for _ in range(200):
      boost.update(_sm(gas=True, v_ego=3.0), E2E, MPC, CRUISE, True)
    self.assertEqual(boost.total_boost, 0.0)


if __name__ == "__main__":
  unittest.main()
