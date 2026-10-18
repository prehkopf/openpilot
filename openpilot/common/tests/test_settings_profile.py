"""RehkopfPilot settings profile (settings_profile.json): baseline settings after a reinstall or a sunnylink restore."""
import json

from openpilot.common.params import Params
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.common.settings_profile import APPLIED_KEY, PROFILE_PATH, apply_settings_profile, load_profile


def write_profile(tmp_path, params, version=1):
  p = tmp_path / "profile.json"
  p.write_text(json.dumps({"version": version, "params": params}))
  return str(p)


def test_repo_profile_is_valid():
  profile = load_profile(PROFILE_PATH)
  assert profile is not None and isinstance(profile["version"], int) and profile["params"]
  with OpenpilotPrefix():
    known = set(Params().all_keys())
    known = {k.decode() if isinstance(k, bytes) else k for k in known}
  # every key in the shipped profile exists on this build (load-preset keys are the only allowed exception)
  assert set(profile["params"]) <= known


def test_applies_once_then_stays_out_of_the_way(tmp_path):
  path = write_profile(tmp_path, {"DynamicExperimentalControl": True, "LongitudinalPersonality": 0, "DisableUpdates": False})
  with OpenpilotPrefix():
    p = Params()
    p.put_bool("DisableUpdates", True)  # e.g. what a sunnylink restore left behind
    assert set(apply_settings_profile(p, path=path)) == {"DynamicExperimentalControl", "LongitudinalPersonality", "DisableUpdates"}
    assert p.get_bool("DynamicExperimentalControl") and p.get("LongitudinalPersonality") == 0 and not p.get_bool("DisableUpdates")
    assert p.get(APPLIED_KEY) == "1"
    # the driver changes something afterwards: a reboot (same version) leaves it alone
    p.put("LongitudinalPersonality", 2, block=True)
    assert apply_settings_profile(p, path=path) == []
    assert p.get("LongitudinalPersonality") == 2


def test_force_reapplies_after_restore(tmp_path):
  path = write_profile(tmp_path, {"DisableUpdates": False})
  with OpenpilotPrefix():
    p = Params()
    apply_settings_profile(p, path=path)
    p.put_bool("DisableUpdates", True, block=True)
    assert apply_settings_profile(p, force=True, path=path) == ["DisableUpdates"]
    assert not p.get_bool("DisableUpdates")


def test_new_version_reapplies(tmp_path):
  with OpenpilotPrefix():
    p = Params()
    apply_settings_profile(p, path=write_profile(tmp_path, {"Mads": True}, version=1))
    p.put_bool("Mads", False, block=True)
    assert apply_settings_profile(p, path=write_profile(tmp_path, {"Mads": True}, version=2)) == ["Mads"]
    assert p.get_bool("Mads")


def test_unknown_keys_skipped_and_missing_file_ok(tmp_path):
  with OpenpilotPrefix():
    p = Params()
    assert apply_settings_profile(p, path=write_profile(tmp_path, {"NoSuchKeyOnThisBuild": 1, "Mads": True})) == ["Mads"]
    assert apply_settings_profile(p, force=True, path=str(tmp_path / "missing.json")) == []
