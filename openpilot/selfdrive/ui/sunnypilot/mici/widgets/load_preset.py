"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params
from openpilot.selfdrive.ui.mici.widgets.button import BigMultiToggle

# label -> OdysseyLoadPreset; the Honda car controller maps each preset to a gas scale (ODYSSEY_LOAD_FACTORS)
PRESETS = {
  "empty": 0,
  "family": 1,
  "family + luggage": 2,
}


def label_for(preset) -> str:
  try:
    value = int(preset)
  except (TypeError, ValueError):
    value = 0
  return next((label for label, v in PRESETS.items() if v == value), "empty")


class LoadPresetToggle(BigMultiToggle):
  """comma four picker for how heavily the Odyssey is loaded; more load adds gas within the safety limit."""
  def __init__(self):
    params = Params()
    super().__init__("van load", list(PRESETS), select_callback=self._on_select,
                     description="Odyssey only. Adds gas for a heavier van, applied within a few seconds.")
    self._params = params
    self.set_value(label_for(params.get("OdysseyLoadPreset", return_default=True)))

  def _on_select(self, label: str):
    if label in PRESETS:
      self._params.put("OdysseyLoadPreset", PRESETS[label])
