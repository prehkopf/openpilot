import subprocess
import threading
import pyray as rl
from enum import IntEnum
from collections.abc import Callable

from openpilot.common.forks import FORKS, HOME_FORK, HOME_INSTALL, Fork, fork_for_url
from openpilot.common.forks import normalize_remote as _norm
from openpilot.common.time_helpers import system_time_valid
from openpilot.selfdrive.ui.mici.layouts.settings.device.device_layout import EngagedConfirmationButton
from openpilot.selfdrive.ui.mici.widgets.info import InfoLayoutMici
from openpilot.selfdrive.ui.mici.widgets.button import BigButton
from openpilot.selfdrive.ui.mici.widgets.dialog import BigConfirmationDialog, BigDialog, BigInputDialog
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, MousePos
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets.scroller import NavScroller

UPDATER_TIMEOUT = 10.0  # seconds to wait for updater to respond


def _split_description(desc: str) -> tuple[str, str, str, str] | None:
  # UpdaterCurrentDescription/UpdaterNewDescription format: "version / branch / commit / date"
  parts = [p.strip() for p in desc.split(" / ")]
  if len(parts) != 4:
    return None
  version, branch, commit, date = parts
  return version, branch, commit, date


class UpdaterState(IntEnum):
  IDLE = 0
  WAITING_FOR_UPDATER = 1
  UPDATER_RESPONDING = 2


class SoftwareInfoLayoutMici(InfoLayoutMici):
  def __init__(self):
    super().__init__("version", "", "branch", "")

  def _update_state(self):
    super()._update_state()

    desc = _split_description(ui_state.params.get("UpdaterCurrentDescription") or "")
    if desc is not None:
      version, branch, commit, date = desc
      self.subtext1.set_text(f"{version} ({date})")
      self.subtext2.set_text(f"{branch} ({commit})")
    else:
      self.subtext1.set_text(ui_state.params.get("Version") or "N/A")
      self.subtext2.set_text(ui_state.params.get("GitBranch") or "N/A")


class CheckUpdateButton(BigButton):
  UPDATER_PROC = "openpilot.system.updated.updated"
  CHECK_FOR_UPDATE = "SIGUSR1"
  DOWNLOAD_UPDATE = "SIGHUP"

  def __init__(self):
    self._txt_update_icon = gui_app.texture("icons_mici/settings/device/update.png", 64, 75)
    self._txt_up_to_date_icon = gui_app.texture("icons_mici/settings/device/up_to_date.png", 64, 64)
    super().__init__("check for update", "", self._txt_update_icon)

    self._waiting_for_updater_t: float | None = None
    self._hide_value_t: float | None = None
    self._state: UpdaterState = UpdaterState.IDLE

    ui_state.add_offroad_transition_callback(self.offroad_transition)

  def offroad_transition(self):
    if ui_state.is_offroad():
      self.set_enabled(True)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    super()._handle_mouse_release(mouse_pos)

    if not system_time_valid():
      dlg = BigDialog("", tr("Please connect to Wi-Fi to update."))
      gui_app.push_widget(dlg)
      return

    self._signal_updater(self.DOWNLOAD_UPDATE if self.get_value() == "download update" else self.CHECK_FOR_UPDATE)

  def check_for_update(self):
    self._signal_updater(self.CHECK_FOR_UPDATE)

  def _signal_updater(self, sig: str):
    self.set_enabled(False)
    self._state = UpdaterState.WAITING_FOR_UPDATER
    self._hide_value_t = None
    self.set_value("")
    self.set_icon(self._txt_update_icon)

    def run():
      subprocess.run(f"pkill -{sig} -f {self.UPDATER_PROC}", shell=True)

    threading.Thread(target=run, daemon=True).start()

  def set_value(self, value: str):
    super().set_value(value)
    if value:
      self.set_text("")
    else:
      self.set_text("check for update")

  def _update_state(self):
    super()._update_state()

    if ui_state.started:
      self.set_enabled(False)
      return

    updater_state = ui_state.params.get("UpdaterState") or ""
    failed_count = ui_state.params.get("UpdateFailedCount") or 0
    failed = int(failed_count) > 0

    if self._state == UpdaterState.WAITING_FOR_UPDATER:
      self.set_rotate_icon(True)
      if updater_state != "idle":
        self._state = UpdaterState.UPDATER_RESPONDING

      # Recover from updater not responding (time invalid shortly after boot)
      if self._waiting_for_updater_t is None:
        self._waiting_for_updater_t = rl.get_time()

      if self._waiting_for_updater_t is not None and rl.get_time() - self._waiting_for_updater_t > UPDATER_TIMEOUT:
        self.set_rotate_icon(False)
        self.set_value("updater failed\nto respond")
        self._state = UpdaterState.IDLE
        self._hide_value_t = rl.get_time()

    elif self._state == UpdaterState.UPDATER_RESPONDING:
      if updater_state == "idle":
        self.set_rotate_icon(False)
        self._state = UpdaterState.IDLE
        self._hide_value_t = rl.get_time()
      else:
        if self.get_value() != updater_state:
          self.set_value(updater_state)

    elif self._state == UpdaterState.IDLE:
      self.set_rotate_icon(False)
      if failed:
        self.set_enabled(True)  # allow retry when failure came from updater param
        if self.get_value() != "failed to update":
          self.set_value("failed to update")

      elif ui_state.params.get_bool("UpdaterFetchAvailable"):
        self.set_enabled(True)
        if self.get_value() != "download update":
          self.set_value("download update")

      elif self._hide_value_t is not None:
        self.set_enabled(True)
        if self.get_value() == "checking...":
          self.set_value("up to date")
          self.set_icon(self._txt_up_to_date_icon)

        # Hide previous text after short amount of time (up to date or failed)
        if rl.get_time() - self._hide_value_t > 3.0:
          self._hide_value_t = None
          self.set_value("")
          self.set_icon(self._txt_update_icon)
      else:
        if self.get_value() != "":
          self.set_value("")

    if self._state != UpdaterState.WAITING_FOR_UPDATER:
      self._waiting_for_updater_t = None


