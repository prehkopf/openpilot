#!/usr/bin/env bash
# Pre-push checklist for RehkopfPilot releases. Run from a PC build of this fork (WSL / Ubuntu 24.04).
# usage: tools/ody/prepush.sh [--full] [--target ody-next|ody-test] [--rlogs DIR]
#   default (~4 min): build, models on PC, code scans, unit/UI tests, Honda car + safety tests,
#                     replay of a recorded Odyssey segment (card, controlsd, plannerd), recorded turns vs lane
#                     changes, submodule pins, release bump
#   --full          : also opendbc's whole suite (tools/ody/opendbc_test.sh) and the A/B replay
# Exits non-zero if any required check fails. Warnings never fail the run.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT=$PWD
FULL=0; TARGET=""; RLOGS="${RLOGS:-/mnt/c/Users/$(ls /mnt/c/Users 2>/dev/null | grep -v -E '^(Public|Default|All Users|Default User|desktop.ini)$' | head -1)/Documents/openpilot/rlogs}"
while [ $# -gt 0 ]; do
  case "$1" in
    --full) FULL=1 ;;
    --target) TARGET="$2"; shift ;;
    --rlogs) RLOGS="$2"; shift ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac; shift
done
[ -z "$TARGET" ] && TARGET=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null | sed 's#^origin/##')
source .venv/bin/activate
export PYTHONPATH="$ROOT"
CHECKS="$ROOT/tools/ody/checks"
LOG=$(mktemp -d)
FAILS=(); WARNS=()
step() {  # name, command...   (required)
  local name=$1; shift
  local t0=$SECONDS
  if "$@" > "$LOG/$name.log" 2>&1; then printf "  PASS  %-22s %4ss\n" "$name" $((SECONDS-t0))
  else printf "  FAIL  %-22s %4ss  (log: %s)\n" "$name" $((SECONDS-t0)) "$LOG/$name.log"; tail -15 "$LOG/$name.log" | sed 's/^/        | /'; FAILS+=("$name"); fi
}
warn() { printf "  WARN  %s\n" "$*"; WARNS+=("$*"); }

