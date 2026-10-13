#!/usr/bin/env bash
# A/B process replay of the Honda routes: a base commit (default: the sunnypilot master this fork tracks)
# against the current checkout. Every difference should trace to a deliberate MVL or brikowski change.
# usage: replay_ab.sh [base ref or sha] [base dir]    run from a built checkout (see build_pc.sh)
set -e
export PATH="$HOME/.local/bin:$PATH"
HERE=$(git rev-parse --show-toplevel)
BASE_DIR=${2:-$HOME/spbase}
git -C "$HERE" fetch -q https://github.com/sunnypilot/sunnypilot.git "${1:-master}"
BASE=$(git -C "$HERE" rev-parse FETCH_HEAD)
echo "base $BASE"
[ -d "$BASE_DIR" ] || git -C "$HERE" worktree add -f --detach "$BASE_DIR" "$BASE"
cd "$BASE_DIR"
git checkout -q --detach "$BASE"
git submodule update --init --recursive --jobs 8 >/dev/null 2>&1
git lfs pull
uv sync --frozen --all-extras -q
source .venv/bin/activate
scons -j"$(nproc)" > "$BASE_DIR/scons.log" 2>&1 || { tail -40 "$BASE_DIR/scons.log"; exit 1; }
cd openpilot/selfdrive/test/process_replay
python test_processes.py -j 8 --whitelist-cars HONDA HONDA2 > "$BASE_DIR/replay.log" 2>&1 || true
deactivate

PR="$HERE/openpilot/selfdrive/test/process_replay"
mkdir -p "$PR/fakedata"
cp fakedata/*_"$BASE".zst "$PR/fakedata/"
cd "$HERE" && source .venv/bin/activate
echo "$BASE" > "$PR/ref_commit"
cd "$PR"
python test_processes.py -j 8 --whitelist-cars HONDA HONDA2 2>&1 | grep -v "^progress" | tail -150
echo "===== diff.txt ====="
head -300 diff.txt
rm -f ref_commit