class InstallUpdateButton(BigButton):
  def __init__(self):
    super().__init__("install now", "", gui_app.texture("icons_mici/settings/device/reboot.png", 64, 70))
    self.set_visible(lambda: ui_state.is_offroad() and ui_state.params.get_bool("UpdateAvailable"))

  def _update_state(self):
    super()._update_state()

    desc = _split_description(ui_state.params.get("UpdaterNewDescription") or "")
    value = f"{desc[0]} ({desc[1]})" if desc is not None else ""
    if self.get_value() != value:
      self.set_value(value)

  def _handle_mouse_release(self, mouse_pos: MousePos):
    super()._handle_mouse_release(mouse_pos)

    self.set_enabled(False)

    def run():
      ui_state.params.put_bool("DoReboot", True, block=True)

    threading.Thread(target=run, daemon=True).start()


def target_remote(params) -> str:
  """The remote the next update downloads from: the chosen one, else the installed one."""
  return params.get("UpdaterTargetRemote") or params.get("GitRemote") or HOME_FORK.url


def branch_options(fork: Fork, remote_branches: set[str], installed_remote: str, installed_branch: str) -> list[str]:
  """Branches to offer for a fork: its curated list, filtered to what exists, plus the installed branch on its fork."""
  options = [b for b in fork.branches if b in remote_branches]
  if _norm(fork.url) == _norm(installed_remote) and installed_branch in remote_branches and installed_branch not in options:
    options.insert(0, installed_branch)
  return options


def ls_remote_branches(url: str, timeout: float = 20.0) -> set[str] | None:
  try:
    out = subprocess.run(["git", "ls-remote", "--heads", url], capture_output=True, text=True, timeout=timeout, check=True).stdout
  except (subprocess.SubprocessError, OSError):
    return None
  return {line.split("refs/heads/", 1)[1] for line in out.splitlines() if "refs/heads/" in line}


class ForkSelectPage(NavScroller):
  def __init__(self, on_select: Callable[[Fork, str], None]):
    super().__init__()
    current = fork_for_url(target_remote(ui_state.params))
    self._on_select = on_select
    buttons = []
    for fork in FORKS:
      owner = fork.url.split("github.com/")[-1].removesuffix(".git").split("/")[0]
      # no icon: it would wrap "RehkopfPilot" mid-word; the current fork is marked in the subtitle instead
      btn = BigButton(fork.name, f"{owner} • current" if fork == current else owner)
      btn.set_click_callback(lambda f=fork: gui_app.push_widget(ForkBranchPage(f, self._picked)))
      buttons.append(btn)
    self._scroller.add_widgets(buttons)

  def _picked(self, fork: Fork, branch: str):
    # the branch page has already closed itself; close this one too, then apply the choice
    self.dismiss(lambda: self._on_select(fork, branch))


