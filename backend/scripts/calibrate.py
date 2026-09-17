#!/usr/bin/env python3
"""Recalibrate the SEVERE_RATE constants against real Chess.com accounts.

Three stages: sample a large club and bucket its members by blitz rating, run
the real pipeline over the sample, then report each category's rate
distribution and the resulting constants.

    python scripts/calibrate.py sample     # -> calibration/candidates.json
    python scripts/calibrate.py sweep      # -> calibration/results.json
    python scripts/calibrate.py report     # prints the table to paste into config

Each constant is the 90th-percentile rate among players in the PRD's target
band, so "severe" means worse than roughly 9 in 10 comparable players. Expect
the sweep to take ~1 minute of engine time per player.
"""

import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import chesscom, config  # noqa: E402
from app.classify import (  # noqa: E402
    _player_moves,
    classify_conversion,
    classify_endgame,
    classify_tactical,
    classify_time_management,
)
from app.engine import evaluate_games_with_stockfish  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "calibration"
CLUB = "https://api.chess.com/pub/club/chess-com-developer-community/members"
BANDS = [(600, 899), (900, 1199), (1200, 1499), (1500, 1799), (1800, 2200)]
PER_BAND = 3
TARGET_BAND = (500, 1800)  # PRD section 5
ACTIVE_WITHIN_S = 180 * 24 * 3600
CONCURRENCY = 3
CATEGORIES = ("tactical", "endgame", "time_management", "conversion")


# --- stage 1: find players ---------------------------------------------------

def _band_of(rating):
    for lo, hi in BANDS:
        if lo <= rating <= hi:
            return f"{lo}-{hi}"
    return None


async def _blitz_stats(client, username, sem):
    async with sem:
        for _ in range(3):
            try:
                resp = await client.get(f"https://api.chess.com/pub/player/{username}/stats")
            except httpx.HTTPError:
                await asyncio.sleep(2)
                continue
            if resp.status_code == 429:
                await asyncio.sleep(5)
                continue
            if resp.status_code != 200:
                return None
            last = resp.json().get("chess_blitz", {}).get("last")
            return {"username": username, "rating": last["rating"], "date": last["date"]} if last else None
    return None


async def sample(max_checked=1500):
    async with httpx.AsyncClient(timeout=25.0, headers=config.CHESS_COM_HEADERS) as client:
        names = [m["username"] for m in (await client.get(CLUB)).json()["all_time"]]
        random.shuffle(names)

        sem = asyncio.Semaphore(5)
        found = {f"{lo}-{hi}": [] for lo, hi in BANDS}
        cutoff = time.time() - ACTIVE_WITHIN_S
        checked = 0

        for i in range(0, min(len(names), max_checked), 40):
            batch = names[i : i + 40]
            checked += len(batch)
            for res in await asyncio.gather(*[_blitz_stats(client, n, sem) for n in batch]):
                if not res or res["date"] < cutoff:
                    continue
                band = _band_of(res["rating"])
                if band and len(found[band]) < PER_BAND:
                    found[band].append(res)
                    print(f"  {band:10} {res['username']:24} {res['rating']}", flush=True)
            if all(len(v) >= PER_BAND for v in found.values()):
                break

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "candidates.json").write_text(json.dumps(found, indent=1))
    print(f"checked {checked} -> " + str({k: len(v) for k, v in found.items()}))


# --- stage 2: run the pipeline ----------------------------------------------

async def _analyze(entry, sem):
    user = entry["username"]
    async with sem:
        try:
            games = await chesscom.fetch_last_n_games(user, "blitz", n=config.MIN_GAMES_REQUIRED)
            if len(games) < config.MIN_GAMES_REQUIRED:
                print(f"  skip {user}: {len(games)} blitz games", flush=True)
                return None
            rows = await evaluate_games_with_stockfish(games, user)
        except Exception as exc:  # noqa: BLE001 — one bad account shouldn't end the sweep
            print(f"  FAIL {user}: {type(exc).__name__}: {exc}", flush=True)
            return None

    tactical, endgame = classify_tactical(rows), classify_endgame(rows)
    timing, conversion = classify_time_management(rows), classify_conversion(rows)

    def rate(category, opportunities):
        return round(category.instances / opportunities, 4) if opportunities else None

    result = {
        "username": user,
        "rating": entry["rating"],
        "meaningful_moves": len(_player_moves(rows)),
        "tactical": {"n": tactical.instances, "rate": rate(tactical, tactical.details["opportunities"])},
        "endgame": {"n": endgame.instances, "rate": rate(endgame, endgame.details["opportunities"])},
        "time_management": {
            "n": timing.instances,
            "rate": rate(timing, timing.details["low_bucket_moves"]),
            "gate": timing.details["gate_met"],
        },
        "conversion": {
            "n": conversion.instances,
            "rate": rate(conversion, conversion.details["games_reached_winning"]),
        },
    }
    print(f"  {user:24} {entry['rating']:5}  " +
          "  ".join(f"{c[:4]}={result[c]['rate']}" for c in CATEGORIES), flush=True)
    return result


async def sweep():
    candidates = json.loads((OUT_DIR / "candidates.json").read_text())
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [_analyze(e, sem) for entries in candidates.values() for e in entries]
    results = [r for r in await asyncio.gather(*tasks) if r]
    results.sort(key=lambda r: r["rating"])
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=1))
    print(f"\n{len(results)} players analyzed")


# --- stage 3: report ---------------------------------------------------------

def _percentile(values, q):
    values = sorted(values)
    return values[min(int(round(q * (len(values) - 1))), len(values) - 1)]


def report():
    rows = json.loads((OUT_DIR / "results.json").read_text())
    target = [r for r in rows if TARGET_BAND[0] <= r["rating"] <= TARGET_BAND[1]]
    print(f"{len(rows)} players, {len(target)} in the target band {TARGET_BAND}\n")
    print(f"{'category':17} {'median':>8} {'p90':>8} {'proposed':>9}   discrimination")

    for category in CATEGORIES:
        pool = target
        if category == "time_management":
            # The gate already excludes players this doesn't apply to.
            pool = [r for r in target if r[category]["gate"]]
        rates = [r[category]["rate"] for r in pool if r[category]["rate"] is not None]
        if not rates:
            continue
        low = [r[category]["rate"] for r in rows if r["rating"] < 1100 and r[category]["rate"] is not None]
        high = [r[category]["rate"] for r in rows if r["rating"] >= 1600 and r[category]["rate"] is not None]
        ratio = statistics.mean(low) / statistics.mean(high) if low and high else float("nan")
        print(f"{category:17} {statistics.median(rates):8.3f} {_percentile(rates, 0.9):8.3f} "
              f"{_percentile(rates, 0.9):9.2f}   {ratio:.2f}x (weak under 1.3x)")

    print("\nCurrent config.SEVERE_RATE:", config.SEVERE_RATE)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "report"
    if stage == "sample":
        asyncio.run(sample())
    elif stage == "sweep":
        asyncio.run(sweep())
    else:
        report()
