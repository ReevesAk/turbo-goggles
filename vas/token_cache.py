from django.core.cache import cache

# Prepaid electricity tokens are single-use and meter-scoped. We keep a
# copy only long enough to field "I lost the SMS" support requests, then
# let Redis drop it - no DB column, no cleanup cron. SMS/email remain the
# source of truth; a cache miss here is expected, not an error.
ELECTRICITY_TOKEN_TTL = 60 * 60 * 24 * 90  # 90 days


def _key(tx_reference):
    return f"vas:electricity_token:{tx_reference}"


def cache_electricity_token(tx_reference, token, units=None):
    """Stash a freshly bought electricity token against its tx_reference.

    No-op when either value is missing (e.g. the settlement-lag path, where
    the shared topup-status response carries no token). The default cache
    TIMEOUT is 5 min, so the TTL is passed explicitly.
    """
    if not tx_reference or not token:
        return
    cache.set(
        _key(tx_reference),
        {"token": token, "units": units or ""},
        ELECTRICITY_TOKEN_TTL,
    )


def get_electricity_token(tx_reference):
    """Return (token, units) for a tx_reference, or (None, None) once the
    cache entry has expired / was never written / Redis is unreachable."""
    data = cache.get(_key(tx_reference)) or {}
    return data.get("token"), data.get("units")


def get_electricity_tokens(tx_references):
    """Batch variant of get_electricity_token for a transaction-history page:
    {tx_reference: token} for the refs that still have a live cache entry
    (others are simply absent). One Redis round-trip via get_many."""
    keymap = {_key(r): r for r in tx_references if r}
    if not keymap:
        return {}
    found = cache.get_many(list(keymap)) or {}
    return {
        keymap[k]: v["token"]
        for k, v in found.items()
        if isinstance(v, dict) and v.get("token")
    }
