"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params
from openpilot.selfdrive.ui.mici.widgets.button import BigMultiToggle
from openpilot.sunnypilot.selfdrive.controls.lib.auto_lane_change import AutoLaneChangeMode

# label -> AutoLaneChangeTimer, in the order the big-screen sunnypilot setting steps through them
MODES = {
  "off": AutoLaneChangeMode.OFF,
  "nudge": AutoLaneChangeMode.NUDGE,
  "nudgeless": AutoLaneChangeMode.NUDGELESS,
  "0.5 s": AutoLaneChangeMode.HALF_SECOND,
  "1 s": AutoLaneChangeMode.ONE_SECOND,
  "2 s": AutoLaneChangeMode.TWO_SECONDS,
  "3 s": AutoLaneChangeMode.THREE_SECONDS,
}


def label_for(value) -> str:
  try:
    value = int(value)
  except (TypeError, ValueError):
    value = AutoLaneChangeMode.NUDGE
  return next((label for label, v in MODES.items() if v == value), "nudge")


class LaneChangeModeToggle(BigMultiToggle):
  """comma four picker for sunnypilot's auto lane change (AutoLaneChangeTimer); before this it was sunnylink-only."""
  def __init__(self):
    super().__init__("lane change", list(MODES), select_callback=self._on_select,
                     description="What the blinker does above lane-change speed.\n" +
                                 "nudge: blinker, then nudge the wheel (default).\n" +
                                 "nudgeless: change as soon as the blinker is on.\n" +
                                 "0.5-3 s: change after the blinker has been on that long.\n" +
                                 "off: no lane changes.")
    self._params = Params()
    self.refresh()

  def refresh(self):
    self.set_value(label_for(self._params.get("AutoLaneChangeTimer", return_default=True)))

  def _on_select(self, label: str):
    if label in MODES:
      self._params.put("AutoLaneChangeTimer", MODES[label])
