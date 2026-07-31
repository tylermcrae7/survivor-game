# SurvivorGameUITests

End-to-end tests that drive the real app against a real island (server) —
no mocks. `AuthenticationUITests` covers the locked-island flow: a clean
launch shows the access gate, typing the code unlocks the start screen,
creating a game reaches the lobby with a connected socket, and the access
cookie survives an app relaunch.

## Running the suite

The tests expect a scratch server on `http://127.0.0.1:8099`. Start it
from the repo root:

```sh
SURVIVOR_ACCESS_CODE=torchtest2468 PORT=8099 .venv/bin/python survivor_server.py
```

The access code must be exactly `torchtest2468` because the test types it
into the gate's text field; any other code and the unlock step fails.

Then run the tests (from `ios/`):

```sh
xcodebuild test -project SurvivorGame.xcodeproj -scheme SurvivorGame \
    -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
    -only-testing:SurvivorGameUITests
```

## Production-strict mode (origin check)

Production runs with an exact-match `ALLOWED_ORIGINS` list, which rejects
websocket handshakes whose `Origin` header doesn't match the site origin
(the bug behind the perpetual "Reconnecting" banner: Starscream derives
`Origin: wss://…` unless the client sends one explicitly). To exercise
that path locally, start the scratch server origin-strict:

```sh
ALLOWED_ORIGINS=http://127.0.0.1:8099 SURVIVOR_ACCESS_CODE=torchtest2468 \
    PORT=8099 .venv/bin/python survivor_server.py
```

The suite's "Connected" assertion then fails unless the app sends the
correct explicit `Origin` header on the socket handshake. Prefer this
mode — it is what production enforces.

## No server? The suite skips itself

`setUpWithError` probes `http://127.0.0.1:8099/api/access/check` before
each test. If nothing answers, the test throws `XCTSkip` with the exact
command above — so the scheme's default test action stays green on a
clean checkout instead of failing on a missing server. A skip in the
test report therefore means "server wasn't running", not "flow is
healthy".
