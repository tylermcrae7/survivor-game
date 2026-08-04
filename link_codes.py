"""
One-time codes for linking a Discord account to a phone.

Voice mirroring needs to know which Discord user a player is, and until now the
only way to say so was to type an 18-digit snowflake into Settings — the app
literally warns you it is "usually 18" digits, which is the sort of hint that
only exists because the field is hostile.

Instead: the phone asks for a code, shows something you can read aloud, and you
run ``/link PALM-472`` in Discord. The interaction tells the bot who ran it, so
nobody types an ID and nothing is matched on a username — those change, and
display names were never unique to begin with.

**The code binds to the phone, not to a player.** The app stores
``discordUserId`` in its own ServerConfig and sends it on every join and
reconnect, so a link that attached to a player would have to be redone every
game and could not be done from Settings at all. Binding to the device means
the join path does not change: this feature only fills in a field that already
exists.

Codes live in memory. They last minutes, and persisting them would mean a new
file for `redeploy.sh` to exclude — `rsync --delete` eats anything the repo
does not have. A deploy invalidates outstanding codes; you ask for another.
"""

import secrets
import time

# Read aloud across a room and typed into Discord by someone no longer looking
# at their phone. Whole words rather than character soup, so "O" and "I" cannot
# be heard as 0 and 1 — that risk lives entirely in the three digits, which are
# spoken as a number. Island vocabulary because it costs nothing to be in
# keeping.
WORDS = (
    "PALM", "TORCH", "REEF", "SAND", "MANGO", "VINE", "COVE", "DRIFT",
    "FLINT", "GULL", "HUT", "JUNGLE", "KELP", "LAGOON", "NEST", "OAR",
    "QUARRY", "RAFT", "SHELL", "TIDE", "URCHIN", "WAVE", "CANOE", "EMBER",
)

CODE_TTL_SECONDS = 600.0        # ten minutes: long enough to find Discord
CLAIM_TTL_SECONDS = 120.0       # the phone has this long to collect a claim
MAX_OUTSTANDING = 200           # a ceiling, so minting cannot exhaust memory

# Someone in the server guessing at codes goes through the bot, so the budget
# is per Discord account rather than per IP.
_CLAIM_ATTEMPT_LIMIT = 6
_CLAIM_ATTEMPT_WINDOW = 300.0


class LinkCodes:
    """The outstanding codes. One instance; not safe across processes."""

    def __init__(self, ttl=CODE_TTL_SECONDS, claim_ttl=CLAIM_TTL_SECONDS):
        self._codes = {}          # code -> {created, discordUserId, claimedAt}
        self._attempts = {}       # discord user id -> [timestamps]
        self._ttl = ttl
        self._claim_ttl = claim_ttl

    # ── minting ───────────────────────────────────────────────────────────

    def mint(self, now=None):
        """A fresh unclaimed code, or None if far too many are outstanding."""
        now = time.time() if now is None else now
        self._sweep(now)
        if len(self._codes) >= MAX_OUTSTANDING:
            return None
        for _ in range(50):
            code = f"{secrets.choice(WORDS)}-{secrets.randbelow(900) + 100}"
            if code not in self._codes:
                self._codes[code] = {"created": now, "discordUserId": None,
                                     "claimedAt": None}
                return code
        return None      # 24×900 combinations and 50 misses: effectively never

    # ── the bot's side ────────────────────────────────────────────────────

    def claim(self, code, discord_user_id, now=None):
        """Bind a Discord account to a pending code.

        Returns ``(ok, message)``. The message is shown to whoever ran
        ``/link``, so it says what to do rather than what went wrong
        internally, and it never reveals whether a code exists but has already
        been used — that would turn a wrong guess into a probe.
        """
        now = time.time() if now is None else now
        self._sweep(now)

        if not isinstance(discord_user_id, str) or not discord_user_id.isdigit():
            return False, "That Discord account could not be identified."
        if self._claim_rate_limited(discord_user_id, now):
            return False, "Too many tries. Wait a few minutes and ask the app for a new code."

        entry = self._codes.get(self._normalise(code))
        if entry is None or entry["discordUserId"] is not None:
            # Only wrong guesses cost budget. Someone linking a second phone
            # should not be throttled for having linked a first one.
            self._record_failure(discord_user_id, now)
            return False, "That code is not valid — ask the app for a fresh one."

        entry["discordUserId"] = discord_user_id
        entry["claimedAt"] = now
        return True, "Linked. Your torch and your voice are the same person now."

    # ── the phone's side ──────────────────────────────────────────────────

    def status(self, code, now=None):
        """``{"claimed": bool, "discordUserId": str|None}``, or None if gone.

        A collected claim is spent: the phone has the id, and leaving the code
        alive would let a second device poll for the same answer.
        """
        now = time.time() if now is None else now
        self._sweep(now)
        key = self._normalise(code)
        entry = self._codes.get(key)
        if entry is None:
            return None
        if entry["discordUserId"] is None:
            return {"claimed": False, "discordUserId": None}
        del self._codes[key]
        return {"claimed": True, "discordUserId": entry["discordUserId"]}

    def cancel(self, code):
        """Drop a code the phone is no longer waiting on."""
        return self._codes.pop(self._normalise(code), None) is not None

    # ── housekeeping ──────────────────────────────────────────────────────

    @staticmethod
    def _normalise(code):
        """Accept what a person typed: spacing, case, a missing hyphen."""
        if not isinstance(code, str):
            return ""
        clean = "".join(code.split()).upper().replace("—", "-").replace("–", "-")
        if "-" not in clean and len(clean) > 3 and clean[-3:].isdigit():
            clean = f"{clean[:-3]}-{clean[-3:]}"
        return clean

    def _sweep(self, now):
        for code, entry in list(self._codes.items()):
            expired = now - entry["created"] > self._ttl
            # A claim nobody collected is worse than an unclaimed code: it is
            # an answer sitting in memory for a phone that has walked away.
            stale_claim = (entry["claimedAt"] is not None
                           and now - entry["claimedAt"] > self._claim_ttl)
            if expired or stale_claim:
                del self._codes[code]

    def _claim_rate_limited(self, discord_user_id, now):
        tries = [t for t in self._attempts.get(discord_user_id, [])
                 if now - t < _CLAIM_ATTEMPT_WINDOW]
        self._attempts[discord_user_id] = tries
        return len(tries) >= _CLAIM_ATTEMPT_LIMIT

    def _record_failure(self, discord_user_id, now):
        self._attempts.setdefault(discord_user_id, []).append(now)
        if len(self._attempts) > 5000:
            self._attempts.clear()
