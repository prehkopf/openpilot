"""RehkopfPilot factory mode: hold CANCEL for 3 s in Park to switch the next start to a stock car and back."""
import os
import wave

import pytest

from opendbc.car.structs import car
from openpilot.cereal import custom
from openpilot.common.basedir import BASEDIR
from openpilot.selfdrive.selfdrived.factory_mode import HOLD_TIME, FactoryModeSwitch, factory_mode_enabled, toggle_factory_mode
from openpilot.selfdrive.ui.soundd import SAMPLE_RATE, sound_list
from openpilot.sunnypilot.selfdrive.selfdrived.events import EVENTS_SP, ET

ButtonType = car.CarState.ButtonEvent.Type
GearShifter = car.CarState.GearShifter
EventNameSP = custom.OnroadEventSP.EventName
AudibleAlertSP = custom.SelfdriveStateSP.AudibleAlert


def be(typ, pressed):
  return car.CarState.ButtonEvent(type=typ, pressed=pressed)


def hold(sw, t0, duration, typ=ButtonType.cancel, gear=GearShifter.park, v_ego=0.0, dt=0.01):
  """Press at t0, hold for duration, release. Returns the times update() returned True."""
  fired = []
  t = t0
  if sw.update([be(typ, True)], gear, v_ego, t):
    fired.append(t)
  while t < t0 + duration:
    t = round(t + dt, 6)
    if sw.update([], gear, v_ego, t):
      fired.append(t)
  sw.update([be(typ, False)], gear, v_ego, t)
  return fired


def test_three_second_hold_in_park_fires_once():
  sw = FactoryModeSwitch()
  fired = hold(sw, 10.0, 6.0)
  assert len(fired) == 1
  assert fired[0] == pytest.approx(10.0 + HOLD_TIME, abs=0.02)


def test_short_hold_and_taps_do_nothing():
  sw = FactoryModeSwitch()
  assert hold(sw, 1.0, HOLD_TIME - 0.2) == []
  for i in range(10):  # double-tap bookmarks and stray taps
    assert hold(sw, 10.0 + i * 0.3, 0.1) == []


def test_needs_park_and_standstill():
  for gear, v_ego in ((GearShifter.drive, 0.0), (GearShifter.reverse, 0.0), (GearShifter.neutral, 0.0),
                      (GearShifter.park, 1.0)):
    assert hold(FactoryModeSwitch(), 1.0, 5.0, gear=gear, v_ego=v_ego) == []


def test_leaving_park_mid_hold_cancels_it():
  sw = FactoryModeSwitch()
  sw.update([be(ButtonType.cancel, True)], GearShifter.park, 0.0, 1.0)
  sw.update([], GearShifter.drive, 0.0, 2.0)
  assert not sw.update([], GearShifter.park, 0.0, 4.5)  # back in Park, still holding: must press again
  assert hold(sw, 5.0, 4.0) != []


def test_other_buttons_ignored():
  for typ in (ButtonType.accelCruise, ButtonType.decelCruise, ButtonType.gapAdjustCruise, ButtonType.lkas, ButtonType.mainCruise):
    assert hold(FactoryModeSwitch(), 1.0, 5.0, typ=typ) == []


def test_each_hold_switches_again():
  sw = FactoryModeSwitch()
  assert len(hold(sw, 1.0, 4.0)) == 1
  assert len(hold(sw, 10.0, 4.0)) == 1


class FakeParams:
  def __init__(self):
    self.store = {}

  def get_bool(self, key):
    return self.store.get(key, False)

  def put_bool(self, key, val, block=False):
    assert block, "must be written before the van is turned off"
    self.store[key] = val


def test_toggle_round_trip_keeps_long_settings():
  p = FakeParams()
  p.store.update({"ExperimentalMode": True, "DynamicExperimentalControl": True, "AlphaLongitudinalEnabled": True})
  assert toggle_factory_mode(p) is True and factory_mode_enabled(p)
  assert toggle_factory_mode(p) is False and not factory_mode_enabled(p)
  assert p.store["ExperimentalMode"] and p.store["DynamicExperimentalControl"] and p.store["AlphaLongitudinalEnabled"]


def test_alerts_and_voice_clips():
  on = EVENTS_SP[EventNameSP.factoryModeOn][ET.PERMANENT]
  off = EVENTS_SP[EventNameSP.factoryModeOff][ET.PERMANENT]
  active = EVENTS_SP[EventNameSP.factoryModeActive][ET.PERMANENT]
  assert on.alert_text_1 == "Factory Mode" and on.audible_alert == AudibleAlertSP.factoryModeOn
  assert off.alert_text_1 == "RehkopfPilot Back On" and off.audible_alert == AudibleAlertSP.factoryModeOff
  assert "next time" in on.alert_text_2 and "next time" in off.alert_text_2
  assert active.alert_text_1 == "Factory Mode"


@pytest.mark.parametrize("alert", [AudibleAlertSP.factoryModeOn, AudibleAlertSP.factoryModeOff])
def test_voice_clip_format(alert):
  filename, play_count, _ = sound_list[alert]
  path = os.path.join(BASEDIR, "openpilot/selfdrive/assets/sounds", filename)
  with open(path, "rb") as f:
    assert not f.read(64).startswith(b"version https://git-lfs"), f"{filename} is an LFS pointer: exempt it in .gitattributes"
  with wave.open(path) as w:  # soundd asserts this format and crashes on anything else
    assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, SAMPLE_RATE)
    assert 0.5 < w.getnframes() / SAMPLE_RATE < 4.0
  assert play_count == 1
