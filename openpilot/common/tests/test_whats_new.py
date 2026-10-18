"""RehkopfPilot what's-new card: RELEASE_NOTES.md section for the installed codename, shown once after an update."""
from openpilot.common.build_name import get_build_name
from openpilot.common.params import Params
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.common.whats_new import ALERT_KEY, RELEASE_NOTES_PATH, SEEN_KEY, release_notes, show_whats_new, whats_new_text

NOTES = """# notes
## Buckhead
- one
- two

## Atlanta
- old
"""


def test_section_parsing(tmp_path):
  p = tmp_path / "RELEASE_NOTES.md"; p.write_text(NOTES)
  assert release_notes("Buckhead", str(p)) == ["one", "two"]
  assert release_notes("Atlanta", str(p)) == ["old"]
  assert release_notes("Nowhere", str(p)) == []
  assert whats_new_text("Buckhead", str(p)) == "Buckhead is installed. • one\n• two"
  assert whats_new_text("Nowhere", str(p)) == "Nowhere is installed."


def test_shown_once_per_codename(tmp_path):
  p = tmp_path / "RELEASE_NOTES.md"; p.write_text(NOTES)
  calls = []
  with OpenpilotPrefix():
    params = Params()
    assert show_whats_new(params, lambda *a: calls.append(a), name="Buckhead", path=str(p))
    assert calls == [(ALERT_KEY, True, "Buckhead is installed. • one\n• two")]
    assert params.get(SEEN_KEY) == "Buckhead"
    assert not show_whats_new(params, lambda *a: calls.append(a), name="Buckhead", path=str(p))  # reboot: not again
    assert show_whats_new(params, lambda *a: calls.append(a), name="Chattahoochee", path=str(p))  # next release
    assert len(calls) == 2


def test_current_build_has_notes():
  # every release must ship notes for its own codename
  name = get_build_name()
  assert name and release_notes(name, RELEASE_NOTES_PATH), f"RELEASE_NOTES.md has no '## {name}' section"
  assert all(len(n) <= 30 for n in release_notes(name, RELEASE_NOTES_PATH)), "keep notes short so they fit the card"
