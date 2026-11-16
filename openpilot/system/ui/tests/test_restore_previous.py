"""Restore previous (Jasper): hidden without a whole backup; the swap never leaves the install directory missing."""
import os
from pathlib import Path

import pytest

from openpilot.system.ui import restore_previous as rp


def make_install(path: Path, tag: str) -> Path:
  (path / "openpilot").mkdir(parents=True)
  (path / "launch_openpilot.sh").write_text("#!/bin/bash\n")
  (path / "BUILD_NAME").write_text(tag)
  return path


@pytest.fixture
def lab(tmp_path):
  base = make_install(tmp_path / "openpilot", "Jasper")
  staging = tmp_path / "safe_staging"
  backup = make_install(staging / "old_openpilot", "Ideal")
  flag = staging / "finalized" / ".overlay_consistent"
  flag.parent.mkdir(parents=True)
  flag.write_text("")
  return base, backup, flag


def test_hidden_without_a_backup(tmp_path):
  assert not rp.backup_available(str(tmp_path / "missing"))


def test_hidden_with_a_partial_backup(tmp_path):
  (tmp_path / "old").mkdir()
  (tmp_path / "old" / "launch_openpilot.sh").write_text("")
  assert not rp.backup_available(str(tmp_path / "old"))  # no code
  (tmp_path / "old2" / "openpilot").mkdir(parents=True)
  assert not rp.backup_available(str(tmp_path / "old2"))  # no launcher


def test_restore_swaps_and_cleans_up(lab):
  base, backup, flag = lab
  calls = []
  assert rp.restore_previous(str(base), str(backup), str(flag), disable_updates=lambda: calls.append(1))
  assert (base / "BUILD_NAME").read_text() == "Ideal"
  assert not backup.exists()
  assert not Path(str(base) + ".failed").exists()
  assert not flag.exists(), "the launcher would install the failed build again"
  assert calls == [1], "updates must be turned off so the failed build isn't downloaded again"


def test_no_backup_changes_nothing(lab, tmp_path):
  base, _, flag = lab
  assert not rp.restore_previous(str(base), str(tmp_path / "nothing"), str(flag))
  assert (base / "BUILD_NAME").read_text() == "Jasper"
  assert flag.exists()


def test_failed_swap_puts_the_current_install_back(lab, monkeypatch):
  base, backup, flag = lab
  real_rename = os.rename

  def rename(src, dst):
    if str(src) == str(backup):
      raise OSError("simulated failure moving the backup in")
    return real_rename(src, dst)

  monkeypatch.setattr(rp.os, "rename", rename)
  assert not rp.restore_previous(str(base), str(backup), str(flag))
  assert (base / "BUILD_NAME").read_text() == "Jasper", "the install directory must never be left missing"
  assert backup.exists()


def test_params_failure_does_not_undo_the_restore(lab):
  base, backup, flag = lab

  def boom():
    raise RuntimeError("params unavailable")

  assert rp.restore_previous(str(base), str(backup), str(flag), disable_updates=boom)
  assert (base / "BUILD_NAME").read_text() == "Ideal"


def test_error_screen_wires_the_button_safely():
  # text.py needs raylib to import; check its source: the button exists, is hidden on PC and without a backup,
  # and goes through restore_previous (not a delete-then-move of BASEDIR)
  src = (Path(__file__).resolve().parents[1] / "text.py").read_text()
  assert 'Button("Restore previous"' in src
  assert "set_visible(not PC and backup_available())" in src
  assert "restore_previous(BASEDIR" in src
  assert "rmtree" not in src
