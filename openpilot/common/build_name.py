from functools import cache
import os

from openpilot.common.basedir import BASEDIR

BUILD_NAME_PATH = os.path.join(BASEDIR, "BUILD_NAME")


@cache
def get_build_name() -> str:
  """RehkopfPilot release codename (Georgia places, A to Z), from the BUILD_NAME file at the repo root."""
  try:
    with open(BUILD_NAME_PATH) as f:
      return f.read().strip()
  except OSError:
    return ""


def build_label(commit: str) -> str:
  """'Atlanta • a60fd7e', or just the short hash when there is no codename. '•' is in the UI font's glyph set."""
  name = get_build_name()
  return f"{name} • {commit[:7]}" if name else commit[:7]
