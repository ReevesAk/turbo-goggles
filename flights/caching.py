import hashlib
import json

from django.core.cache import cache

# Booking always re-confirms pricing/availability live via Revalidate, so a
# short cache window on Search results doesn't risk stale bookings and helps
# stay under FlightsLogic's daily search rate limit (FLERSEA027).
SEARCH_CACHE_TTL = 600

SEARCH_CACHE_FIELDS = (
    "journey_type",
    "origin_destination_info",
    "adults",
    "childs",
    "infants",
    "cabin_class",
    "required_currency",
)


def _search_cache_key(data):
    payload = {field: data[field] for field in SEARCH_CACHE_FIELDS}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return f"flight_search:{digest}"


def get_cached_search(data):
    return cache.get(_search_cache_key(data))


def set_cached_search(data, response):
    cache.set(_search_cache_key(data), response, SEARCH_CACHE_TTL)
