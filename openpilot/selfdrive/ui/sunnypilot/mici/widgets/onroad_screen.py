"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params
from openpilot.selfdrive.ui.mici.widgets.button import BigMultiToggle

# OnroadScreenOffBrightness values, see sunnypilot/layouts/settings/display.py OnroadBrightness
BRIGHTNESS_AUTO = 0
BRIGHTNESS_SCREEN_OFF = 2

# label -> (OnroadScreenOffBrightness, OnroadScreenOffTimer seconds or None to leave as is)
PRESETS = {
  "always on": (BRIGHTNESS_AUTO, None),
  "off after 15s": (BRIGHTNESS_SCREEN_OFF, 15),
  "off after 3m": (BRIGHTNESS_SCREEN_OFF, 180),
}
CUSTOM = "custom"


def preset_for(brightness: int, timer: int) -> str:
  if brightness == BRIGHTNESS_AUTO:
    return "always on"
  for label, (b, t) in PRESETS.items():
    if b == brightness and t == timer:
      return label
  return CUSTOM


class OnroadScreenToggle(BigMultiToggle):
  """comma four picker for sunnypilot's onroad screen-off settings; a tap or an alert wakes the screen."""
  def __init__(self):
    params = Params()
    current = preset_for(int(float(params.get("OnroadScreenOffBrightness", return_default=True))),
                         int(params.get("OnroadScreenOffTimer", return_default=True)))
    # keep a value set from sunnylink visible until the user cycles away from it
    options = list(PRESETS) + ([CUSTOM] if current == CUSTOM else [])
    super().__init__("onroad screen", options, select_callback=self._on_select,
                     description="Turn the screen off while driving. A tap or any alert wakes it.")
    self._params = params
    self.set_value(current)

  def _on_select(self, label: str):
    if label not in PRESETS:
      return
    if CUSTOM in self._options:
      self._options.remove(CUSTOM)
    brightness, timer = PRESETS[label]
    if timer is not None:
      self._params.put("OnroadScreenOffTimer", timer)
    self._params.put("OnroadScreenOffBrightness", brightness)
