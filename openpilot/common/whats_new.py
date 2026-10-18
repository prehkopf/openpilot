import os
import re

from openpilot.common.basedir import BASEDIR
from openpilot.common.build_name import get_build_name

RELEASE_NOTES_PATH = os.path.join(BASEDIR, "RELEASE_NOTES.md")
SEEN_KEY = "WhatsNewSeenBuild"
ALERT_KEY = "Offroad_WhatsNew"


def release_notes(name: str, path: str = RELEASE_NOTES_PATH) -> list[str]:
  """Bullet lines of the '## <name>' section of RELEASE_NOTES.md."""
  try:
    with open(path) as f:
      text = f.read()
  except OSError:
    return []
  m = re.search(rf"^## {re.escape(name)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
  if not m:
    return []
  return [line[2:].strip() for line in m.group(1).splitlines() if line.startswith("- ")]


def whats_new_text(name: str, path: str = RELEASE_NOTES_PATH) -> str:
  """Card text: the first sentence is the title, the rest is the body (see mici offroad_alerts)."""
  notes = release_notes(name, path)
  return f"{name} is installed. " + "\n".join(f"• {n}" for n in notes) if notes else f"{name} is installed."


def show_whats_new(params, set_alert, name: str | None = None, path: str = RELEASE_NOTES_PATH) -> bool:
  """Once per codename, raise the what's-new card. It clears itself on the next drive (CLEAR_ON_ONROAD_TRANSITION)."""
  name = name if name is not None else get_build_name()
  if not name or params.get(SEEN_KEY) == name:
    return False
  set_alert(ALERT_KEY, True, whats_new_text(name, path))
  params.put(SEEN_KEY, name, block=True)
  return True
