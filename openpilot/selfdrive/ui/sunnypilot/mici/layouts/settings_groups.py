"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.cereal import log
from openpilot.selfdrive.ui.layouts.settings.common import restart_needed_callback
from openpilot.selfdrive.ui.mici.widgets.button import BigButton, BigMultiParamToggle, BigParamControl
from openpilot.selfdrive.ui.sunnypilot.mici.widgets.lane_change_mode import LaneChangeModeToggle
from openpilot.selfdrive.ui.sunnypilot.mici.widgets.load_preset import LoadPresetToggle
from openpilot.selfdrive.ui.sunnypilot.mici.widgets.onroad_screen import OnroadScreenToggle
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.widgets.scroller import NavScroller

PERSONALITY_TO_INT = log.LongitudinalPersonality.schema.enumerants


class GroupLayout(NavScroller):
  """One settings group: re-reads every param-backed control when shown, so changes made elsewhere
  (sunnylink, the settings profile, the steering-wheel distance button) show up."""
  def __init__(self, widgets):
    super().__init__()
    self._scroller.add_widgets(widgets)

  def show_event(self):
    super().show_event()
    self._refresh()

  def _refresh(self):
    ui_state.update_params()
    for item in self._scroller.items:
      if hasattr(item, "refresh"):
        item.refresh()
      elif hasattr(item, "_load_value"):
        item._load_value()


class DefaultParamControl(BigParamControl):
  """A param toggle that shows the key's default when it has never been set (BigParamControl shows off)."""
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.refresh()

  def refresh(self):
    self.set_checked(bool(self.params.get(self.param, return_default=True)))


def page_button(text: str, icon: str, w: int, h: int, page) -> BigButton:
  btn = BigButton(text, "", gui_app.texture(icon, w, h))
  btn.set_click_callback(lambda: gui_app.push_widget(page))
  return btn


class DrivingGroup(GroupLayout):
  """Everything that changes how the car drives."""
  def __init__(self):
    self._personality = BigMultiParamToggle("driving personality", "LongitudinalPersonality", ["aggressive", "standard", "relaxed"],
                                            description="Standard is recommended.\n" +
                                                        "Aggressive follows closer, with firmer gas and braking.\n" +
                                                        "Relaxed leaves more space.\n" +
                                                        "The steering wheel distance button changes it too.")
    self._experimental = BigParamControl("experimental mode", "ExperimentalMode",
                                         description_icon=gui_app.texture("icons_mici/experimental_mode.png", 64, 64),
                                         description="Let the driving model control gas and brakes.\n" +
                                                     "Includes stopping for red lights and stop signs.\n" +
                                                     "Set speed is a maximum, not a target.\n" +
                                                     "The path colors show acceleration and braking.")
    self._dec = BigParamControl("dynamic experimental", "DynamicExperimentalControl",
                                description="Only with experimental mode on.\n" +
                                            "Normal ACC following by default; the model takes over\n" +
                                            "for stops, lights and curves. The DEC pill shows why.")
    self._load = LoadPresetToggle()
    self._mads = DefaultParamControl("MADS steering", "Mads",
                                 description="Steering stays on when cruise is off or you brake,\n" +
                                             "and the LKAS button turns steering on by itself.\n" +
                                             "Change it with the car off.")
    self._lane_change = LaneChangeModeToggle()
    self._enable = BigParamControl("enable RehkopfPilot", "OpenpilotEnabledToggle", toggle_callback=restart_needed_callback,
                                   description="Enable to use RehkopfPilot driver assistance.\n" +
                                               "Disable to use your car's stock driver assistance.")
    # most-changed first: load changes with every trip, MADS and enable only with the car off
    super().__init__([self._load, self._personality, self._dec, self._lane_change, self._experimental, self._mads, self._enable])

    self._mads.set_enabled(lambda: not ui_state.started)
    self._enable.set_enabled(lambda: not ui_state.engaged)
    ui_state.add_engaged_transition_callback(self._refresh)

  def _update_state(self):
    super()._update_state()
    # keep the personality pill in step with the steering wheel distance button
    if ui_state.sm.updated["selfdriveState"]:
      personality = PERSONALITY_TO_INT[ui_state.sm["selfdriveState"].personality]
      if personality != ui_state.personality and ui_state.started:
        self._personality.set_value(self._personality._options[personality])
      ui_state.personality = personality

  def _refresh(self):
    super()._refresh()
    if ui_state.CP is not None:
      has_long = ui_state.has_longitudinal_control
      for item in (self._experimental, self._dec, self._personality):
        item.set_visible(has_long)
      if not has_long:
        for item, key in ((self._experimental, "ExperimentalMode"), (self._dec, "DynamicExperimentalControl")):
          item.set_checked(False)
          ui_state.params.remove(key)


class ScreenGroup(GroupLayout):
  """What the screen shows and when it warns. (No metric toggle: IsMetric stays at its default, mph.)"""
  def __init__(self):
    super().__init__([
      OnroadScreenToggle(),
      BigParamControl("lane departure warnings", "IsLdwEnabled",
                      description="Warn when you drift across a detected lane line.\n" +
                                  "Only above 31 mph (50 km/h), with no turn signal."),
    ])


class RecordingGroup(GroupLayout):
  """What gets recorded and uploaded."""
  def __init__(self):
    record_front = BigParamControl("record & upload cabin camera", "RecordFront",
                                   description_icon=gui_app.texture("icons_mici/settings/device/cameras.png", 64, 64),
                                   toggle_callback=restart_needed_callback,
                                   description="Records the driver camera. Needed to save moments in the cabin.")
    record_mic = BigParamControl("record & upload mic audio", "RecordAudio",
                                 description_icon=gui_app.texture("icons_mici/microphone.png", 64, 64),
                                 toggle_callback=restart_needed_callback,
                                 description="Record microphone audio while driving.\n" +
                                             "Audio is included in dashcam videos in sunnylink.")
    always_on_dm = BigParamControl("always-on driver monitor", "AlwaysOnDM",
                                   description="Monitor the driver even when RehkopfPilot is not engaged.")
    super().__init__([record_front, record_mic, always_on_dm])
    record_front.set_enabled(False if ui_state.params.get_bool("RecordFrontLock") else (lambda: not ui_state.engaged))
    record_mic.set_enabled(lambda: not ui_state.engaged)


class PagesGroup(GroupLayout):
  """A group whose entries open existing full pages (software, device, developer, ...)."""
  def __init__(self, buttons):
    super().__init__(buttons)