echo "RehkopfPilot pre-push: $(git log --oneline -1) -> ${TARGET:-<no target>}"
echo "build: $(cat BUILD_NAME 2>/dev/null) $(grep -o '"[^"]*"' openpilot/sunnypilot/common/version.h)"

# 1. build (params keys are compiled in, so a stale build gives false UnknownKeyName failures)
step build scons -j"$(nproc)"

# 2. the processes no unit test starts: driving model + driver monitoring, loaded and run on PC
step models python "$CHECKS/model_e2e.py"

#    store models are downloaded precompiled, unlike the default model: the live catalog must match this build
step model_store python "$CHECKS/model_store.py"
grep -q "^WARN" "$LOG/model_store.log" && warn "$(grep '^WARN' "$LOG/model_store.log" | head -1 | sed 's/^WARN //')"

# 3. static scans: unresolved imports, unregistered params keys, unknown services
step imports python -I "$CHECKS/importscan.py" "$ROOT"
step params python -I "$CHECKS/paramscan.py" "$ROOT"
step services python "$CHECKS/svcscan.py" "$ROOT"
step lint ruff check openpilot/selfdrive openpilot/sunnypilot openpilot/system openpilot/common tools/ody
#    the device installer pulls LFS from .lfsconfig's host only; comma-merged objects can be missing there
step lfs_host python -I "$CHECKS/lfs_host.py" "$ROOT"

# 4. tests: openpilot + sunnypilot unit/UI tests, Honda car and safety tests
#    locationd/calibrationd scenario tests assert comma's thresholds; MVL widened them on purpose (mount tolerance)
step pytest bash -c "cd openpilot && python -m pytest -q -p no:cacheprovider -n $(nproc) --timeout=300 common selfdrive system sunnypilot \
  --ignore=selfdrive/test/process_replay --ignore=selfdrive/ui/tests/diff \
  --deselect openpilot/selfdrive/locationd/test/test_calibrationd.py::TestCalibrationd::test_calibration_auto_reset \
  --deselect openpilot/selfdrive/locationd/test/test_locationd_scenarios.py::TestLocationdScenarios::test_consistent_gyro_spikes \
  --deselect openpilot/selfdrive/locationd/test/test_locationd_scenarios.py::TestLocationdScenarios::test_consistent_timing_spikes \
  --deselect openpilot/sunnypilot/selfdrive/locationd/tests/test_locationd.py::TestLocationdProc::test_params_gps \
  -k 'not onroad and not power_draw and not test_models_segs'"
#    timing-sensitive (waits 5 s for a param); alone and retried so CPU load from the parallel run can't fail it.
#    It passes 10/10 on a quiet machine but failed 3 back-to-back retries right after the parallel run, so wait
#    (up to 60 s) for the 1-minute load average to drop under a quarter of the cores, and pause between retries.
settle() { for _ in $(seq 30); do awk -v n="$(nproc)" '{exit !($1 < n / 4)}' /proc/loadavg && return; sleep 2; done; }
settle
step locationd_gps bash -c "cd openpilot && for i in 1 2 3; do timeout 120 python -m pytest -q -p no:cacheprovider --timeout=60 \
  sunnypilot/selfdrive/locationd/tests/test_locationd.py::TestLocationdProc::test_params_gps && exit 0; sleep 10; done; exit 1"
#    settings pages are built only at UI start and drawn only when opened: build + render every one offscreen
step settings_ui python tools/ody/checks/settings_render.py "$LOG/settings"
step honda_car env PYTHONPATH="$ROOT/opendbc_repo:$ROOT" python -m pytest -q -p no:cacheprovider opendbc_repo/opendbc/car/honda/tests
#    same tests split across workers: the Odyssey get_params sets class-level CarControllerParams values, so a test
#    can pass serially only because an earlier test built Odyssey params in the same process
step honda_car_parallel env PYTHONPATH="$ROOT/opendbc_repo:$ROOT" python -m pytest -q -p no:cacheprovider -n "$(nproc)" \
  opendbc_repo/opendbc/car/honda/tests
step honda_safety env PYTHONPATH="$ROOT/opendbc_repo:$ROOT" python -m pytest -q -p no:cacheprovider opendbc_repo/opendbc/safety/tests/test_honda.py

# 5. card + controlsd from this build on a recorded Odyssey drive (newest pulled segment with openpilot long)
SEG=$(ls -d "$RLOGS"/*--*--* 2>/dev/null | sort -V | tail -40 | head -1)
if [ -n "$SEG" ]; then step replay python tools/ody/replay_segments.py "$SEG"; else warn "no rlogs at $RLOGS, skipped own-drive replay"; fi
#    this build's DesireHelper over recorded turns and lane changes: no more lane changes started in real turns, and
#    no fewer real lane changes, than the build that drove them (a turn on the gas once started a lane change)
if [ -n "$SEG" ]; then step turn_lane_change python "$CHECKS/turn_lane_change.py" "$RLOGS"; fi
#    factory mode leaves the van stock: card passive, noOutput safety, nothing sent (no radar silence)
if [ -n "$SEG" ]; then step factory_mode python "$CHECKS/factory_mode.py" "$SEG"; fi
#    calmer stop-and-go DEC: no flicker on the route 24 stop-and-go, and the replay still matches the van
step dec_calm python "$CHECKS/dec_calm.py" "$RLOGS"

# 6. submodule pins: does our tinygrad contain the pin comma's current master expects? (informational)
python "$CHECKS/pin_check.py" > "$LOG/pins.log" 2>&1; sed 's/^/        /' "$LOG/pins.log"
grep -q "^WARN" "$LOG/pins.log" && warn "submodule pins: see above"

# 7. release audit vs the published branch: params keys whose type changed (and their readers), commits with
#    no real author identity in openpilot or in the opendbc pin range
if [ -n "$TARGET" ] && git rev-parse -q --verify "origin/$TARGET" >/dev/null; then
  step release_audit python -I "$CHECKS/release_audit.py" "$ROOT" "origin/$TARGET"
  while read -r w; do warn "$w"; done < <(grep "^WARN" "$LOG/release_audit.log" | sed 's/^WARN //')
fi

# 8. release bump: a push to ody-next/ody-test should carry a new codename + release-date version
if [ -n "$TARGET" ] && git rev-parse -q --verify "origin/$TARGET" >/dev/null; then
  git diff --quiet "origin/$TARGET" HEAD -- BUILD_NAME && warn "BUILD_NAME unchanged vs origin/$TARGET (next codename? see NOTES)"
  git diff --quiet "origin/$TARGET" HEAD -- openpilot/sunnypilot/common/version.h && warn "version.h unchanged vs origin/$TARGET (should be today's date YYYY.MM.DD)"
  today=$(date +%Y.%m.%d); grep -q "\"$today" openpilot/sunnypilot/common/version.h || warn "version is not today's date ($today)"
fi

if [ $FULL = 1 ]; then
  step opendbc_suite tools/ody/opendbc_test.sh "$(git rev-parse --abbrev-ref HEAD)"
  step replay_ab tools/ody/replay_ab.sh
fi

echo
if [ ${#FAILS[@]} -gt 0 ]; then echo "PRE-PUSH: FAILED (${FAILS[*]})"; exit 1; fi
echo "PRE-PUSH: OK (${#WARNS[@]} warnings) in ${SECONDS}s"
