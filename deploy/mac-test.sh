#!/bin/bash
# Survivor Game — the full test pass, run on the Mac mini.
#
# Testing does not run on GitHub. This is the one command that checks a
# branch end to end: lint, every Python suite, the live API and scripted-game
# harnesses against a scratch server, the browser UI checklist (when
# Playwright is installed) and the iOS unit tests (when Xcode is) — the one
# thing no Linux box can do.
#
#   bash deploy/mac-test.sh            # everything available
#   SKIP_IOS=1 bash deploy/mac-test.sh # skip the Xcode build
#
# It never touches the live server: the scratch server runs on its own port
# (8097) from a throwaway directory, so ~/srv's games.json is never read or
# written. Logs land in .test-logs/<timestamp>/; summary.txt in that folder is
# the result to post on the board.

set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
PY="$REPO_DIR/.venv/bin/python"
E2E_PORT=8097
LOG_DIR="$REPO_DIR/.test-logs/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$LOG_DIR"
SUMMARY="$LOG_DIR/summary.txt"
FAILED=0

{
    echo "Survivor test pass — $(date '+%Y-%m-%d %H:%M')"
    echo "Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null)  Commit: $(git rev-parse --short HEAD 2>/dev/null)"
    git diff --quiet HEAD -- 2>/dev/null || echo "NOTE: uncommitted changes in the working tree"
    echo
} > "$SUMMARY"

record() {   # record <PASS|FAIL|SKIP> <step> [detail]
    local line="$1  $2${3:+ — $3}"
    echo "$line" | tee -a "$SUMMARY"
    if [ "$1" = FAIL ]; then FAILED=1; fi
}

run_step() { # run_step <name> <command...>
    local name="$1"; shift
    echo "── $name"
    if "$@" > "$LOG_DIR/$name.log" 2>&1; then
        record PASS "$name" "$(tail -n 1 "$LOG_DIR/$name.log")"
    else
        record FAIL "$name" "see $LOG_DIR/$name.log"
    fi
}

# ── Python environment (the repo's own .venv; never the live one in ~/srv) ──
if [ ! -x "$PY" ]; then
    python3 -m venv "$REPO_DIR/.venv"
fi
if ! "$PY" -m pip install -q -r requirements.txt pytest ruff > "$LOG_DIR/pip.log" 2>&1; then
    record FAIL "install" "see $LOG_DIR/pip.log"
    exit 1
fi

run_step lint "$REPO_DIR/.venv/bin/ruff" check --select F,E9 \
    --exclude ios,companion,docs,tests "$REPO_DIR"
run_step python-suites "$PY" -m pytest

# ── Live harnesses against a scratch server ──
SCRATCH="$(mktemp -d)"
( cd "$SCRATCH" && PORT=$E2E_PORT SURVIVOR_TEST_HOOKS=1 \
    exec "$PY" "$REPO_DIR/survivor_server.py" ) > "$LOG_DIR/scratch-server.log" 2>&1 &
SERVER_PID=$!
up=""
for _ in $(seq 1 40); do
    if curl -fsS "http://127.0.0.1:$E2E_PORT/api/ping" > /dev/null 2>&1; then up=1; break; fi
    sleep 0.5
done
if [ -n "$up" ]; then
    export SURVIVOR_TEST_BASE="http://127.0.0.1:$E2E_PORT"
    run_step e2e-api "$PY" tests/e2e/e2e_api_live_test.py
    run_step e2e-scripted-games "$PY" tests/e2e/scripted_full_games.py
    unset SURVIVOR_TEST_BASE
    if grep -q Traceback "$LOG_DIR/scratch-server.log"; then
        record FAIL "scratch-server" "tracebacks in $LOG_DIR/scratch-server.log"
    fi
else
    record FAIL "scratch-server" "did not answer on :$E2E_PORT"
fi
kill "$SERVER_PID" 2>/dev/null
wait "$SERVER_PID" 2>/dev/null
rm -rf "$SCRATCH"

# ── Browser UI checklist (starts its own server on the same port) ──
if "$PY" -c "import playwright" 2>/dev/null; then
    run_step ui-checklist "$PY" tests/ui/test_ui_rules_checklist.py
else
    record SKIP "ui-checklist" "pip install playwright && .venv/bin/python -m playwright install chromium"
fi

# ── iOS unit tests ──
if [ -n "${SKIP_IOS:-}" ]; then
    record SKIP "ios-unit-tests" "SKIP_IOS set"
elif command -v xcodebuild > /dev/null 2>&1; then
    DEST="${IOS_DESTINATION:-}"
    if [ -z "$DEST" ]; then
        SIM_ID="$(xcrun simctl list devices available -j 2>/dev/null | python3 -c '
import json, sys
devices = json.load(sys.stdin).get("devices", {})
ios = [d for runtime, ds in sorted(devices.items(), reverse=True) if "iOS" in runtime for d in ds]
iphones = [d for d in ios if d.get("name", "").startswith("iPhone")]
print((iphones or ios or [{}])[0].get("udid", ""))' 2>/dev/null)"
        DEST="id=$SIM_ID"
    fi
    if [ "$DEST" = "id=" ]; then
        record FAIL "ios-unit-tests" "no iOS simulator available (set IOS_DESTINATION)"
    else
        run_step ios-unit-tests xcodebuild test \
            -project ios/SurvivorGame.xcodeproj -scheme SurvivorGame \
            -destination "$DEST" -only-testing:SurvivorGameTests -quiet
    fi
else
    record SKIP "ios-unit-tests" "xcodebuild not found"
fi

echo
if [ "$FAILED" = 0 ]; then
    echo "RESULT: PASS" | tee -a "$SUMMARY"
else
    echo "RESULT: FAIL" | tee -a "$SUMMARY"
fi
echo "Summary: $SUMMARY"
exit "$FAILED"
