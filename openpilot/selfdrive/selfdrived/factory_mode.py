"""RehkopfPilot: factory mode, a stock Odyssey for other drivers. In Park, hold CANCEL for 3 s to switch.

Factory mode starts the drive passive (the same path as the "enable RehkopfPilot" toggle off): the panda stays in
no-output safety, so the harness relay hands the car back to the stock camera, and the radar is never silenced,
so stock ACC, LKAS and collision mitigation work. The switch only takes effect at the next start because the radar
is silenced once per ignition cycle and can't be woken cleanly mid-drive.

openpilotLongitudinalControl stays set in factory mode, so selfdrived and the UI don't clear ExperimentalMode or
DynamicExperimentalControl, and RehkopfPilot comes back with the same settings.
"""
from opendbc.car.structs import car

ButtonType = car.CarState.ButtonEvent.Type
GearShifter = car.CarState.GearShifter

HOLD_TIME = 3.0  # s of CANCEL held in Park
PARKED_SPEED = 0.1  # m/s


class FactoryModeSwitch:
  def __init__(self) -> None:
    self._press_t: float | None = None
    self._fired = False  # one switch per hold

  def update(self, button_events, gear_shifter, v_ego: float, t: float) -> bool:
    """t is a monotonic time in seconds. Returns True once when CANCEL has been held for HOLD_TIME in Park."""
    for be in button_events:
      if be.type != ButtonType.cancel:
        continue
      if be.pressed:
        self._press_t, self._fired = t, False
      else:
        self._press_t = None

    if gear_shifter != GearShifter.park or v_ego > PARKED_SPEED:
      self._press_t = None  # leaving Park mid-hold cancels it; the next press starts over
      return False

    if self._press_t is not None and not self._fired and t - self._press_t >= HOLD_TIME:
      self._fired = True
      return True
    return False


def factory_mode_enabled(params) -> bool:
  return params.get_bool("FactoryMode")


def toggle_factory_mode(params) -> bool:
  """Flips the mode for the next start. Returns the new value (True = factory mode next start)."""
  enabled = not factory_mode_enabled(params)
  params.put_bool("FactoryMode", enabled, block=True)  # written before the van can be turned off
  return enabled
