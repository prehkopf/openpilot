#!/usr/bin/env bash
# How far behind each upstream is this checkout? Run before pulling in updates.
# usage: freshness.sh     run from a checkout of this fork (with opendbc_repo initialized)
cd "$(git rev-parse --show-toplevel)"
behind() {  # name url ref [dir]
  git -C "${4:-.}" fetch -q "$2" "$3" 2>/dev/null || { echo "$1: fetch failed"; return; }
  echo "$1: $(git -C "${4:-.}" rev-list --count HEAD..FETCH_HEAD) commits not in this build (latest $(git -C "${4:-.}" log -1 --format=%cs FETCH_HEAD))"
}
behind "comma openpilot master   " https://github.com/commaai/openpilot master
behind "sunnypilot master        " https://github.com/sunnypilot/sunnypilot master
behind "MVL sp-honda-dev-202608  " https://github.com/mvl-boston/openpilot sp-honda-dev-202608
behind "brikowski openpilot ody-op" https://github.com/brikowski/openpilot ody-op
behind "comma opendbc master     " https://github.com/commaai/opendbc master opendbc_repo
behind "brikowski opendbc ody-op " https://github.com/brikowski/opendbc ody-op opendbc_repo
echo "== MVL branches missing or stale in prehkopf/openpilot (for the branch switcher)"
mine=$(git ls-remote --heads https://github.com/prehkopf/openpilot)
git ls-remote --heads https://github.com/mvl-boston/openpilot | while read -r sha ref; do
  f=$(echo "$mine" | awk -v r="$ref" '$2==r{print $1}')
  if [ -z "$f" ]; then echo "MISSING ${ref#refs/heads/}"; elif [ "$f" != "$sha" ]; then echo "STALE ${ref#refs/heads/}"; fi
done
