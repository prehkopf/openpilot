"""RehkopfPilot: the forks the branch switcher offers, shared by the UI and the updater.

The updater only follows a remote on this list, so a param written from anywhere else (sunnylink, a restore)
cannot point the device at someone else's code.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Fork:
  name: str
  url: str
  branches: tuple[str, ...]  # the builds worth offering for this van; only those that exist on the remote are shown


# Pick the fork first, then the branch. The installed branch is always offered for the installed fork, and
# "switch branch" still accepts any branch name on the target fork.
FORKS = (
  Fork("RehkopfPilot", "https://github.com/prehkopf/openpilot.git", ("ody-next", "ody-test")),
  Fork("MVL", "https://github.com/mvl-boston/openpilot.git", ("sp-honda-202607", "sp-honda-dev-202608")),
  Fork("brikowski", "https://github.com/brikowski/openpilot.git", ("ody-op", "ody-op-test")),
  Fork("sunnypilot", "https://github.com/sunnypilot/sunnypilot.git", ("release-mici", "release-mici-staging")),
  Fork("comma", "https://github.com/commaai/openpilot.git", ("release-mici", "nightly")),
)
HOME_FORK = FORKS[0]
HOME_INSTALL = "prehkopf/ody-next"


def normalize_remote(url: str) -> str:
  return url.strip().lower().rstrip("/").removesuffix(".git")


def fork_for_url(url: str) -> Fork | None:
  return next((f for f in FORKS if normalize_remote(f.url) == normalize_remote(url)), None)