class ForkBranchPage(NavScroller):
  """Branches on one fork. Asks GitHub which exist (in the background) so only installable ones are offered."""
  def __init__(self, fork: Fork, on_select: Callable[[Fork, str], None]):
    super().__init__()
    self._fork = fork
    self._on_select = on_select
    self._result: set[str] | None = None
    self._done = threading.Event()
    self._shown = False
    self._status = BigButton(fork.name, "checking GitHub...")
    self._status.set_enabled(False)
    self._scroller.add_widgets([self._status])
    threading.Thread(target=self._fetch, daemon=True).start()

  def _fetch(self):
    self._result = ls_remote_branches(self._fork.url)
    self._done.set()

  def _update_state(self):
    super()._update_state()
    if self._shown or not self._done.is_set():
      return
    self._shown = True
    params = ui_state.params
    if self._result is None:
      self._status.set_value("couldn't reach GitHub")
      return
    options = branch_options(self._fork, self._result, params.get("GitRemote") or "", params.get("GitBranch") or "")
    if not options:
      self._status.set_value("no builds for this van")
      return
    check_icon = gui_app.texture("icons_mici/settings/device/up_to_date.png", 64, 64)
    targeted = fork_for_url(target_remote(params)) == self._fork
    buttons = []
    if self._leaving_home():
      note = BigButton("one-way: reinstall", HOME_INSTALL)  # the value line fits ~17 characters
      note.set_enabled(False)
      buttons.append(note)
    for branch in options:
      on_target = targeted and branch == (params.get("UpdaterTargetBranch") or "")
      btn = BigButton(branch, "", check_icon if on_target else None, scroll=True)
      btn.set_click_callback(lambda b=branch: self._choose(b))
      buttons.append(btn)
    self._scroller.items.clear()
    self._scroller.add_widgets(buttons)

  def _leaving_home(self) -> bool:
    # other forks' software can't switch back to this fork from their own menus
    return self._fork != HOME_FORK and fork_for_url(ui_state.params.get("GitRemote") or "") == HOME_FORK

  def _choose(self, branch: str):
    if self._leaving_home():
      icon = gui_app.texture("icons_mici/settings/device/update.png", 64, 64)
      gui_app.push_widget(BigConfirmationDialog(f"switch to {self._fork.name}", icon, confirm_callback=lambda: self._finish(branch)))
    else:
      self._finish(branch)

  def _finish(self, branch: str):
    self.dismiss(lambda: self._on_select(self._fork, branch))


def target_label(params) -> str:
  fork = fork_for_url(target_remote(params))
  branch = params.get("UpdaterTargetBranch") or ""
  return f"{fork.name}/{branch}" if fork and fork != HOME_FORK else branch


class TargetBranchButton(BigButton):
  def __init__(self, check_update_btn: CheckUpdateButton):
    super().__init__("target branch", target_label(ui_state.params),
                     description="Pick whose software (RehkopfPilot, MVL, brikowski, ...) and which build to download.")
    self._check_update_btn = check_update_btn
    self.set_click_callback(self._on_click)
    self.set_visible(not ui_state.params.get_bool("IsTestedBranch"))
    self.set_enabled(lambda: ui_state.is_offroad())

  def _update_state(self):
    super()._update_state()

    target = target_label(ui_state.params)
    if self.get_value() != target:
      self.set_value(target)

  def _on_click(self):
    gui_app.push_widget(ForkSelectPage(self._on_select))

  def _on_select(self, fork: Fork, branch: str):
    ui_state.params.put("UpdaterTargetRemote", fork.url, block=True)
    ui_state.params.put("UpdaterTargetBranch", branch, block=True)
    self.set_value(target_label(ui_state.params))
    self._check_update_btn.check_for_update()


class SoftwareLayoutMici(NavScroller):
  def __init__(self):
    super().__init__()

    check_update_btn = CheckUpdateButton()

    def switch_branch_handle_selection(new_branch: str):
      if new_branch:
        ui_state.params.put("UpdaterTargetBranch", new_branch, block=True)
        check_update_btn.check_for_update()
        self._scroller.scroll_panel.set_offset(-300)

    def switch_branch_clicked():
      current_branch = ui_state.params.get("GitBranch") or ""
      dlg = BigInputDialog("enter branch", current_branch, minimum_length=1,
                           confirm_callback=switch_branch_handle_selection)
      gui_app.push_widget(dlg)
      return

    switch_branch_btn = BigButton("switch branch", "", gui_app.texture("icons_mici/settings/device/update.png", 64, 64))
    switch_branch_btn.set_click_callback(switch_branch_clicked)

    def uninstall_openpilot_callback():
      ui_state.params.put_bool("DoUninstall", True, block=True)

    uninstall_openpilot_btn = EngagedConfirmationButton("uninstall RehkopfPilot", "uninstall",
                                                        gui_app.texture("icons_mici/settings/device/uninstall.png", 64, 64),
                                                        uninstall_openpilot_callback, exit_on_confirm=False,
                                                        description="Remove RehkopfPilot from this device.",
                                                        description_icon=gui_app.texture("icons_mici/setup/factory_reset.png", 64, 64))

    self._scroller.add_widgets([
      SoftwareInfoLayoutMici(),
      check_update_btn,
      InstallUpdateButton(),
      TargetBranchButton(check_update_btn),
      switch_branch_btn,
      uninstall_openpilot_btn,
    ])
