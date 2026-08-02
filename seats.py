"""
Seats — the six colours a castaway can be.

The printed game ships 12 Survivor Character Cards, 2 of each of 6 colours
(docs/survivor_rules.md:20), and 6 Inheritance Cards, "1 OF EACH COLOR". So
colour is not decoration: it is a fixed, enumerable identity, and every
Inheritance Card is bound to exactly one of six seats.

**Derive, then trust what's stored.** A player record written from now on
carries both the seat key and the seat's hex. A record written before seats
existed carries only a hex, so `seat_of` falls back to an exact hex lookup —
which is enough to place 361 of the 391 players already in games.json. Anything
it cannot place returns None, and everything downstream treats a seatless
player as exactly what they are: someone with a colour and no seat.

**No migration, deliberately.** Mapping old colours onto the nearest seat was
measured against the live store and produces *duplicate seats in 13 of 117
games* — sage (#96CEB4) and teal (#4ECDC4) sit at the same table and both land
on teal. Two players, one seat, one Inheritance card. A mechanic that decides
who inherits a dead player's hand cannot rest on a heuristic that is visibly
wrong one game in nine. Exact matching can never do that, because colours are
already unique within a game.
"""

SEATS = (
    {"key": "red",    "label": "Red",    "hex": "#FF6B6B"},
    {"key": "teal",   "label": "Teal",   "hex": "#4ECDC4"},
    {"key": "blue",   "label": "Blue",   "hex": "#45B7D1"},
    {"key": "orange", "label": "Orange", "hex": "#F9844A"},
    {"key": "green",  "label": "Green",  "hex": "#90BE6D"},
    {"key": "yellow", "label": "Yellow", "hex": "#F9C74F"},
)

SEAT_KEYS = tuple(s["key"] for s in SEATS)
SEAT_HEX = {s["key"]: s["hex"] for s in SEATS}
SEAT_LABELS = {s["key"]: s["label"] for s in SEATS}

_BY_HEX = {s["hex"].upper(): s["key"] for s in SEATS}

# Append-only. Every off-roster value a client has ever sent, and the seat it
# means. Never remove an entry: an installed phone keeps sending the old value
# long after the server stops offering it, and losing your place at the fire
# over a colour is a punishment out of all proportion.
_ALIASES = {
    "#96CEB4": "green",   # the clients' sage
    "#98D8C8": "teal",
    "#FFEAA7": "yellow",
    "#F7DC6F": "yellow",
    "#DDA0DD": "red",     # plum; nothing closer is free in spirit
    "RED": "red", "TEAL": "teal", "BLUE": "blue",
    "ORANGE": "orange", "GREEN": "green", "YELLOW": "yellow",
}


def roster():
    """The six seats, for a client that needs to draw the picker."""
    return [dict(seat) for seat in SEATS]


def seat_of(player):
    """This player's seat key, or None.

    Exact only — never fuzzy, never nearest-colour. Within-game colours are
    unique, so exact matching cannot produce two players on one seat, and that
    invariant is the whole reason Inheritance can bind to a colour at all.
    """
    if not isinstance(player, dict):
        return None
    stored = player.get("seat")
    if isinstance(stored, str) and stored in SEAT_HEX:
        return stored
    colour = player.get("color")
    if isinstance(colour, str):
        return _BY_HEX.get(colour.strip().upper())
    return None


def seat_hex(key):
    """The canonical hex for a seat key."""
    return SEAT_HEX.get(key)


def taken_seats(game):
    """{seat key: player id} for everyone currently seated."""
    out = {}
    for pid, player in ((game or {}).get("players") or {}).items():
        key = seat_of(player)
        if key:
            out[key] = pid
    return out


def free_seats(game):
    """Seat keys nobody holds, in table order."""
    taken = taken_seats(game)
    return [key for key in SEAT_KEYS if key not in taken]


def resolve_request(value):
    """Turn whatever a client asked for into (seat key or None, was_explicit).

    `was_explicit` means "they named a seat we understood" — a seat key, a seat
    hex, or a known alias. Those get a hard error when the seat is taken, so two
    people both reaching for Red are told rather than silently re-seated.
    Anything we cannot place is not a request at all; it falls through to
    auto-assign.
    """
    if not isinstance(value, str):
        return None, False
    text = value.strip()
    if not text:
        return None, False
    if text in SEAT_HEX:                       # a seat key
        return text, True
    upper = text.upper()
    if upper in _BY_HEX:                       # a seat's own hex
        return _BY_HEX[upper], True
    if upper in _ALIASES:                      # something we once offered
        return _ALIASES[upper], True
    return None, False


def assign(game, requested=None):
    """Choose this player's seat. Returns (key, error message or None).

    Never fails for a reason the player can do anything about: there are six
    seats and at most six players, so a free seat always exists for anyone
    allowed through the door.
    """
    key, explicit = resolve_request(requested)
    taken = taken_seats(game)

    if key and key not in taken:
        return key, None
    if key and explicit:
        holder = (game.get("players") or {}).get(taken[key], {}).get("name", "someone")
        return None, f"That colour is already taken by {holder}."

    free = free_seats(game)
    if not free:
        return None, "Every seat at this fire is taken."
    return free[0], None
