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
import threading

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
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f)
    logger.info("Generated new VAPID keys for turn notifications")
    return keys


def public_key():
    keys = get_keys()
    return keys["public"] if keys else None


def _subs():
    return _load_json(SUBS_FILE, {})


def _write_subs(subs):
    with open(SUBS_FILE, "w") as f:
        json.dump(subs, f)


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


def _webpush(subscription, payload, keys):      # test seam
    webpush(subscription_info=subscription, data=payload,
            vapid_private_key=keys["private"],
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
