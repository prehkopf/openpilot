"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import pyray as rl

from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

GREEN = rl.Color(51, 196, 92, 255)
GREY = rl.Color(170, 170, 170, 255)
ORANGE = rl.Color(255, 145, 40, 255)
WHITE = rl.Color(255, 255, 255, 255)

FONT_SIZE = 22
PAD_X = 10
PILL_H = 28
MARGIN = 12
GAP = 6


def pill_states(op_long: bool, experimental: bool, dec_enabled: bool, dec_active: bool,
                dec_blended: bool) -> list[tuple[str, rl.Color]]:
  """What the two status pills say. Pure function so it can be tested without a UI."""
  pills = [("OP LONG", GREEN) if op_long else ("STOCK ACC", GREY)]
  if op_long and experimental:
    if dec_enabled and dec_active:
      pills.append(("DEC•EXP", ORANGE) if dec_blended else ("DEC•ACC", WHITE))  # "•" is in the loaded glyph set, "·" is not
    else:
      pills.append(("EXP", ORANGE))
  return pills


class StatusPills(Widget):
  """Tiny top-right pills: who controls gas/brake, and what experimental/DEC is doing right now."""

  def __init__(self):
    super().__init__()
    self._font = gui_app.font(FontWeight.SEMI_BOLD)
    self._alpha = FirstOrderFilter(0.0, 0.1, 1 / gui_app.target_fps)
    self._can_draw = True

  def set_can_draw(self, can_draw: bool) -> None:
    self._can_draw = can_draw

  def _current(self) -> list[tuple[str, rl.Color]]:
    sm = ui_state.sm
    CP = ui_state.CP
    op_long = bool(CP.openpilotLongitudinalControl) if CP is not None else ui_state.has_longitudinal_control
    experimental = sm.recv_frame['selfdriveState'] >= ui_state.started_frame and sm['selfdriveState'].experimentalMode
    dec_enabled = dec_active = dec_blended = False
    if sm.recv_frame['longitudinalPlanSP'] >= ui_state.started_frame:
      dec = sm['longitudinalPlanSP'].dec
      dec_enabled, dec_active = dec.enabled, dec.active
      dec_blended = dec.state.raw == 1  # DynamicExperimentalControlState.blended
    return pill_states(op_long, experimental, dec_enabled, dec_active, dec_blended)

  def _render(self, rect: rl.Rectangle) -> None:
    alpha = self._alpha.update(1.0 if (self._can_draw and ui_state.started) else 0.0)
    if alpha < 1e-2:
      return
    self.draw_pills(rect, self._current(), alpha)

  def draw_pills(self, rect: rl.Rectangle, pills: list[tuple[str, rl.Color]], alpha: float = 1.0) -> None:
    y = rect.y + MARGIN
    for text, color in pills:
      size = measure_text_cached(self._font, text, FONT_SIZE)
      w = size.x + 2 * PAD_X
      pill = rl.Rectangle(rect.x + rect.width - MARGIN - w, y, w, PILL_H)
      rl.draw_rectangle_rounded(pill, 1.0, 10, rl.Color(0, 0, 0, int(150 * alpha)))
      rl.draw_rectangle_rounded_lines_ex(pill, 1.0, 10, 2, rl.Color(color.r, color.g, color.b, int(200 * alpha)))
      text_pos = rl.Vector2(pill.x + PAD_X, pill.y + (PILL_H - size.y) / 2)
      rl.draw_text_ex(self._font, text, text_pos, FONT_SIZE, 0, rl.Color(color.r, color.g, color.b, int(255 * alpha)))
      y += PILL_H + GAP
