import json
import os

from openpilot.common.basedir import BASEDIR
from openpilot.common.swaglog import cloudlog

PROFILE_PATH = os.path.join(BASEDIR, "settings_profile.json")
APPLIED_KEY = "SettingsProfileApplied"


def load_profile(path: str = PROFILE_PATH) -> dict | None:
  try:
    with open(path) as f:
      return json.load(f)
  except (OSError, ValueError):
    return None


def apply_settings_profile(params, force: bool = False, path: str = PROFILE_PATH) -> list[str]:
  """Apply RehkopfPilot's baseline settings. Without force, only when this profile version hasn't been applied yet
  (a reinstall wipes params, so it applies again). Keys this build doesn't have are skipped. Returns keys written."""
  profile = load_profile(path)
  if not profile:
    return []
  version = str(profile.get("version", ""))
  if not force and params.get(APPLIED_KEY) == version:
    return []
  known = {k.decode() if isinstance(k, bytes) else k for k in params.all_keys()}
  written = []
  for key, value in profile.get("params", {}).items():
    if key not in known:
      continue
    if isinstance(value, bool):
      params.put_bool(key, value, block=True)
    else:
      params.put(key, value, block=True)
    written.append(key)
  params.put(APPLIED_KEY, version, block=True)
  cloudlog.warning(f"settings profile v{version} applied ({'forced' if force else 'new'}): {', '.join(written)}")
  return written
