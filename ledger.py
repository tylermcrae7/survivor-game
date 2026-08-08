"""
The island's private ledger (Task D1).

``game["_ledger"]`` is server-side-only plumbing behind a leading
underscore — the same convention every other piece of server-only state in
this codebase uses (``_pending_alerts``, ``_responderIds``, ...).

**It persists to ``games.json`` by design — that is required, not a leak.**
A jury casts its vote hours, sometimes a full server restart, after the
councils it is voting on the memory of: who blindsided whom, who took whose
idol, who never lifted a finger. ``GameState._save`` dumps ``self.games``
verbatim, so the ledger simply rides along with every other piece of live
game state the way it already has to survive a restart. It is stripped from
``get_game_state`` (``survivor_server.py`` — the top-level ``_``-prefixed
key sweep that runs before any deep copy of a game ever leaves the process)
and so it never reaches a client, an HTTP response, or a socket event. **Do
not "fix" the persistence** by keeping the ledger out of ``games.json`` —
that would erase every juror's memory across every deploy.

Shape::

    game["_ledger"] = {
        "councilIndex": 3,   # how many tribal councils have been recorded
        "players": {
            pid: {
                "votesAgainst":  [{"council": 0, "voters": {voterId: n}}, ...],
                "votesCast":     [{"council": 0, "votes":  {targetId: n}}, ...],
                "stolenFrom":    {thiefId: count},   # cards taken FROM me BY them
                "stolenBy":      {victimId: count},  # cards I took FROM them
                "challengeWins": 0,
                "cardsPlayed":   0,
                "idolsPlayed":   0,
                "cardsPlayedOn": {playerId: count},  # cards played ON me, by whom
                "eliminatedAtCouncil": None,         # explicit — see below
            },
            ...
        },
    }

The council index is tracked here, in the ledger itself, and bumped once
per real vote reveal (``record_council_votes``) — not derived from
``gameHistory`` or any other structure — so "which council" is always
well-defined for both a vote record and an elimination record.

``eliminatedAtCouncil`` is set **explicitly**, at elimination time, by
``record_elimination`` — never inferred from ``votesAgainst``. The rock/tie
cascade in ``resolve_tribal_eliminations`` can eliminate a player who took
zero votes at that council (a Leader's tie-break pick, or the "no votes"
tier of the priority ladder), and D3's central jury question — "did you
vote for me at the council that ended me?" — would silently mis-answer if
this were derived from the vote data instead of stated plainly.

Every ``record_*`` / ``get_player_ledger`` call runs ``ensure_ledger``
itself, so a caller never has to remember to heal first. ``ensure_ledger``
is idempotent, mutates in place, and follows the same heal-on-load
convention as ``ensure_card_uids`` and friends (see CLAUDE.md): it never
raises, and a game that has never seen a ledger — or one left partial by an
old save — gets a fully-shaped, all-zero ledger instead of an error.
"""

import hashlib


def _fresh_player_entry():
    return {
        "votesAgainst": [],
        "votesCast": [],
        "stolenFrom": {},
        "stolenBy": {},
        "challengeWins": 0,
        "cardsPlayed": 0,
        "idolsPlayed": 0,
        "cardsPlayedOn": {},
        "eliminatedAtCouncil": None,
    }


def _heal_player_entry(entry):
    """Coerce a possibly-missing/partial/corrupt entry into the full shape,
    in place. Never raises — a wrong-typed field is simply replaced."""
    if not isinstance(entry, dict):
        return _fresh_player_entry()
    entry.setdefault("votesAgainst", [])
    entry.setdefault("votesCast", [])
    entry.setdefault("stolenFrom", {})
    entry.setdefault("stolenBy", {})
    entry.setdefault("challengeWins", 0)
    entry.setdefault("cardsPlayed", 0)
    entry.setdefault("idolsPlayed", 0)
    entry.setdefault("cardsPlayedOn", {})
    entry.setdefault("eliminatedAtCouncil", None)
    if not isinstance(entry["votesAgainst"], list):
        entry["votesAgainst"] = []
    if not isinstance(entry["votesCast"], list):
        entry["votesCast"] = []
    if not isinstance(entry["stolenFrom"], dict):
        entry["stolenFrom"] = {}
    if not isinstance(entry["stolenBy"], dict):
        entry["stolenBy"] = {}
    if not isinstance(entry["cardsPlayedOn"], dict):
        entry["cardsPlayedOn"] = {}
    if not isinstance(entry.get("challengeWins"), int):
        entry["challengeWins"] = 0
    if not isinstance(entry.get("cardsPlayed"), int):
        entry["cardsPlayed"] = 0
    if not isinstance(entry.get("idolsPlayed"), int):
        entry["idolsPlayed"] = 0
    if entry.get("eliminatedAtCouncil") is not None and not isinstance(entry["eliminatedAtCouncil"], int):
        entry["eliminatedAtCouncil"] = None
    return entry


def ensure_ledger(game):
    """Idempotent heal: create/repair ``game["_ledger"]`` in place.

    Safe on a brand-new game, an old save with no ledger at all, or a
    ledger left partial by an earlier crash. Every player currently seated
    in the game gets a healed entry; anything already recorded is left
    alone. Never raises, even if ``game`` isn't the shape expected.
    """
    if not isinstance(game, dict):
        return {"councilIndex": 0, "players": {}}
    ledger = game.get("_ledger")
    if not isinstance(ledger, dict):
        ledger = {}
        game["_ledger"] = ledger
    if not isinstance(ledger.get("councilIndex"), int) or ledger["councilIndex"] < 0:
        ledger["councilIndex"] = 0
    players = ledger.get("players")
    if not isinstance(players, dict):
        players = {}
        ledger["players"] = players
    for pid in (game.get("players") or {}):
        players[pid] = _heal_player_entry(players.get(pid))
    return ledger


