"""RehkopfPilot user-first branch switcher: pick the fork, then the branch; the updater follows the chosen fork."""
import subprocess

from openpilot.selfdrive.ui.mici.layouts.settings.software import (FORKS, HOME_FORK, branch_options, fork_for_url, target_label,
                                                                   target_remote)

MVL = next(f for f in FORKS if f.name == "MVL")


class FakeParams:
  def __init__(self, **v):
    self.v = v

  def get(self, k, *a, **kw):
    return self.v.get(k)


def test_fork_for_url_normalizes():
  assert fork_for_url("https://github.com/prehkopf/openpilot.git") == HOME_FORK
  assert fork_for_url("https://github.com/PREHKOPF/openpilot/") == HOME_FORK
  assert fork_for_url("https://github.com/mvl-boston/openpilot") == MVL
  assert fork_for_url("https://example.com/x.git") is None


def test_branch_options_filter_to_existing_and_keep_installed():
  remote = {"ody-next", "ody-test", "ody-sg", "some-accord-branch"}
  assert branch_options(HOME_FORK, remote, HOME_FORK.url, "ody-next") == ["ody-next", "ody-test"]
  # installed branch outside the curated list is still offered, first, on its own fork only
  assert branch_options(HOME_FORK, remote, HOME_FORK.url, "ody-sg") == ["ody-sg", "ody-next", "ody-test"]
  assert branch_options(MVL, {"sp-honda-202607", "sp-honda-dev-202608", "ody-sg"}, HOME_FORK.url, "ody-sg") == \
    ["sp-honda-202607", "sp-honda-dev-202608"]
  # curated names that don't exist on the remote are not offered
  assert branch_options(MVL, {"sp-honda-202607"}, HOME_FORK.url, "ody-next") == ["sp-honda-202607"]


def test_target_remote_and_label():
  p = FakeParams(GitRemote=HOME_FORK.url, UpdaterTargetBranch="ody-next")
  assert target_remote(p) == HOME_FORK.url and target_label(p) == "ody-next"
  p = FakeParams(GitRemote=HOME_FORK.url, UpdaterTargetRemote=MVL.url, UpdaterTargetBranch="sp-honda-202607")
  assert target_remote(p) == MVL.url and target_label(p) == "MVL/sp-honda-202607"


def _git(*args, cwd):
  return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_updater_follows_chosen_fork(tmp_path):
  from openpilot.system.updated.updated import Updater
  _git("init", "-q", cwd=tmp_path)
  _git("remote", "add", "origin", HOME_FORK.url, cwd=tmp_path)
  u = object.__new__(Updater)
  u.params = FakeParams()
  u.apply_target_remote(str(tmp_path))  # nothing chosen: untouched
  assert _git("remote", "get-url", "origin", cwd=tmp_path) == HOME_FORK.url
  u.params = FakeParams(UpdaterTargetRemote=MVL.url)
  u.apply_target_remote(str(tmp_path))
  assert _git("remote", "get-url", "origin", cwd=tmp_path) == MVL.url
  u.apply_target_remote(str(tmp_path))  # idempotent
  assert _git("remote", "get-url", "origin", cwd=tmp_path) == MVL.url
