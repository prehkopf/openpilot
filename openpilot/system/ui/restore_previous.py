"""RehkopfPilot (Jasper): put the previous install back from the error screen, in an order that can't leave no openpilot.

Idea from FrogPilot ("Restore the previous version from the error screen"). The launcher already keeps the install it
replaced at /data/safe_staging/old_openpilot (launch_chffrplus.sh moves it there when it applies an update), and the
updater clears it only once it runs again. So the backup is there exactly when a new build crashes before the updater
starts, which is the case this button is for.

FrogPilot deletes BASEDIR first and then moves the backup in, so a failure in between leaves no openpilot at all. Here:
1. check the backup looks like an install (launch script and openpilot/ present);
2. rename the failed install aside (same filesystem, atomic), then rename the backup into BASEDIR;
   if that second rename fails, rename the failed install back and stop;
3. only then delete the failed install;
4. remove the finalized update so the launcher doesn't install the failed build again on the next boot, and turn off
   automatic updates so the updater doesn't download it again (turn them back on in Settings > Software).
After the reboot the restored launcher runs its own AGNOS check (agnos_init), so a restored build that needs a different
AGNOS flashes it as it would after any update.
"""
import os
import shutil

STAGING_ROOT = os.getenv("UPDATER_STAGING_ROOT", "/data/safe_staging")
BACKUP_DIR = os.path.join(STAGING_ROOT, "old_openpilot")
FINALIZED_FLAG = os.path.join(STAGING_ROOT, "finalized", ".overlay_consistent")
LAUNCH_SCRIPTS = ("launch_openpilot.sh", "launch_chffrplus.sh")


def backup_available(backup: str = BACKUP_DIR) -> bool:
  """True when the backup looks like a whole install: a launch script and the code."""
  if not os.path.isdir(backup):
    return False
  has_launcher = any(os.path.isfile(os.path.join(backup, s)) for s in LAUNCH_SCRIPTS)
  has_code = os.path.isdir(os.path.join(backup, "openpilot")) or os.path.isdir(os.path.join(backup, "selfdrive"))
  return has_launcher and has_code


def restore_previous(basedir: str, backup: str = BACKUP_DIR, finalized_flag: str = FINALIZED_FLAG,
                     disable_updates=None) -> bool:
  """Swap the backup into basedir. Returns True when the backup is in place. Never leaves basedir missing."""
  if not backup_available(backup):
    return False
  basedir = basedir.rstrip("/")
  failed = basedir + ".failed"
  if os.path.lexists(failed):
    shutil.rmtree(failed, ignore_errors=True)

  os.rename(basedir, failed)
  try:
    os.rename(backup, basedir)
  except OSError:
    os.rename(failed, basedir)  # put the failed install back rather than leave nothing
    return False

  shutil.rmtree(failed, ignore_errors=True)
  try:
    os.remove(finalized_flag)
  except FileNotFoundError:
    pass
  if disable_updates is not None:
    try:
      disable_updates()
    except Exception:
      pass  # the restore itself is done; a params failure must not undo it
  return True
