import httpx
import pytest

from app import chesscom, config

ARCHIVES = "https://api.chess.com/pub/player/testplayer/games/archives"
JAN = "https://api.chess.com/pub/player/testplayer/games/2026/01"
FEB = "https://api.chess.com/pub/player/testplayer/games/2026/02"


def game(time_class, tag):
    return {"time_class": time_class, "pgn": f"pgn-{tag}", "url": f"url-{tag}"}


@pytest.fixture(autouse=True)
def clear_cache():
    chesscom._counts_cache.clear()
    yield
    chesscom._counts_cache.clear()


@pytest.fixture
def mock_api(monkeypatch):
    def install(routes, on_request=None):
        def handler(request: httpx.Request) -> httpx.Response:
            if on_request:
                on_request(request)
            url = str(request.url)
            if url not in routes:
                return httpx.Response(404)
            return httpx.Response(200, json=routes[url])

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient
        monkeypatch.setattr(
            chesscom.httpx,
            "AsyncClient",
            lambda **kwargs: real_client(transport=transport, **kwargs),
        )

    return install


async def test_unknown_username_returns_none(mock_api):
    mock_api({})
    assert await chesscom.fetch_game_counts("testplayer") is None


async def test_user_with_no_games_is_not_a_missing_user(mock_api):
    mock_api({ARCHIVES: {"archives": []}})
    assert await chesscom.fetch_game_counts("testplayer") == {
        "bullet": 0,
        "blitz": 0,
        "rapid": 0,
    }


async def test_counts_are_bucketed_by_time_class(mock_api):
    mock_api(
        {
            ARCHIVES: {"archives": [JAN, FEB]},
            JAN: {"games": [game("blitz", i) for i in range(5)]},
            FEB: {
                "games": [game("blitz", i) for i in range(3)]
                + [game("rapid", i) for i in range(2)]
                + [game("daily", i) for i in range(4)]
            },
        }
    )
    counts = await chesscom.fetch_game_counts("testplayer")
    assert counts == {"bullet": 0, "blitz": 8, "rapid": 2}


async def test_counts_stop_once_every_bucket_hits_the_cap(mock_api):
    fetched = []
    big_month = {"games": [game(tc, i) for tc in config.TIME_CONTROLS for i in range(70)]}
    mock_api(
        {ARCHIVES: {"archives": [JAN, FEB]}, JAN: big_month, FEB: big_month},
        on_request=lambda r: fetched.append(str(r.url)),
    )
    counts = await chesscom.fetch_game_counts("testplayer")

    assert all(c == config.ELIGIBILITY_COUNT_CAP for c in counts.values())
    assert JAN not in fetched  # the older month was never requested


async def test_counts_are_cached_between_calls(mock_api):
    fetched = []
    mock_api(
        {ARCHIVES: {"archives": [FEB]}, FEB: {"games": [game("blitz", 1)]}},
        on_request=lambda r: fetched.append(str(r.url)),
    )
    first = await chesscom.fetch_game_counts("TestPlayer")
    second = await chesscom.fetch_game_counts("testplayer")

    assert first == second
    assert fetched.count(ARCHIVES) == 1


async def test_archive_walk_is_bounded_by_months(mock_api, monkeypatch):
    months = [f"https://api.chess.com/pub/player/testplayer/games/2026/{i:02d}" for i in range(1, 13)]
    routes = {ARCHIVES: {"archives": months}}
    routes.update({m: {"games": []} for m in months})
    fetched = []
    mock_api(routes, on_request=lambda r: fetched.append(str(r.url)))
    monkeypatch.setattr(config, "MAX_ARCHIVE_MONTHS", 3)

    await chesscom.fetch_game_counts("testplayer")
    assert len([u for u in fetched if u != ARCHIVES]) == 3


async def test_last_n_games_are_newest_first_and_filtered(mock_api):
    mock_api(
        {
            ARCHIVES: {"archives": [JAN, FEB]},
            JAN: {"games": [game("blitz", "jan1"), game("blitz", "jan2")]},
            FEB: {"games": [game("rapid", "feb1"), game("blitz", "feb2")]},
        }
    )
    games = await chesscom.fetch_last_n_games("testplayer", "blitz", n=3)

    assert [g["url"] for g in games] == ["url-feb2", "url-jan2", "url-jan1"]
    assert games[0]["pgn"] == "pgn-feb2"


async def test_last_n_games_stops_at_n(mock_api):
    mock_api(
        {
            ARCHIVES: {"archives": [FEB]},
            FEB: {"games": [game("blitz", i) for i in range(10)]},
        }
    )
    assert len(await chesscom.fetch_last_n_games("testplayer", "blitz", n=4)) == 4


async def test_unsupported_time_control_is_rejected():
    with pytest.raises(ValueError):
        await chesscom.fetch_last_n_games("testplayer", "daily", n=5)
