"""RehkopfPilot onroad status pills: what each row says for a given state (pure logic, no window)."""
import pytest

from openpilot.selfdrive.ui.sunnypilot.mici.onroad.status_pills import pill_rows, PillInputs


def texts(p: PillInputs):
  return [[t for t, _ in row] for row in pill_rows(p)]


@pytest.mark.parametrize("p, want", [
  (PillInputs(op_long=False), [["STOCK ACC"]]),
  (PillInputs(op_long=True), [["OP LONG"]]),
  (PillInputs(op_long=True, experimental=True), [["OP LONG"], ["EXP"]]),
  (PillInputs(op_long=True, experimental=True, dec_enabled=True, dec_active=True), [["OP LONG"], ["DEC•ACC"]]),
  (PillInputs(op_long=True, experimental=True, dec_enabled=True, dec_active=True, dec_blended=True, dec_reason="stopAhead"),
   [["OP LONG"], ["STOP AHEAD", "DEC•EXP"]]),
  (PillInputs(op_long=True, experimental=True, dec_enabled=True, dec_active=True, dec_blended=True, dec_reason="curve"),
   [["OP LONG"], ["CURVE", "DEC•EXP"]]),
  (PillInputs(op_long=True, experimental=True, dec_enabled=True, dec_active=True, dec_blended=True, dec_reason="none"),
   [["OP LONG"], ["DEC•EXP"]]),
  (PillInputs(op_long=True, lead_dist=42.0, v_ego=20.0), [["2.1s", "OP LONG"]]),
  (PillInputs(op_long=True, lead_dist=5.0, v_ego=0.0), [["16ft", "OP LONG"]]),
  (PillInputs(op_long=True, lead_dist=5.0, v_ego=0.0, metric=True), [["5m", "OP LONG"]]),
  (PillInputs(op_long=True, lead_dist=42.0, v_ego=20.0, load_preset=1), [["FAMILY", "2.1s", "OP LONG"]]),
  (PillInputs(op_long=True, load_preset=2), [["LUGGAGE", "OP LONG"]]),
  (PillInputs(op_long=False, experimental=True, dec_enabled=True, dec_active=True), [["STOCK ACC"]]),
])
def test_pill_rows(p, want):
  assert texts(p) == want
