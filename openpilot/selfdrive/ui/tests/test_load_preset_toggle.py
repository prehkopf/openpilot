from types import SimpleNamespace
import unittest

from openpilot.selfdrive.ui.sunnypilot.mici.widgets.load_preset import PRESETS, LoadPresetToggle, label_for


class FakeParams:
  def __init__(self, **values):
    self.values = dict(values)

  def put(self, key, value):
    self.values[key] = value


class TestLoadPresetToggle(unittest.TestCase):
  def test_label_for(self):
    self.assertEqual(label_for(0), "empty")
    self.assertEqual(label_for(1), "family")
    self.assertEqual(label_for(2), "family + luggage")
    for bad in (None, 3, -1, "x"):
      self.assertEqual(label_for(bad), "empty")

  def test_select_writes_preset(self):
    for label, preset in PRESETS.items():
      toggle = SimpleNamespace(_params=FakeParams(OdysseyLoadPreset=0))
      LoadPresetToggle._on_select(toggle, label)
      self.assertEqual(toggle._params.values, {"OdysseyLoadPreset": preset})

  def test_unknown_label_leaves_param(self):
    toggle = SimpleNamespace(_params=FakeParams(OdysseyLoadPreset=2))
    LoadPresetToggle._on_select(toggle, "custom")
    self.assertEqual(toggle._params.values, {"OdysseyLoadPreset": 2})

  def test_presets_match_car_controller(self):
    # the Honda car controller maps the same 0..2 range; out of range falls back to the empty van
    from opendbc.car.honda.carcontroller import ODYSSEY_LOAD_FACTORS
    self.assertEqual(sorted(PRESETS.values()), list(range(len(ODYSSEY_LOAD_FACTORS))))


if __name__ == "__main__":
  unittest.main()
