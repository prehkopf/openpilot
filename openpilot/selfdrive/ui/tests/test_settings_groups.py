"""RehkopfPilot comma four settings: five task groups, nothing lost, nothing duplicated (no window needed)."""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from openpilot.selfdrive.ui.sunnypilot.mici.layouts.settings_groups import DefaultParamControl
from openpilot.selfdrive.ui.sunnypilot.mici.widgets.lane_change_mode import MODES, LaneChangeModeToggle, label_for
from openpilot.sunnypilot.selfdrive.controls.lib.auto_lane_change import AUTO_LANE_CHANGE_TIMER, AutoLaneChangeMode

UI = Path(__file__).resolve().parents[1]
GROUPS = (UI / "sunnypilot/mici/layouts/settings_groups.py").read_text()
HOME = (UI / "sunnypilot/mici/layouts/settings.py").read_text()
DEVICE = (UI / "mici/layouts/settings/device/device_layout.py").read_text()
STOCK_TOGGLES = (UI / "mici/layouts/settings/toggles.py").read_text()

# stock toggles deliberately left off the comma four menu (the param keeps its default)
REMOVED_ON_PURPOSE = {
  "IsMetric": "Patrick drives in mph; the button was clutter (2026-10-18)",
}

PARAM_CONTROL = re.compile(r'Big(?:Multi)?Param(?:Control|Toggle)\(\s*"[^"]*",\s*"(\w+)"')


class FakeParams:
  def __init__(self, **values):
    self.values = dict(values)

  def put(self, key, value):
    self.values[key] = value

  def get(self, key, return_default=False):
    return self.values.get(key, {"Mads": True, "AutoLaneChangeTimer": 0}.get(key) if return_default else None)


def test_every_stock_toggle_lives_in_exactly_one_group():
  # if upstream adds a toggle to the stock page, this fails until it is placed in a group
  stock = set(PARAM_CONTROL.findall(STOCK_TOGGLES))
  grouped = PARAM_CONTROL.findall(GROUPS)
  assert stock, "stock toggle page parse found nothing"
  assert set(REMOVED_ON_PURPOSE) <= stock, "a removed toggle is gone from the stock page; drop it from REMOVED_ON_PURPOSE"
  for key in stock - set(REMOVED_ON_PURPOSE):
    assert grouped.count(key) == 1, f"{key}: in {grouped.count(key)} groups"
  for key in REMOVED_ON_PURPOSE:
    assert key not in grouped, key


def test_home_order_is_most_used_first():
  order = [HOME.index(f'("{label}"') for label in ("driving", "software", "screen\\n& alerts", "privacy", "system")]
  assert order == sorted(order)


def test_driving_order_is_most_used_first():
  order = ("[self._load, self._destination, self._personality, self._dec, self._lane_change, self._pass_hints, self._experimental, " +
           "self._mads, self._enable]")
  assert order in " ".join(GROUPS.split()).replace("[ ", "[")


def test_moved_pickers_are_in_groups_not_on_device_page():
  for widget in ("OnroadScreenToggle()", "LoadPresetToggle()", "LaneChangeModeToggle()", "PassHintsToggle()"):
    assert GROUPS.count(widget) == 1, widget
    assert widget not in DEVICE, widget


@pytest.mark.parametrize("page", ["SoftwareLayoutMici()", "ModelsLayoutMici()", "SunnylinkLayoutMici()", "NetworkLayoutMici()",
                                  "DeveloperLayoutMici()", "FirehoseLayout()", "DeviceLayoutMici()"])
def test_each_stock_page_built_once(page):
  # built once, opened from inside a group; double construction would start duplicate network/pairing state
  assert HOME.count(page) == 1, page


def test_home_has_five_groups():
  for label in ("driving", "screen\\n& alerts", "privacy", "software", "system"):
    assert f'"{label}"' in HOME, label


def test_lane_change_modes_cover_sunnypilot_range():
  assert sorted(MODES.values()) == sorted(AUTO_LANE_CHANGE_TIMER)
  assert label_for(AutoLaneChangeMode.NUDGE) == "nudge"
  for bad in (None, 9, "x"):
    assert label_for(bad) == "nudge"


def test_lane_change_select_and_refresh_round_trip():
  for label, value in MODES.items():
    toggle = SimpleNamespace(_params=FakeParams(AutoLaneChangeTimer=0), set_value=lambda v: None)
    LaneChangeModeToggle._on_select(toggle, label)
    assert toggle._params.values == {"AutoLaneChangeTimer": value}
    shown = []
    toggle.set_value = shown.append
    LaneChangeModeToggle.refresh(toggle)
    assert shown == [label]


def test_mads_shows_its_default_when_never_set():
  shown = []
  ctl = SimpleNamespace(params=FakeParams(), param="Mads", set_checked=shown.append)
  DefaultParamControl.refresh(ctl)
  assert shown == [True]
  ctl.params = FakeParams(Mads=False)
  DefaultParamControl.refresh(ctl)
  assert shown == [True, False]
