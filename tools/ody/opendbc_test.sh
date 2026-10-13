#!/usr/bin/env bash
# Run opendbc's full suite (lint, safety C tests, MISRA, car tests incl. test_odyssey_port.py) on a branch of
# prehkopf/opendbc, in a standalone Linux clone. Needs the compiled safety library, so Linux/WSL only.
# usage: opendbc_test.sh [branch] [dir]     defaults: ody-next ~/opendbc
set -e
BRANCH=${1:-ody-next}
DIR=${2:-$HOME/opendbc}
SHIM="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/opendbc_shim"
export PATH="$HOME/.local/bin:$PATH"
[ -d "$DIR" ] || git clone https://github.com/prehkopf/opendbc.git "$DIR"
cd "$DIR"
git fetch -q origin "$BRANCH" && git checkout -q -f -B "$BRANCH" "origin/$BRANCH"
source ./setup.sh
echo "$SHIM" > "$(ls -d .venv/lib/python3*/site-packages)/op_shim.pth"
git log --oneline -1
./test.sh > "$DIR/test.log" 2>&1 && echo "test.sh OK" || echo "test.sh FAILED, see $DIR/test.log"
grep -E "^Ran|^FAILED|^OK|All good|passed|failed" "$DIR/test.log" | tail -8
