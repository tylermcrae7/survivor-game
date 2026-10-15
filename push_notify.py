"""
Web Push for turn/tribal notifications.

Keys and subscriptions are RUNTIME state (like games.json): auto-generated,
stored beside the server, excluded from git and from redeploy's rsync.
Subscriptions must never ride inside game state — every client receives the
full game state, and a push endpoint is a private capability URL.

The whole module degrades to a quiet no-op when pywebpush isn't installed,
so the game never depends on the push stack being healthy.
"""
import json
import logging
import os
import threading
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

try:
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid02, b64urlencode
    AVAILABLE = True
except ImportError:            # dependency not installed — feature stays dark
    AVAILABLE = False

    class WebPushException(Exception):
        """Placeholder so callers/tests can reference the name either way."""

KEYS_FILE = "push_keys.json"
SUBS_FILE = "push_subs.json"
_lock = threading.Lock()

# A subscription's endpoint is a URL the server will POST to on every turn.
# Accepting any URL let a phone point the Mac at its own LAN (SSRF), so only
# the browsers' real push services are reachable.
PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com", "android.googleapis.com",      # Chrome / Android
    "push.apple.com",                                     # Safari, iOS home-screen apps
    "push.services.mozilla.com",                          # Firefox
    "notify.windows.com",                                 # Edge
)
MAX_SUBSCRIPTION_BYTES = 2048


def _atomic_write_json(path, data):
    """Write-then-rename, so a crash mid-write never leaves a torn file — a
    torn push_keys.json used to mint new VAPID keys and silently break every
    existing subscription."""
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def allowed_endpoint(endpoint):
    """True for an https URL on one of the real push services."""
    try:
        url = urlparse(endpoint)
    except (TypeError, ValueError):
        return False
    host = (url.hostname or "").lower()
    return url.scheme == "https" and any(
        host == suffix or host.endswith("." + suffix) for suffix in PUSH_HOST_SUFFIXES)


def clean_subscription(sub):
    """The parts of a PushSubscription the server needs, or None if unusable.

    Only `endpoint` and `keys` are kept (a client could otherwise park
    arbitrary data in push_subs.json), and the whole thing is size-capped.
    """
    if not isinstance(sub, dict):
        return None
    endpoint = sub.get("endpoint")
    keys = sub.get("keys")
    if not isinstance(endpoint, str) or not allowed_endpoint(endpoint):
        return None
    if not isinstance(keys, dict) or not all(
            isinstance(keys.get(k), str) and keys.get(k) for k in ("p256dh", "auth")):
        return None
    cleaned = {"endpoint": endpoint, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}
    if len(json.dumps(cleaned)) > MAX_SUBSCRIPTION_BYTES:
        return None
    return cleaned


def _load_json(path, fallback):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return fallback


def get_keys():
    """VAPID keypair, auto-generated on first use and persisted."""
    if not AVAILABLE:
        return None
    keys = _load_json(KEYS_FILE, None)
    if keys and keys.get("private") and keys.get("public"):
        return keys
    from cryptography.hazmat.primitives import serialization
    vapid = Vapid02()
    vapid.generate_keys()
    private = vapid.private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    keys = {"private": private, "public": b64urlencode(raw)}
    _atomic_write_json(KEYS_FILE, keys)
    logger.info("Generated new VAPID keys for turn notifications")
    return keys


def public_key():
    keys = get_keys()
    return keys["public"] if keys else None


def _subs():
    return _load_json(SUBS_FILE, {})


def _write_subs(subs):
    _atomic_write_json(SUBS_FILE, subs)


def subscribe(gid, player_id, subscription):
    with _lock:
        subs = _subs()
        subs[f"{gid}:{player_id}"] = subscription
        _write_subs(subs)


def unsubscribe(gid, player_id):
    with _lock:
        subs = _subs()
        if subs.pop(f"{gid}:{player_id}", None) is not None:
            _write_subs(subs)


def prune(live_game_ids):
    """Forget subscriptions for games that no longer exist (the collector
    calls this; nothing removed them before, so the file only ever grew)."""
    live = set(live_game_ids)
    with _lock:
        subs = _subs()
        kept = {k: v for k, v in subs.items() if k.split(":", 1)[0] in live}
        if len(kept) != len(subs):
            _write_subs(kept)
        return len(subs) - len(kept)


def _vapid_key(private):
    """What pywebpush can sign with.

    get_keys() stores the private key as PEM, but pywebpush only parses a
    raw/DER base64 *string* — handed the PEM, every send raised "Could not
    deserialize key data", notify_player logged a warning, and no turn
    notification was ever delivered. A Vapid object is accepted as-is.
    """
    if isinstance(private, str) and private.lstrip().startswith("-----BEGIN"):
        return Vapid02.from_pem(private.encode())
    return private


def _webpush(subscription, payload, keys):      # test seam
    if not allowed_endpoint(subscription.get("endpoint")):
        # A subscription stored before endpoints were checked
        raise ValueError("push endpoint is not a known push service")
    webpush(subscription_info=subscription, data=payload,
            vapid_private_key=_vapid_key(keys["private"]),
            vapid_claims={"sub": "mailto:tylermcrae7@gmail.com"},
            timeout=4)


def _send_async(fn):                            # test seam (tests run inline)
    threading.Thread(target=fn, daemon=True).start()


def notify_player(gid, player_id, title, body):
    """Fire-and-forget; a dead subscription unsubscribes itself."""
    if not AVAILABLE:
        return
    sub = _subs().get(f"{gid}:{player_id}")
    if not sub:
        return
    keys = get_keys()
    if not keys:
        return

    def _send():
        try:
            _webpush(sub, json.dumps({"title": title, "body": body}), keys)
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                unsubscribe(gid, player_id)    # endpoint expired
            else:
                logger.warning(f"Push to {gid}:{player_id} failed: {e}")
        except Exception as e:
            logger.warning(f"Push to {gid}:{player_id} failed: {e}")

    _send_async(_send)
