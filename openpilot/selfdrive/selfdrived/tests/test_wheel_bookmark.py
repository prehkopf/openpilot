"""RehkopfPilot: double-tap CANCEL on the steering wheel saves a bookmark."""
from opendbc.car.structs import car
from openpilot.cereal import custom, log
from openpilot.selfdrive.selfdrived.events import EVENTS, ET
from openpilot.selfdrive.selfdrived.wheel_bookmark import DOUBLE_TAP_WINDOW, WheelBookmark, new_wheel_bookmark

ButtonType = car.CarState.ButtonEvent.Type
EventName = log.OnroadEvent.EventName


def be(typ, pressed):
  return car.CarState.ButtonEvent(type=typ, pressed=pressed)


def tap(wb, t, typ=ButtonType.cancel):
  fired = wb.update([be(typ, True)], t)
  wb.update([be(typ, False)], t + 0.1)
  return fired


def test_double_tap_counts_once():
  wb = WheelBookmark()
  assert not tap(wb, 10.0)
  assert tap(wb, 10.4)
  assert wb.count == 1


def test_slow_taps_do_not_count():
  wb = WheelBookmark()
  for i in range(4):
    assert not tap(wb, 10.0 + i * (DOUBLE_TAP_WINDOW + 0.3))
  assert wb.count == 0


def test_triple_tap_is_one_bookmark_then_a_fresh_start():
  wb = WheelBookmark()
  tap(wb, 1.0)
  tap(wb, 1.3)
  assert not tap(wb, 1.6)  # third tap starts a new double-tap
  assert tap(wb, 1.9)
  assert wb.count == 2


def test_other_buttons_and_releases_are_ignored():
  wb = WheelBookmark()
  for t, typ in ((1.0, ButtonType.accelCruise), (1.2, ButtonType.accelCruise), (1.4, ButtonType.decelCruise),
                 (1.5, ButtonType.decelCruise), (1.7, ButtonType.gapAdjustCruise), (1.8, ButtonType.gapAdjustCruise),
                 (2.0, ButtonType.lkas), (2.1, ButtonType.lkas)):
    tap(wb, t, typ)
  assert wb.update([be(ButtonType.cancel, False), be(ButtonType.cancel, False)], 3.0) is False
  assert wb.count == 0
  # a cancel then a +/- press inside the window is not a double-tap
  tap(wb, 5.0)
  tap(wb, 5.2, ButtonType.accelCruise)
  assert wb.count == 0


def test_ui_fires_on_new_count_only():
  assert new_wheel_bookmark(1, 0)
  assert new_wheel_bookmark(4, 3)
  assert not new_wheel_bookmark(3, 3)
  assert not new_wheel_bookmark(0, 3)  # selfdrived restarted for a new drive


def test_schema_and_chime():
  msg = custom.SelfdriveStateSP.new_message()
  msg.wheelBookmarkCount = 2
  assert msg.wheelBookmarkCount == 2
  chime = custom.SelfdriveStateSP.AudibleAlert.promptSingleHigh
  for name in (EventName.userBookmark, EventName.userBookmarkNotPaired):
    alert = EVENTS[name][ET.PERMANENT]
    assert alert.alert_text_1 == "Bookmark Saved"
    assert alert.audible_alert == chime
