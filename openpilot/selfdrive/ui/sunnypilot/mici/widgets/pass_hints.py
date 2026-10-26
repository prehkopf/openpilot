"""RehkopfPilot pass hints setting (PassHints): off, learning (logged, never shown), pill, pill + chime."""
from openpilot.common.params import Params
from openpilot.selfdrive.ui.mici.widgets.button import BigMultiToggle

MODES = {"off": 0, "learning": 1, "pill": 2, "pill + chime": 3}


def label_for(value) -> str:
  try:
    value = int(value)
  except (TypeError, ValueError):
    value = 1
  return next((label for label, v in MODES.items() if v == value), "learning")


class PassHintsToggle(BigMultiToggle):
  def __init__(self):
    super().__init__("pass hints", list(MODES), select_callback=self._on_select,
                     description="A blue PASS pill when a slower car has held you back on a divided road\n" +
                                 "and the line beside you is dashed white. Advice only: it can't see\n" +
                                 "beside or behind you, so check your mirrors.\n" +
                                 "learning: worked out and logged, never shown (for checking first).\n" +
                                 "pill + chime: also a soft chime.")
    self._params = Params()
    self.refresh()

  def refresh(self):
    self.set_value(label_for(self._params.get("PassHints", return_default=True)))

  def _on_select(self, label: str):
    if label in MODES:
      self._params.put("PassHints", MODES[label])
