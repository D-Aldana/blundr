"""Chess.com Published-Data API fetch stage.

Chess.com exposes games only as monthly archives — there is no "last N games"
endpoint — so both the eligibility count and the analysis fetch walk the same
archive list backwards through `_iter_recent_games`.
"""

import time
from typing import AsyncIterator, Optional

import httpx

from . import config

# Short-lived cache so the /analyze call right after /eligibility doesn't
# re-walk the same archives.
_counts_cache: dict[str, tuple[float, Optional[dict]]] = {}


def _cache_counts(key: str, result: Optional[dict]) -> None:
    """Evict expired entries before inserting, so cycling usernames can't grow
    the cache without bound."""
    now = time.monotonic()
    for k in [k for k, (t, _) in _counts_cache.items() if now - t >= config.GAME_COUNT_CACHE_TTL]:
        del _counts_cache[k]
    _counts_cache[key] = (now, result)


def require_valid_username(username: str) -> str:
    """Guard the fetch entry points, not just the API boundary — the username
    is interpolated into the request path, where "../" or "?" would otherwise
    let a caller pick which Chess.com endpoint we hit."""
    if not config.USERNAME_PATTERN.match(username):
        raise ValueError("invalid_username")
    return username.lower()


async def _fetch_archive_urls(client: httpx.AsyncClient, username: str) -> Optional[list[str]]:
    """Monthly archive URLs, oldest first. A 404 here is how an unknown
    username is distinguished from a real user with zero games."""
    resp = await client.get(
        f"{config.CHESS_COM_BASE}/player/{require_valid_username(username)}/games/archives",
        headers=config.CHESS_COM_HEADERS,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("archives", [])


async def _iter_recent_games(
    client: httpx.AsyncClient,
    username: str,
    archive_urls: Optional[list[str]] = None,
) -> AsyncIterator[dict]:
    """Yield games newest-first, walking at most MAX_ARCHIVE_MONTHS archives.
    Callers that already hold the archive list pass it in rather than
    re-requesting it."""
    if archive_urls is None:
        archive_urls = await _fetch_archive_urls(client, username)
    if not archive_urls:
        return

    for url in list(reversed(archive_urls))[: config.MAX_ARCHIVE_MONTHS]:
        resp = await client.get(url, headers=config.CHESS_COM_HEADERS)
        resp.raise_for_status()
        games = resp.json().get("games", [])
        # Chess.com returns each month oldest-first; reverse for newest-first.
        for game in reversed(games):
            yield game


async def fetch_game_counts(username: str) -> Optional[dict]:
    """Per-time-control game counts, or None if the username doesn't exist.

    Counts are capped per bucket and the archive walk is bounded by months —
    this answers "do they clear the 20-game bar", not "how many have they
    played in their life".
    """
    key = require_valid_username(username)

    cached = _counts_cache.get(key)
    if cached and time.monotonic() - cached[0] < config.GAME_COUNT_CACHE_TTL:
        return cached[1]

    counts = {tc: 0 for tc in config.TIME_CONTROLS}
    cap = config.ELIGIBILITY_COUNT_CAP
    result: Optional[dict] = counts

    async with httpx.AsyncClient(timeout=10.0) as client:
        archive_urls = await _fetch_archive_urls(client, username)
        if archive_urls is None:
            result = None
        else:
            async for game in _iter_recent_games(client, username, archive_urls):
                tc = game.get("time_class")
                if tc in counts and counts[tc] < cap:
                    counts[tc] += 1
                if all(c >= cap for c in counts.values()):
                    break

    _cache_counts(key, result)
    return result


async def fetch_last_n_games(username: str, time_control: str, n: int) -> list[dict]:
    """The most recent n games in a time control, newest first.

    Each item carries the PGN plus the Chess.com game url, which the report
    uses as a stable per-game id. Assumes eligibility was already checked.
    """
    if time_control not in config.VALID_TIME_CLASSES:
        raise ValueError(f"unsupported time_control: {time_control}")
    require_valid_username(username)

    matched: list[dict] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        async for game in _iter_recent_games(client, username):
            if game.get("time_class") == time_control and game.get("pgn"):
                matched.append({"pgn": game["pgn"], "url": game.get("url", "")})
                if len(matched) >= n:
                    break

    return matched
