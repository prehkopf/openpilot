#!/usr/bin/env bash
# Full PC build of a branch of this fork (Ubuntu 24.04 / WSL), then print the Odyssey tuning it builds.
# usage: build_pc.sh [branch] [dir]     defaults: ody-next ~/odynext
# First run takes a while (clone + ~900 MB of models from sunnypilot's Hugging Face store); rebuilds are ~1-2 min.
set -e
BRANCH=${1:-ody-next}
DIR=${2:-$HOME/odynext}
export PATH="$HOME/.local/bin:$PATH"
command -v git-lfs >/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq git-lfs; }
git lfs install --skip-repo >/dev/null
if [ ! -d "$DIR" ]; then
  git clone --branch "$BRANCH" --recurse-submodules --jobs 8 https://github.com/prehkopf/openpilot.git "$DIR"
fi
cd "$DIR"
git fetch -q origin "$BRANCH" && git checkout -q -B "$BRANCH" "origin/$BRANCH"
git submodule update --init --recursive --jobs 8
git lfs pull
echo "HEAD $(git log --oneline -1) | opendbc $(git -C opendbc_repo log --oneline -1)"
[ -d .venv ] || tools/setup_dependencies.sh
source .venv/bin/activate
scons -j"$(nproc)" > "$DIR/scons.log" 2>&1 && echo "scons ok (t=${SECONDS}s)" || { tail -40 "$DIR/scons.log"; exit 1; }
python tools/ody/check_params.py
