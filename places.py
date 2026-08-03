"""
Places — where every castaway is standing on the island.

Five named places exist. During normal play the camp is open and people drift
between the Camp Fire, the Beach and the Water Well, which is where alliances
get made. When the tribe is called to Tribal Council everybody is standing in
the same spot whether they like it or not — except during the council's
discussion, which is exactly when the scheming happens, so camp reopens for it
and shuts again when the ballot starts. A snuffed torch goes to Exile Island
and stays there until the Final Tribal Council reunites everyone. In the lobby
(or once a season is over) there is only the Camp Fire.

**Derive, don't hook.** A player record stores only the place a player *chose*
(``placeChoice``). The place they are actually standing in is derived from the
game's phase every time it is asked for:

    effective = policy.forced  if the phase forces everyone together
              = the chosen place, if that place is open this phase
              = the first open place, otherwise

So the moment ``game["phase"]`` changes — anywhere, by any of the ~9 lines that
assign it — everyone is already in the right place, with no transition hooks to
forget. A player who wandered off to the Beach reads as being at Tribal Council
the instant the torches are lit, and drifts back to the Beach when camp reopens.

A Discord bot mirrors these places onto voice channels by polling
``GET /api/voice/plan/<gameId>`` and acting only when ``version`` changes, but
nothing here depends on the bot existing: the clients render places from the
game state alone.
"""

import hashlib
import json
import re

# The island, in display order. Keys are the stable wire contract; labels are
# what humans (and Discord channels) see.
PLACES = (
    {"key": "camp_fire", "label": "Camp Fire"},
    {"key": "the_beach", "label": "The Beach"},
    {"key": "the_water_well", "label": "The Water Well"},
    {"key": "tribal_council", "label": "Tribal Council"},
    {"key": "exile_island", "label": "Exile Island"},
)

PLACE_KEYS = tuple(p["key"] for p in PLACES)
PLACE_LABELS = {p["key"]: p["label"] for p in PLACES}

# Where you can be when camp is open...
CAMP_PLACES = ("camp_fire", "the_beach", "the_water_well")
# ...and where you start, and end up whenever there is nowhere else to be.
DEFAULT_PLACE = "camp_fire"

# Where a snuffed torch goes. The point of it is that they can still talk to
# each other: watching the rest of a season in silence is nobody's idea of a
# night in. They stay there until the Final Tribal Council, where the jury and
# the finalists are in one room again.
EXILE_PLACE = "exile_island"
EXILE_PHASES = ("playing", "tribal_council")

# phase -> (open places, forced place or None). A forced place overrides every
# stored choice; an open list without a forced place lets people move.
_PHASE_POLICY = {
    "lobby":          (("camp_fire",),      "camp_fire"),
    "playing":        (CAMP_PLACES,          None),
    "tribal_council": (("tribal_council",), "tribal_council"),
    "final_tribal":   (("tribal_council",), "tribal_council"),
    "finished":       (("camp_fire",),      "camp_fire"),
}

# Tribal Council is not one room for its whole length. Discussion is when the
# scheming actually happens — the tribe breaks up, pairs wander off, and then
# everyone is called back to vote. So camp reopens for that one sub-phase and
# shuts again the moment the ballot starts.
#
# These are `currentVote["phase"]` values, not `game["phase"]`: the game phase
# stays "tribal_council" for the whole ceremony.
TALK_SUBPHASES = ("discussion",)

# The Final Tribal Council is deliberately absent. Its deliberation is the jury
# questioning two finalists to their faces, which is the ceremony rather than an
# interlude in it.

# Unknown or missing phase: the safe answer is "everyone's at the fire". This
# also covers the legacy "final" phase and any phase added later — a new phase
# never leaves a player standing somewhere invalid.
_FALLBACK_POLICY = (("camp_fire",), "camp_fire")

# Discord snowflakes are decimal ids. Real ones are 17-19 digits today; the
# range below is loose enough to survive Discord's clock without accepting junk.
_DISCORD_ID_RE = re.compile(r'^[0-9]{15,25}$')


