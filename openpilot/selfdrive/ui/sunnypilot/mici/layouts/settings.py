"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.common.params import Params
from openpilot.selfdrive.ui.mici.layouts.settings import settings as OP
from openpilot.selfdrive.ui.mici.layouts.settings.settings import SettingsBigButton
from openpilot.selfdrive.ui.mici.layouts.settings.network.network_layout import NetworkLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.device.device_layout import DeviceLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.developer import DeveloperLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.software import SoftwareLayoutMici
from openpilot.selfdrive.ui.mici.layouts.settings.firehose import FirehoseLayout
from openpilot.selfdrive.ui.mici.widgets.button import BigCircleButton
from openpilot.selfdrive.ui.mici.widgets.dialog import BigConfirmationDialog, BigDialog
from openpilot.selfdrive.ui.sunnypilot.mici.layouts.settings_groups import (DrivingGroup, PagesGroup, RecordingGroup, ScreenGroup,
                                                                             page_button)
from openpilot.selfdrive.ui.sunnypilot.mici.layouts.sunnylink import SunnylinkLayoutMici
from openpilot.selfdrive.ui.sunnypilot.mici.layouts.models import ModelsLayoutMici
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets.scroller import NavScroller

ICON_SIZE = 70
BIG_ICON_SIZE = 110
SP_ICONS = "../../sunnypilot/selfdrive/assets"


class SettingsLayoutSP(OP.SettingsLayout):
  """RehkopfPilot settings home: five groups by task instead of one page per code owner.
  driving / screen & alerts / privacy & recording / software / device & developer"""
  def __init__(self):
    # the stock pages are built once here and opened from inside the groups
    NavScroller.__init__(self)
    self._params = Params()
    self._font_medium = gui_app.font(FontWeight.MEDIUM)

    self._device_panel = DeviceLayoutMici()
    self._software_group = PagesGroup([
      page_button("updates &\nbranch", "icons_mici/settings/software.png", 64, 75, SoftwareLayoutMici()),
      page_button(tr("models"), f"{SP_ICONS}/offroad/icon_models.png", ICON_SIZE, ICON_SIZE, ModelsLayoutMici()),
      page_button(tr("sunnylink"), f"{SP_ICONS}/icons_mici/sunnylink.png", 76, 44, SunnylinkLayoutMici()),
    ])
    self._device_group = PagesGroup([
      page_button("device", "icons_mici/settings/device_icon.png", 72, 58, self._device_panel),
      page_button("network", "icons_mici/settings/network/wifi_strength_full.png", 76, 56, NetworkLayoutMici()),
      page_button("developer", "icons_mici/settings/developer_icon.png", 64, 60, DeveloperLayoutMici()),
      page_button("firehose", "icons_mici/settings/firehose.png", 52, 62, FirehoseLayout()),
    ])

    groups = [
      ("driving", "icons_mici/settings/device/lkas.png", 64, 64, DrivingGroup()),
      ("screen &\nalerts", "icons_mici/settings/device/info.png", 64, 64, ScreenGroup()),
      ("privacy &\nrecording", "icons_mici/settings/device/cameras.png", 64, 64, RecordingGroup()),
      ("software", "icons_mici/settings/software.png", 64, 75, self._software_group),
      ("device &\ndeveloper", "icons_mici/settings/device_icon.png", 72, 58, self._device_group),
    ]
    group_buttons = []
    for text, icon, w, h, page in groups:
      btn = SettingsBigButton(text, "", gui_app.texture(icon, w, h))
      btn.set_click_callback(lambda page=page: gui_app.push_widget(page))
      group_buttons.append(btn)
    self._device_button = group_buttons[-1]

    self.icon_offroad_enable = gui_app.texture(f"{SP_ICONS}/icons_mici/always_offroad.png", BIG_ICON_SIZE, BIG_ICON_SIZE)
    self.icon_offroad_disable = gui_app.texture(f"{SP_ICONS}/icons_mici/disable_offroad.png", BIG_ICON_SIZE, BIG_ICON_SIZE)
    self.icon_offroad_slider = gui_app.texture("icons_mici/settings/device/lkas.png", BIG_ICON_SIZE, BIG_ICON_SIZE)

    # onroad: enable-always-offroad sits at the front; offroad: at the end
    self._enable_offroad_btn_onroad = BigCircleButton(self.icon_offroad_enable, red=True)
    self._enable_offroad_btn_onroad.set_click_callback(lambda: self._handle_always_offroad(True))
    self._enable_offroad_btn_onroad.set_visible(lambda: ui_state.started and not ui_state.always_offroad)

    self._enable_offroad_btn_offroad = BigCircleButton(self.icon_offroad_enable, red=True)
    self._enable_offroad_btn_offroad.set_click_callback(lambda: self._handle_always_offroad(True))
    self._enable_offroad_btn_offroad.set_visible(lambda: not ui_state.started and not ui_state.always_offroad)

    self._disable_offroad_btn = BigCircleButton(self.icon_offroad_disable, red=False)
    self._disable_offroad_btn.set_click_callback(lambda: self._handle_always_offroad(False))
    self._disable_offroad_btn.set_visible(lambda: ui_state.always_offroad)

    self._scroller.add_widgets([self._disable_offroad_btn, self._enable_offroad_btn_onroad, *group_buttons,
                                self._enable_offroad_btn_offroad])

    if ui_state.params.get_bool("ShowDebugInfo"):
      gui_app.set_show_touches(True)
      gui_app.set_show_fps(True)

  def show_pairing(self):
    # settings, then device & developer, then the device page scrolled to pairing (no entrance animations behind it)
    gui_app.push_widget(self)
    self._y_pos_filter.x = 0.0
    self.set_shown_callback(self._scroll_to_device)
    gui_app.push_widget(self._device_group)
    gui_app.push_widget(self._device_panel)
    self._device_panel.set_shown_callback(self._device_panel.scroll_to_pairing)

  def _handle_always_offroad(self, enable: bool):

    def _set_offroad_status(status: bool):
      if not ui_state.engaged:
        ui_state.params.put_bool("OffroadMode", status)
        ui_state.always_offroad = status

    if not enable:
      dlg = BigConfirmationDialog(tr("slide to exit always offroad"), self.icon_offroad_slider, red=False,
                                  confirm_callback=lambda: _set_offroad_status(False))
    else:
      if ui_state.engaged:
        gui_app.push_widget(BigDialog(tr("disengage to enable always offroad"), "", ))
        return

      dlg = BigConfirmationDialog(tr("slide to force offroad"), self.icon_offroad_slider, red=True,
                                  confirm_callback=lambda: _set_offroad_status(True))
    gui_app.push_widget(dlg)
