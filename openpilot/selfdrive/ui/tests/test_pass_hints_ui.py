"""RehkopfPilot pass hints: the soft chime plays once per hint, and the setting's labels."""
from openpilot.selfdrive.ui.soundd import PassChime, sound_list, AudibleAlertSP
from openpilot.selfdrive.ui.sunnypilot.mici.widgets.pass_hints import MODES, label_for


def test_chime_plays_once_per_new_hint():
  c = PassChime()
  assert not c.update(3)  # first message after a soundd restart: baseline only, no replay
  assert not c.update(3)
  assert c.update(4)
  assert not c.update(4)
  assert c.update(5)


def test_chime_sound_is_registered_once_only():
  name, loops, _ = sound_list[AudibleAlertSP.passHint]
  assert name == "pass_hint.wav" and loops == 1


def test_setting_labels():
  assert [label_for(v) for v in (0, 1, 2, 3)] == list(MODES)
  assert label_for(None) == "learning" and label_for(9) == "learning"
