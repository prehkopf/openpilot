"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import math
import time

import pyray as rl

from openpilot.selfdrive.ui.mici.layouts.home import MiciHomeLayout
from openpilot.selfdrive.ui.ui_state import ui_state, ChestnutState
from openpilot.system.ui.lib.application import FontWeight
from openpilot.system.ui.widgets.label import UnifiedLabel
from openpilot.selfdrive.selfdrived.factory_mode import factory_mode_enabled


def home_title(factory_mode: bool) -> str:
  return "Factory" if factory_mode else "RehkopfPilot"


class MiciHomeLayoutSP(MiciHomeLayout):
  def __init__(self):
    super().__init__()
    self._openpilot_label = UnifiedLabel("RehkopfPilot", font_size=70, font_weight=FontWeight.AUDIOWIDE, max_width=480, wrap_text=False)
    self._factory_check_t = 0.0

  def _update_state(self):
    super()._update_state()
    # factory mode for the next start (hold CANCEL in Park) replaces the title, so the next driver sees it
    if time.monotonic() - self._factory_check_t > 1.0:
      self._factory_check_t = time.monotonic()
      self._openpilot_label.set_text(home_title(factory_mode_enabled(ui_state.params)))

  def _set_chestnut_visibility(self):
    usb_connected = ui_state.usb_connected
    usb_unknown = ui_state.usb_unknown
    chestnut_state = ui_state.chestnut_state
    loading = chestnut_state == ChestnutState.LOADING

    self._usb_icon.set_visible(usb_connected and usb_unknown)
    self._chestnut_loading_icon.set_opacity(0.35 + 0.65 * (0.5 - 0.5 * math.cos(rl.get_time() * 6.0)))
    self._chestnut_loading_icon.set_visible(not usb_unknown and loading)
    self._chestnut_icon.set_visible(not usb_unknown and not loading and
                                    chestnut_state in (ChestnutState.READY, ChestnutState.ACTIVE))
    self._chestnut_failed_icon.set_visible(not usb_unknown and chestnut_state in (ChestnutState.UNCOMPILED, ChestnutState.FAILED))
