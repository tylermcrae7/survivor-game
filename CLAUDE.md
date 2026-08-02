# Survivor Game — working notes

## The live server does not run from this repo

The LaunchAgent runs the server from `~/srv/survivor-game`, a plain rsync'd
copy. It is not a checkout, has no git remote, and does not pull. macOS TCC
blocks launchd processes from `~/Documents`, and Python hangs forever opening
the venv there — hence the separate directory. It will not go away.

**A commit is not a deploy.** Pushing to GitHub changes nothing about what
players are running. This has already cost a round of bug reports that were
all one undeployed commit: the seat colours, the Inheritance card, and Sorry
For You's discard choice were reported as broken weeks after they were fixed.

### After any change to Python, `survivor_cards.json`, or the web client

```bash
bash deploy/redeploy.sh
```

Run it as part of finishing the work, not as a separate errand — the same way
you'd run the tests. It rsyncs the repo over `~/srv/survivor-game`, installs
requirements, and bounces the LaunchAgent. It never touches live runtime state
(`games.json`, `winners.json`, push keys, logs).

Bouncing drops live socket connections for a moment; players reconnect on
their own. If a game is mid-council and the timing matters, say so and ask
first. Otherwise just deploy.

Then confirm it actually took, rather than assuming:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/
```

`/api/game/<id>/state` answers `{"success": false, "gated": true}` without the
access code — that is the gate doing its job, not a broken server.

### Never edit `~/srv/survivor-game` directly

The next redeploy runs `rsync --delete` and the edit is gone. Change the repo
and redeploy.

## The iOS app deploys separately

Nothing in `deploy/redeploy.sh` touches iOS — it is excluded from the rsync.
Swift changes reach a phone only through a new TestFlight build. When a fix is
iOS-side, say so plainly, because deploying the server will not deliver it.

An app on a phone talks to whatever server it reaches, which may be older or
newer than the build. Client code has to survive both directions: decode what
it doesn't recognise, and never assume a field the server might not send yet.

## Migrations heal on load, they don't migrate

Saved games are healed when the store is read — `ensure_card_uids`,
`ensure_seat_bound_inheritance`, `seats.seat_of` deriving a seat from a stored
colour. Each is idempotent and mutates in place, keeping card uids intact.
Follow that pattern rather than writing a one-shot migration script: games are
in flight when a deploy lands, and the store on disk is not rewritten until
the next ordinary action persists it.

Before shipping one, dry-run it against a **copy** of the live store:

```bash
cp ~/srv/survivor-game/games.json /tmp/prod-games-copy.json
```

## Xcode project

`ios/project.yml` is the source of truth — run `xcodegen generate`. Never
hand-edit `project.pbxproj`.