def _entry(game, pid):
    """The healed ledger entry for one player, creating it if needed — even
    for a pid not (yet, or no longer) present in ``game["players"]``, so a
    write never has to happen in a particular order relative to roster
    changes."""
    ledger = ensure_ledger(game)
    entry = _heal_player_entry(ledger["players"].get(pid))
    ledger["players"][pid] = entry
    return entry


def get_player_ledger(game, pid):
    """Public read accessor for bots (D2/D3). Always returns the full
    shape, healing first — an empty/missing ledger reads as all-zero
    rather than raising, which is what lets bot scoring fall back to
    hand-size-only behaviour without a special case."""
    return _entry(game, pid)


# ───────────────────────────── write sites ──────────────────────────────

def record_steal(game, thief_id, victim_id, count):
    """Cards moved FROM victim_id TO thief_id. Called from
    ``rules_engine._record_steal_alert``, which already has exactly these
    three values every time cards actually move."""
    if not thief_id or not victim_id or not count or count <= 0:
        return
    thief = _entry(game, thief_id)
    victim = _entry(game, victim_id)
    thief["stolenBy"][victim_id] = thief["stolenBy"].get(victim_id, 0) + count
    victim["stolenFrom"][thief_id] = victim["stolenFrom"].get(thief_id, 0) + count


def record_council_votes(game, votes_by_voter):
    """The full ``{voterId: {targetId: count}}`` ballot box, as it stood
    before Block A Vote exclusion or idol/necklace protection ever touches
    it — the ledger remembers what a voter actually chose, not what the
    tally counted afterward.

    Bumps the ledger's own council-index counter by exactly one and returns
    the index this batch of ballots was filed under. Call this once per
    real reveal (the tally itself), not from the funnel's first tap that
    merely opens the idol window — ``survivor_server.reveal_votes`` only
    reaches the tally code path once per council.
    """
    ledger = ensure_ledger(game)
    council_idx = ledger["councilIndex"]
    ledger["councilIndex"] = council_idx + 1
    for voter_id, targets in (votes_by_voter or {}).items():
        if not voter_id or not isinstance(targets, dict) or not targets:
            continue
        voter = _entry(game, voter_id)
        voter["votesCast"].append({"council": council_idx, "votes": dict(targets)})
        for target_id, count in targets.items():
            if not target_id or not count:
                continue
            target = _entry(game, target_id)
            record = next((r for r in target["votesAgainst"]
                           if r.get("council") == council_idx), None)
            if record is None:
                record = {"council": council_idx, "voters": {}}
                target["votesAgainst"].append(record)
            record["voters"][voter_id] = record["voters"].get(voter_id, 0) + count
    return council_idx


def next_council_index(game):
    """The index the NEXT reveal will file its ballots under — "this
    council, in progress" from a voting bot's point of view. Used for the
    D2 tiebreak hash so it changes from council to council."""
    return ensure_ledger(game)["councilIndex"]


def last_council_index(game):
    """The most recently completed council. Used to stamp an elimination
    that follows immediately after a reveal within the same tribal
    council — safe because only one tribal council is ever in flight, so
    no second reveal can land between the two."""
    return max(0, ensure_ledger(game)["councilIndex"] - 1)


def record_challenge_win(game, winner_id):
    if not winner_id:
        return
    _entry(game, winner_id)["challengeWins"] += 1


def record_card_played(game, player_id, target_ids=None, is_idol=False):
    """A card played from ``player_id``'s hand. ``target_ids`` — a single
    id or an iterable of them — marks who it was played ON; a self-target
    (playing an idol on yourself, say) is not held against anyone and is
    silently skipped."""
    if not player_id:
        return
    entry = _entry(game, player_id)
    entry["cardsPlayed"] += 1
    if is_idol:
        entry["idolsPlayed"] += 1
    if not target_ids:
        return
    if isinstance(target_ids, str):
        target_ids = [target_ids]
    for target_id in target_ids:
        if not target_id or target_id == player_id:
            continue
        target = _entry(game, target_id)
        target["cardsPlayedOn"][player_id] = target["cardsPlayedOn"].get(player_id, 0) + 1


def record_elimination(game, player_id, council_index):
    """Explicit, never inferred — see the module docstring for why a
    rock-draw / tie-break elimination cannot be read back out of
    ``votesAgainst``."""
    if not player_id:
        return
    _entry(game, player_id)["eliminatedAtCouncil"] = council_index


# ─────────────── shared determinism helper (D2 jitter, D3 tiebreak) ───────────────

def tiebreak_score(gid, council_index, actor_id, candidate_id):
    """A deterministic value in [0, 1) from a stable hash of
    ``(gid, council_index, actor_id, candidate_id)``.

    Deliberately NOT the shared ``BotRunner`` rng — that rng is one
    instance shared by every bot in the game, unseeded per-bot, so drawing
    from it during scoring would make the outcome depend on the order bots
    happen to be evaluated in, which would silently defeat the
    "same inputs, same outputs" determinism this plan requires. A hash of
    the actual identity of the decision has no such dependency: the same
    bot facing the same candidate at the same council always gets the same
    jitter, regardless of what order bots act in or how many times the
    caller recomputes it.

    Callers scale this down before adding it to a real score — it exists to
    be decisive only among near-equal candidates (breaking the bloc), never
    to overrule an actual, meaningful difference between two candidates.
    """
    key = f"{gid}|{council_index}|{actor_id}|{candidate_id}".encode("utf-8")
    digest = hashlib.sha256(key).digest()
    n = int.from_bytes(digest[:4], "big")
    return n / 0xFFFFFFFF