def place_policy(game, player=None):
    """
    What the current phase allows: ``{"open": [...], "forced": key|None}``.

    ``forced`` set means nobody may move — everyone reads as standing there.
    ``open`` is never empty, so ``open[0]`` is always a usable fallback.

    Pass ``player`` for that player's own policy. Without one you get the
    table's, which is what the Discord bot locks channels by and what an older
    client reads. The two differ only for a snuffed player: they go to Exile
    Island and stay there, so wherever the living may wander — and during the
    council's discussion they may wander far — the dead are somewhere else.
    """
    game = game or {}
    phase = game.get("phase")
    open_places, forced = _PHASE_POLICY.get(phase, _FALLBACK_POLICY)

    if phase == "tribal_council":
        subphase = (game.get("currentVote") or {}).get("phase")
        if subphase in TALK_SUBPHASES:
            open_places, forced = CAMP_PLACES, None

    # Out of the game is out of the rooms. Exile lasts from the snuffing until
    # the Final Tribal Council — `final_tribal` and `finished` are deliberately
    # not exile phases, because that is the reunion.
    if (player or {}).get("isEliminated") and phase in EXILE_PHASES:
        open_places, forced = (EXILE_PLACE,), EXILE_PLACE

    return {"open": list(open_places), "forced": forced}


def _effective(policy, player):
    """effective_place() with the policy already computed (one hash per call)."""
    if policy["forced"]:
        return policy["forced"]
    chosen = (player or {}).get("placeChoice")
    if isinstance(chosen, str) and chosen in policy["open"]:
        return chosen
    return policy["open"][0]


def effective_place(game, player):
    """
    Where ``player`` is actually standing right now — always a valid place key.

    Derived, never stored: the phase gets the final say over the player's choice.
    """
    return _effective(place_policy(game, player), player)


def voice_plan(game):
    """
    The Discord bot's whole view of a game: who is standing where, plus a
    content hash so it can poll cheaply and act only when something changed.

    Every place appears, empty ones included, so the bot can clear a channel it
    no longer needs. Computer players are left out entirely — a bot has no
    Discord presence to move. Players are listed in roster order.

    ``policy`` is the *table's*, which is what the bot locks channels by. A
    snuffed player is narrower than that — Exile Island, alone — so each entry
    carries ``eliminated`` and the bot bars them from the living's rooms
    individually. Moving them to Exile is not enough on its own: nothing stops
    a ghost walking back into The Beach in Discord, and the plan version only
    moves when the *game* changes, so no later poll would notice.
    """
    game = game or {}
    policy = place_policy(game)

    buckets = {key: [] for key in PLACE_KEYS}
    for pid, player in (game.get("players") or {}).items():
        if player.get("isBot"):
            continue
        mine = place_policy(game, player)
        buckets[_effective(mine, player)].append({
            "playerId": pid,
            "name": player.get("name"),
            "discordUserId": player.get("discordUserId"),
            "eliminated": bool(player.get("isEliminated")),
        })

    places = [{"key": key, "label": PLACE_LABELS[key], "players": buckets[key]}
              for key in PLACE_KEYS]

    return {
        "gameId": game.get("id"),
        "phase": game.get("phase"),
        "version": plan_version(policy, places),
        "policy": policy,
        "places": places,
    }


def plan_version(policy, places):
    """
    A 12-char content hash of the plan's meaningful half.

    Only ``policy`` and ``places`` feed it: gameId never changes and phase is
    already implied by the policy, so the version moves exactly when the thing
    the bot has to act on moves.
    """
    payload = json.dumps({"policy": policy, "places": places},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def validate_discord_user_id(value):
    """
    Normalize an optional Discord user id off the wire.

    Returns ``(value_or_None, error_message_or_None)``. Absent, null and empty
    all mean "not linked" and are accepted. Anything present must be a *string*
    of digits: a JSON number would already have lost precision in a JavaScript
    client (snowflakes exceed 2^53), so those are refused loudly rather than
    stored wrong.
    """
    if value is None:
        return None, None
    if isinstance(value, str) and not value.strip():
        return None, None
    if not isinstance(value, str):
        return None, ("discordUserId must be a string of digits "
                      "(quote it — the number is too big for JSON numbers).")
    clean = value.strip()
    if not _DISCORD_ID_RE.match(clean):
        return None, "That doesn't look like a Discord user ID."
    return clean, None
