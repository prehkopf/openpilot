"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from dataclasses import dataclass

import pyray as rl

from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

GREEN = rl.Color(51, 196, 92, 255)
GREY = rl.Color(170, 170, 170, 255)
ORANGE = rl.Color(255, 145, 40, 255)
RED = rl.Color(255, 70, 60, 255)
WHITE = rl.Color(255, 255, 255, 255)
BLUE = rl.Color(110, 170, 255, 255)

FONT_SIZE = 22
PAD_X = 10
PILL_H = 28
MARGIN = 12
GAP = 6

# DEC's reason for blended mode (custom.capnp DynamicExperimentalControl.DecReason) -> pill
REASONS = {
  "stopAhead": ("STOP AHEAD", ORANGE),
  "slowing": ("SLOWING", ORANGE),
  "curve": ("CURVE", ORANGE),
  "stopped": ("STOPPED", WHITE),
  "collision": ("COLLISION", RED),
}
LOAD_PRESETS = {1: "FAMILY", 2: "LUGGAGE"}  # OdysseyLoadPreset (ody-test); Empty shows nothing
M_TO_FT = 3.28084


@dataclass
class PillInputs:
  op_long: bool
  experimental: bool = False
  dec_enabled: bool = False
  dec_active: bool = False
  dec_blended: bool = False
  dec_reason: str = "none"
  lead_dist: float | None = None  # m, None without a lead
  v_ego: float = 0.0              # m/s
  metric: bool = False
  load_preset: int = 0
  factory: bool = False  # passive drive (factory mode or RehkopfPilot toggled off): the car is stock


def pill_rows(p: PillInputs) -> list[list[tuple[str, rl.Color]]]:
  """Pills as rows, each row read left to right and drawn right-aligned. Pure, so it's testable without a UI."""
  if p.factory:
    return [[("FACTORY", WHITE)]]
  row1: list[tuple[str, rl.Color]] = []
  if p.load_preset in LOAD_PRESETS:
    row1.append((LOAD_PRESETS[p.load_preset], BLUE))
  if p.lead_dist is not None:
    if p.v_ego > 1.0:
      row1.append((f"{p.lead_dist / p.v_ego:.1f}s", WHITE))  # following gap in seconds
    else:
      row1.append((f"{p.lead_dist:.0f}m" if p.metric else f"{p.lead_dist * M_TO_FT:.0f}ft", WHITE))
  row1.append(("OP LONG", GREEN) if p.op_long else ("STOCK ACC", GREY))
  rows = [row1]
  if p.op_long and p.experimental:
    if p.dec_enabled and p.dec_active:
      row2 = [("DEC•EXP", ORANGE) if p.dec_blended else ("DEC•ACC", WHITE)]  # "•" is in the loaded glyph set, "·" is not
      if p.dec_blended and p.dec_reason in REASONS:
        row2.insert(0, REASONS[p.dec_reason])
    else:
      row2 = [("EXP", ORANGE)]
    rows.append(row2)
  return rows


class StatusPills(Widget):
  """Tiny top-right pills: load preset, gap to the lead, who controls gas/brake, and what experimental/DEC is doing."""

  def __init__(self):
    super().__init__()
    self._font = gui_app.font(FontWeight.SEMI_BOLD)
    self._alpha = FirstOrderFilter(0.0, 0.1, 1 / gui_app.target_fps)
    self._can_draw = True
    self._load_preset = 0
    self._frame = 0

  def set_can_draw(self, can_draw: bool) -> None:
    self._can_draw = can_draw

  def _read_load_preset(self) -> None:
    if self._frame % gui_app.target_fps == 0:  # params at 1 Hz
      try:
        self._load_preset = int(ui_state.params.get("OdysseyLoadPreset", return_default=True) or 0)
      except Exception:  # the key only exists on builds with van-load presets
        self._load_preset = 0
    self._frame += 1

  def _current(self) -> list[list[tuple[str, rl.Color]]]:
    sm = ui_state.sm
    CP = ui_state.CP
    self._read_load_preset()
    p = PillInputs(op_long=bool(CP.openpilotLongitudinalControl) if CP is not None else ui_state.has_longitudinal_control,
                   metric=ui_state.is_metric, load_preset=self._load_preset,
                   factory=bool(CP.passive) if CP is not None else False)
    if sm.recv_frame['selfdriveState'] >= ui_state.started_frame:
      p.experimental = sm['selfdriveState'].experimentalMode
    if sm.recv_frame['longitudinalPlanSP'] >= ui_state.started_frame:
      dec = sm['longitudinalPlanSP'].dec
      p.dec_enabled, p.dec_active, p.dec_blended = dec.enabled, dec.active, dec.state.raw == 1  # 1 = blended
      p.dec_reason = str(dec.reason)
    if sm.recv_frame['radarState'] >= ui_state.started_frame and sm['radarState'].leadOne.present:
      p.lead_dist = sm['radarState'].leadOne.dRel
    if sm.recv_frame['carState'] >= ui_state.started_frame:
      p.v_ego = sm['carState'].vEgo
    return pill_rows(p)

  def _render(self, rect: rl.Rectangle) -> None:
    alpha = self._alpha.update(1.0 if (self._can_draw and ui_state.started) else 0.0)
    if alpha < 1e-2:
      return
    self.draw_rows(rect, self._current(), alpha)

  def draw_rows(self, rect: rl.Rectangle, rows: list[list[tuple[str, rl.Color]]], alpha: float = 1.0) -> None:
    y = rect.y + MARGIN
    for row in rows:
      x = rect.x + rect.width - MARGIN
      for text, color in reversed(row):  # right-aligned: draw the rightmost pill first
        size = measure_text_cached(self._font, text, FONT_SIZE)
        w = size.x + 2 * PAD_X
        x -= w
        pill = rl.Rectangle(x, y, w, PILL_H)
        rl.draw_rectangle_rounded(pill, 1.0, 10, rl.Color(0, 0, 0, int(150 * alpha)))
        rl.draw_rectangle_rounded_lines_ex(pill, 1.0, 10, 2, rl.Color(color.r, color.g, color.b, int(200 * alpha)))
        rl.draw_text_ex(self._font, text, rl.Vector2(pill.x + PAD_X, pill.y + (PILL_H - size.y) / 2), FONT_SIZE, 0,
                        rl.Color(color.r, color.g, color.b, int(255 * alpha)))
        x -= GAP
      y += PILL_H + GAP
