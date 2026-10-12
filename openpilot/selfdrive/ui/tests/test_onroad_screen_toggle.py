from types import SimpleNamespace
import unittest

from openpilot.selfdrive.ui.sunnypilot.mici.widgets.onroad_screen import (BRIGHTNESS_AUTO, BRIGHTNESS_SCREEN_OFF, CUSTOM, PRESETS,
                                                                          OnroadScreenToggle, preset_for)


class FakeParams:
  def __init__(self, **values):
    self.values = dict(values)

  def put(self, key, value):
    self.values[key] = value


class TestOnroadScreenToggle(unittest.TestCase):
  def test_preset_for(self):
    self.assertEqual(preset_for(BRIGHTNESS_AUTO, 15), "always on")
    self.assertEqual(preset_for(BRIGHTNESS_AUTO, 600), "always on")
    self.assertEqual(preset_for(BRIGHTNESS_SCREEN_OFF, 15), "off after 15s")
    self.assertEqual(preset_for(BRIGHTNESS_SCREEN_OFF, 180), "off after 3m")
    self.assertEqual(preset_for(BRIGHTNESS_SCREEN_OFF, 300), CUSTOM)  # e.g. 5m set from sunnylink
    self.assertEqual(preset_for(10, 15), CUSTOM)  # a fixed dim level

  def _select(self, label, **values):
    toggle = SimpleNamespace(_params=FakeParams(**values), _options=list(PRESETS) + [CUSTOM])
    OnroadScreenToggle._on_select(toggle, label)
    return toggle

  def test_select_writes_params(self):
    t = self._select("off after 15s", OnroadScreenOffBrightness=0, OnroadScreenOffTimer=600)
    self.assertEqual(t._params.values, {"OnroadScreenOffBrightness": BRIGHTNESS_SCREEN_OFF, "OnroadScreenOffTimer": 15})
    self.assertNotIn(CUSTOM, t._options)

    t = self._select("off after 3m")
    self.assertEqual(t._params.values, {"OnroadScreenOffBrightness": BRIGHTNESS_SCREEN_OFF, "OnroadScreenOffTimer": 180})

  def test_always_on_keeps_timer(self):
    t = self._select("always on", OnroadScreenOffBrightness=2, OnroadScreenOffTimer=180)
    self.assertEqual(t._params.values, {"OnroadScreenOffBrightness": BRIGHTNESS_AUTO, "OnroadScreenOffTimer": 180})

  def test_presets_use_allowed_timer_values(self):
    # the sunnylink picker and params migration only accept these
    from openpilot.sunnypilot.system.params_migration import VALID_TIMER_VALUES
    for _, timer in PRESETS.values():
      if timer is not None:
        self.assertIn(timer, VALID_TIMER_VALUES)


if __name__ == "__main__":
  unittest.main()
