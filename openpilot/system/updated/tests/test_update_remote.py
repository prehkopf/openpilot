import subprocess

from openpilot.common.params import Params
from openpilot.system.updated.updated import Updater

HOME = "https://github.com/prehkopf/openpilot.git"


def origin(path):
  return subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=path, text=True).strip()


def repo(tmp_path):
  subprocess.check_call(["git", "init", "-q", str(tmp_path)])
  subprocess.check_call(["git", "remote", "add", "origin", HOME], cwd=tmp_path)
  return str(tmp_path)


def test_follows_a_fork_from_the_switcher(tmp_path):
  path = repo(tmp_path)
  Params().put("UpdaterTargetRemote", "https://github.com/brikowski/openpilot.git")
  Updater().apply_target_remote(path)
  assert origin(path) == "https://github.com/brikowski/openpilot.git"


def test_ignores_a_remote_not_in_the_fork_list(tmp_path):
  # RehkopfPilot: a param written from elsewhere (sunnylink, a restore) must not redirect updates
  path = repo(tmp_path)
  Params().put("UpdaterTargetRemote", "https://github.com/attacker/openpilot.git")
  Updater().apply_target_remote(path)
  assert origin(path) == HOME
