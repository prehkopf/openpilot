from openpilot.common.forks import FORKS, HOME_FORK, fork_for_url


def test_known_forks_match_however_written():
  assert fork_for_url("https://github.com/prehkopf/openpilot.git") == HOME_FORK
  assert fork_for_url(" https://github.com/PREHKOPF/openpilot/ ") == HOME_FORK
  for fork in FORKS:
    assert fork_for_url(fork.url.removesuffix(".git")) == fork


def test_anything_else_is_not_a_fork():
  for url in ("https://github.com/attacker/openpilot.git", "https://example.com/prehkopf/openpilot.git",
              "git@github.com:prehkopf/openpilot.git", "", "https://github.com/prehkopf/openpilot.git.evil"):
    assert fork_for_url(url) is None, url
