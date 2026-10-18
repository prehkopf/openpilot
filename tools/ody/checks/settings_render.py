# Render the comma four settings home and every settings group page to PNG contact sheets (PC, offscreen).
# usage (via run_py.sh): settings_render.py <out dir>
import os
import sys
import time

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
from openpilot.common.prefix import OpenpilotPrefix
PREFIX = OpenpilotPrefix()
PREFIX.__enter__()

import pyray as rl

rl.set_config_flags(rl.ConfigFlags.FLAG_WINDOW_HIDDEN)
os.environ["OFFSCREEN"] = "1"
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app

gui_app.init_window("settings", fps=60)
from openpilot.selfdrive.ui.sunnypilot.mici.layouts.settings import SettingsLayoutSP

W, H = gui_app.width, gui_app.height


def frames(widget, name):
  # one wide offscreen canvas holding the whole page, so every card shows in full
  widget.set_rect(rl.Rectangle(0, 0, W, H))
  widget.show_event()
  for _ in range(5):
    ui_state.update()
    widget.render(rl.Rectangle(0, 0, W, H))
  width = int(max(W, widget._scroller.content_size + 60))
  tex = rl.load_render_texture(width, H)
  for _ in range(40):
    ui_state.update()
    rl.begin_texture_mode(tex)
    rl.clear_background(rl.BLACK)
    widget.render(rl.Rectangle(0, 0, width, H))
    rl.end_texture_mode()
    time.sleep(0.003)
  img = rl.load_image_from_texture(tex.texture)
  rl.image_flip_vertical(img)
  rl.export_image(img, f"{OUT}/{name}.png")
  labels = [getattr(getattr(i, "_label", None), "text", None) or type(i).__name__ for i in widget._scroller.items if i.is_visible]
  print(f"{name}: {labels}")


ui_state.update_params()  # the UI main loop does this at startup (sets always_offroad etc.)
home = SettingsLayoutSP()
frames(home, "0_home")
# every labelled card on the home screen opens a group page; follow the home order, name files by label
groups = [i for i in home._scroller.items if getattr(getattr(i, "_label", None), "text", "")]
for n, btn in enumerate(groups, 1):
  name = f"{n}_" + "".join(c if c.isalnum() else "_" for c in btn._label.text.replace("\n", " ")).strip("_")
  pushed = []
  orig = gui_app.push_widget
  gui_app.push_widget = pushed.append
  btn._click_callback()
  gui_app.push_widget = orig
  frames(pushed[0], name)
