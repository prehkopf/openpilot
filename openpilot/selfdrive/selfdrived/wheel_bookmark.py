"""RehkopfPilot: double-tap CANCEL on the steering wheel to bookmark the drive.

msgq allows one publisher per service and the UI owns userBookmark, so selfdrived only counts double-taps
(selfdriveStateSP.wheelBookmarkCount) and the UI publishes the bookmark, the same way as the onroad swipe.
CANCEL is used because a single tap only ends openpilot longitudinal (steering stays on with MADS), and it is
pressed rarely in normal driving, unlike +/- (double-tapped to change speed) or distance (cycles personality).
"""
from opendbc.car.structs import car

ButtonType = car.CarState.ButtonEvent.Type

DOUBLE_TAP_WINDOW = 0.7  # s allowed between the two presses


class WheelBookmark:
  def __init__(self) -> None:
    self.count = 0
    self._last_press: float | None = None

  def update(self, button_events, t: float) -> bool:
    """t is a monotonic time in seconds. Returns True on the second press of a double-tap."""
    tapped = False
    for be in button_events:
      if be.type != ButtonType.cancel or not be.pressed:
        continue
      if self._last_press is not None and t - self._last_press <= DOUBLE_TAP_WINDOW:
        self.count += 1
        self._last_press = None  # a third quick tap starts a new double-tap
        tapped = True
      else:
        self._last_press = t
    return tapped


def new_wheel_bookmark(count: int, prev: int) -> bool:
  """UI side: a changed, non-zero count is a new bookmark. selfdrived restarts each drive, so the count drops to 0."""
  return count != prev and count != 0
