# PRD: Blundr (v1)

**Name:** Blundr
**Owner:** [you]
**Status:** Draft v1
**Last updated:** 2026-09-17

---

## 1. Summary

A free, no-signup web tool that takes a Chess.com username and time control, analyzes the player's last 20 games with Stockfish, and produces a shareable "weakness report card" — a small set of chess-fundamentals scores (tactics, endgame technique, time management, conversion), the top 1-2 things to practice, and a short plain-language summary. Designed to be genuinely useful, fast to try, and attractive enough to share on LinkedIn/social.

## 2. Problem

Existing free tools (Chess.com's own review, Chessigma, etc.) analyze **one game at a time**: move grades, accuracy %, an eval graph. None of them answer the question a player actually wants answered after enough games: *"What is actually wrong with my chess, in fundamental terms, and what should I practice?"* That requires looking across many games, not one — and turning raw engine output into a diagnosis, not just a grade.

## 3. Goals

- Give a player a credible, data-backed answer to "what are my real weaknesses" — grounded in their own recent games, not generic advice.
- Make it trivially easy to try (username in, report out, no signup).
- Make the output attractive enough that someone would screenshot and share it.
- (Secondary/personal goal) Produce a concrete artifact demonstrating disciplined AI-boundary judgment: deterministic classification for anything factual, LLM only for narrative framing, with a validation guardrail against hallucinated claims.

## 4. Non-goals (v1)

- Not a move-by-move single-game analyzer (that space is well-served already).
- Not a "bot that plays like you" or sparring engine — later phase.
- No Lichess or PGN upload support — Chess.com API only for v1.
- No accounts, saved history, or rolling/incremental tracking — single on-demand report only.
- Not trying to cover all 8 possible fundamentals categories — 4 to start.

## 5. Target user

A club-level to intermediate online player (roughly 500-1800 Chess.com rating) who plays regularly enough to have 20+ recent games in at least one time control, and is curious/improvement-minded enough to want more than a single accuracy percentage.

## 6. Design principle: fun, and as few steps as possible

This is meant to feel like a fun thing a stranger tries in one sitting, not a tool they configure. Concretely:

- **One input, one button.** Username + time control, nothing else to fill in. No settings, no options to tune before seeing a result.
- **No dead ends.** If something's missing (not enough games, bad username), say so immediately and clearly rather than letting someone wait through processing to find out.
- **No required signup, ever, for the core flow.** Signup (if it exists at all) is only ever a later, optional add-on for someone who already got value.
- **The wait itself should feel like part of the fun**, not friction — light, specific progress messaging rather than a generic spinner.

## 7. Minimum games requirement

The report requires **at least 20 games in the selected time control** to run at all. This is a hard gate, checked immediately after fetching the player's game list — before running any engine analysis — so someone doesn't wait through a 30-second analysis only to be told their sample was too small.

- If the player has **fewer than 20 games** in the chosen time control: show a friendly, specific message immediately (e.g., "You've got 12 blitz games on record — come back after a few more, or try rapid/bullet if you've got more games there") rather than a generic error. Where possible, show counts for their other time controls so they can just pick one that qualifies, in one click, without leaving the page.
- If they have **zero games** in any time control (new/inactive account): a friendly "no games found yet" state.
- This replaces the earlier "graceful minimum-games fallback" idea from the risks section — v1 does **not** attempt to analyze on a smaller sample. Fixed threshold, checked upfront, no analysis run below it.

## 8. User flow

1. **Landing page.** Enter Chess.com username, select a time control (bullet/blitz/rapid). One button: "Analyze my last 20 games."
2. **Instant eligibility check.** Fetch the player's recent game counts per time control; if the selected one has fewer than 20 games, stop here and show the friendly message + alternative time controls (see Section 7). No engine analysis runs yet.
3. **Processing state.** Only once eligible: backend runs engine eval and classifies the last 20 games. Show a progress indicator with light personality (not a bare spinner) — this is a wait of maybe 15-45 seconds.
4. **Report page.** Displays:
   - Headline insight (one sentence, the single biggest leak)
   - Weakness scores across 4 categories (visual, e.g. radar or bar chart)
   - Top 1-2 practice recommendations, each tied to specific evidence from their games
   - A short LLM-written summary paragraph
   - A "share" affordance producing a clean, shareable image/card of the result
5. **Edge cases:** username not found, zero games at all — each needs a clear, friendly message (not a generic error). (Insufficient games in a time control is handled at step 2, not here.)

## 9. Fundamentals taxonomy (v1: 4 categories)

| Category | Definition | Detection signal |
|---|---|---|
| **Tactical awareness** | Missing forcing wins/losses (forks, pins, hanging pieces, back rank, etc.) | Centipawn loss above threshold where engine's best move was a forcing move (capture/check) |
| **Endgame technique** | Mistakes concentrated in low-piece-count positions | Centipawn loss above threshold where piece count ≤ endgame cutoff |
| **Time management** | Move quality degrades as clock runs low, independent of position complexity | Correlation between centipawn loss and clock time remaining, controlling for move number |
| **Conversion** | Losing/drawing games after reaching a clearly winning position | Eval trajectory after first crossing a "winning" threshold (e.g. ≥ +300), checking for later decline to equal/loss |

*(Positional understanding, opening prep, and defensive resilience are planned for v1.1 — cut from v1 to keep scope tight.)*

## 10. Data pipeline

1. **Fetch:** Chess.com public API → game count check per time control, then last 20 games for the selected time control (PGN format), once the minimum-games gate (Section 7) passes.
2. **Parse & evaluate:** python-chess steps through each game; Stockfish (depth ~12-14 for speed in v1) evaluates every position. Record per move: move number, phase/piece count, eval before/after (→ centipawn loss), clock time remaining (from PGN clock annotations), whether the best move was forcing or quiet, game result, color played.
3. **Flat dataset:** one row per move across all 20 games — single source of truth for everything downstream.
4. **Classification:** deterministic rules per category (see taxonomy table above) applied to the flat dataset.
5. **Sample-size guard:** a category only gets a reported score if it has ≥3 qualifying instances across the 20 games; otherwise it's shown as "insufficient data" rather than a shaky number.
6. **Recommendation mapping:** deterministic lookup from worst-scoring categories (by frequency × severity) to specific, evidence-backed practice suggestions (e.g., "you missed 4 knight forks in your last 20 games → practice knight-fork puzzles," not generic "do more tactics").
7. **LLM summary generation:** the LLM receives *only* the computed scores, counts, and recommendation text — never raw PGN or game text — and writes a short coaching paragraph.
8. **Output validation (guardrail):** validate that the LLM's summary only references categories/numbers actually provided; flag or strip any claim that introduces unsupported specificity (e.g., referencing an opening or motif never passed to it).

## 11. Success criteria for v1

- A stranger can go from "never heard of this" to "has a report" in under 2 minutes, no signup.
- Reports are self-evidently grounded (each recommendation visibly ties to a specific stat, not a platitude).
- At least one category is correctly suppressed/flagged when sample size is too low, verified with test accounts.
- The output validation guardrail catches at least one real hallucination case during testing (this is expected and useful, not a bug to be embarrassed by).

## 12. Risks / open questions

- **Depth vs. speed tradeoff:** lower Stockfish depth (12-14) is needed for a fast v1 experience, but may reduce classification precision — worth validating against a few known games where the "right" diagnosis is already known.
- **Drop-off at the eligibility gate:** requiring exactly 20 games in one time control will turn away casual players who don't meet it in any single mode. Mitigate by making that moment itself painless (show counts, one-click switch to a qualifying time control) rather than loosening the threshold.
- **Chess.com API rate limits / availability** — the endpoints, field names and 404 behaviour are confirmed against the live API (Section 16), and archive walking is bounded and cached to keep request volume low. Published rate limits are still unconfirmed; worth watching once there is real traffic.
- **Tone calibration:** balancing "fun/shareable" against "credible coaching tool" — leaning fun for the share hook while keeping the underlying classification rigorous.

## 13. Tech stack (v1)

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python + FastAPI | Async support fits the multi-step fetch → eval → classify → LLM flow |
| Chess engine | Stockfish binary + `python-chess` | `python-chess` handles PGN parsing, board state, and UCI communication with Stockfish |
| Job handling | In-process async background task, polled by job ID | No Celery/Redis needed for v1 — there's no persistence requirement (see Non-goals), so a single-instance in-memory job store is sufficient at hobby scale. Revisit only if traffic outgrows one server. |
| Database | None for v1 | No accounts, no history — nothing to persist between requests |
| Frontend | Vite + React + TypeScript + Tailwind | Small surface area (landing form, progress state, report view) — a heavier framework isn't needed, React mainly earns its keep on the report page's state handling. Recharts was in the original stack for a radar chart; see Section 17 for why the report uses eval bars instead |
| LLM | Claude API, called server-side only | Receives only computed scores/counts, never raw PGN; output passed through the validation guardrail (Section 10) before being returned |
| Shareable card | Design the report page to look good as a screenshot for v1 | Real server-side image generation (headless-browser render or programmatic image lib) deferred until there's evidence people want to share it |
| Local setup | Docker Compose, or a Makefile for native dev | `docker compose up` needs nothing installed but Docker — Stockfish, Python and Node all live in the images, which removes the engine binary as a setup step. `make setup && make dev` is the faster native loop |
| Hosting | Render, Starter tier (~$7/month) | Avoids the free tier's cold-start penalty (30-60s after 15 min idle), which would badly hurt first-impression UX for a "try this on LinkedIn" tool. Stockfish's CPU-bound workload also needs a real always-on instance, not serverless. |

**Explicitly avoided for v1:**
- **Railway** — no longer has an ongoing free tier (removed 2023, replaced with a one-time $5 trial credit); paid plans start at $5-20/month.
- **Serverless functions** for the backend — execution time limits and cold starts conflict with a 15-45 second CPU-bound Stockfish job.
- **Redis / Celery job queue** and **managed Postgres** — unnecessary given v1 has no persistence requirement; would add cost (Render's managed Postgres runs $7-95+/month, and its free Postgres tier expires after 90 days) and complexity with no corresponding v1 need. Add only if a future phase (accounts, history, rolling baseline) requires it.

## 14. API contract (v1)

Three endpoints: an eligibility check (fast, no engine analysis), a job kickoff, and a job-status poll. Splitting eligibility from analysis means the frontend never shows a progress bar unless a report is actually going to be produced — consistent with the "no dead ends" principle in Section 6.

**`POST /eligibility`**

Request:
```json
{ "username": "hikaru", "time_control": "blitz" }
```

Response (eligible):
```json
{ "eligible": true, "game_count": 47 }
```

Response (not eligible — offers one-click alternatives per Section 7):
```json
{
  "eligible": false,
  "game_count": 8,
  "alternatives": [
    { "time_control": "rapid", "game_count": 23 },
    { "time_control": "bullet", "game_count": 61 }
  ]
}
```

Response (user not found):
```json
{ "error": "user_not_found" }
```

**`POST /analyze`** (called only after eligibility passes)

Request:
```json
{ "username": "hikaru", "time_control": "blitz" }
```

Response:
```json
{ "job_id": "abc123" }
```

`/analyze` also refuses work rather than queueing it without bound (Section 16):

```json
{ "error": "invalid_username" }                      // 400
{ "error": "rate_limited", "retry_after_s": 1800 }   // 429, with Retry-After
{ "error": "busy" }                                  // 503, engine at capacity
```

**`GET /analyze/{job_id}`** (polled by the frontend during processing)

Response while running:
```json
{ "status": "running", "step": "evaluating_games", "progress": 0.6 }
```

A job waiting for an engine slot reports its place in line, so the wait stays
explicable rather than looking stalled:
```json
{ "status": "running", "step": "queued", "progress": 0.1, "queue_position": 2 }
```

Response when done:
```json
{ "status": "done", "report": { "...": "see report payload shape below" } }
```

Response on failure:
```json
{ "status": "failed", "error": "stockfish_timeout" }
```

**Report payload shape** (embedded in the `done` response above):
```json
{
  "headline": "Your biggest leak: converting winning positions",
  "categories": [
    { "name": "tactical", "score": 0.65, "confidence": "ok", "instances": 5 },
    { "name": "endgame", "score": 0.3, "confidence": "low", "instances": 2 },
    { "name": "time_management", "score": 0.8, "confidence": "ok", "instances": 9 },
    { "name": "conversion", "score": 0.4, "confidence": "ok", "instances": 4 }
  ],
  "recommendations": [
    { "category": "time_management", "text": "...", "evidence": "..." },
    { "category": "conversion", "text": "...", "evidence": "..." }
  ],
  "summary": "LLM-generated paragraph, grounded in the above",
  "games_analyzed": 20,
  "time_control": "blitz"
}
```

The `step` field in the polling response is intentionally a machine-readable key (not display text) so the frontend can map it to the "fun, specific" progress messaging described in Section 6, rather than showing a generic spinner.

## 15. Classifier thresholds (v1)

Concrete, deterministic rules behind the 4 category scores in Section 9. These are first-pass heuristics, not statistically rigorous models — expected to be refined once there's real data to look at (see "known simplification" note below).

**Tactical awareness**
- Trigger: centipawn loss ≥ 150 on a move where the engine's best move was a forcing move (capture, check, or a move creating an immediate material threat within 1 ply).
- Rationale: 150cp is roughly "lost a clean pawn or worse" — large enough to be a real miss rather than depth-12-14 engine noise.

**Endgame technique**
- Trigger: centipawn loss ≥ 100, in a position with ≤ 12 total pieces on the board (both sides, including kings and pawns).
- Rationale: lower threshold than tactics because endgame inaccuracies are often smaller-magnitude but still meaningful — e.g., drifting 80cp in a technically winning king-pawn endgame is a real technique gap, not noise.

**Time management**
- Not a per-move threshold — a correlation check. Bucket moves by clock time remaining as a percentage of starting time (e.g., >50%, 25-50%, 10-25%, <10%), compute average centipawn loss per bucket, and flag the category if average loss in the low-time bucket (<10-25%) is at least 1.5x the average loss in the high-time bucket (>50%), **and** there are ≥5 qualifying moves in the low-time bucket.
- Rationale: controls for "you just make more mistakes in general" — the flag specifically means time pressure amplifies the error rate, not just that mistakes exist.

**Conversion**
- Trigger: eval reaches ≥ +300 (from the player's perspective) at some point in the game, and later in the same game either drops below +100 or the game result is not a win.
- Counted once per game where this pattern occurs (not once per move).
- Rationale: +300 is a clear, unambiguous "winning" threshold — avoids counting marginal +150 edges as blown advantages.

**Sample-size guard (applies to all 4 categories, works alongside the 20-game minimum in Section 7):**
- Minimum 3 qualifying instances across the 20 games to report a score at all.
- 3-5 instances → `confidence: "low"`
- 6+ instances → `confidence: "ok"`
- Below 3 → `confidence: "insufficient"` — category omitted from the headline/recommendation logic but still shown in the UI as "not enough data yet," consistent with Section 5's guard.

**Category score formula (v1):**

```
score = min(1.0, (instances / opportunities) / severe_rate)
```

The score is a **rate**: how often a category fires, against how often it could have. Each category has its own opportunity set — the denominator is what the player could have got wrong, not a flat move count:

| Category | Opportunities |
|---|---|
| Tactical awareness | every meaningful move (see below) |
| Endgame technique | moves played with ≤ 12 pieces on the board |
| Time management | moves played under 25% of the clock |
| Conversion | winning positions reached |

`severe_rate` is the per-category rate at which the category counts as a severe problem. A player at that rate scores 1.0.

**Calibration (done).** The four constants were set by running the real pipeline over 15 Chess.com accounts sampled across the rating range (612 to 2127 blitz, three per 400-point band), plus super-GM anchors. Each constant is the **90th-percentile rate among players in the target band** (§5: 500-1800), so "severe" means *worse than roughly 9 in 10 comparable players* — which also gives the headline its meaning: your worst category is where you sit furthest out on the distribution for players like you.

| Category | Observed median | Observed p90 | `severe_rate` |
|---|---|---|---|
| Tactical | 0.060 | 0.105 | **0.11** |
| Endgame | 0.154 | 0.196 | **0.20** |
| Time management | 0.241 | 0.350 | **0.35** |
| Conversion | 0.422 | 0.600 | **0.60** |

Time management is measured over players who clear its ratio gate (9 of 15), since the gate already excludes the rest.

Validated at the top of the range — under the calibrated constants, two super-GM accounts land at the bottom of every distribution, where they belong:

| | tactical | endgame | time | conversion |
|---|---|---|---|---|
| Hikaru (3410) | 0.14 | 0.43 | 0.30 | 0.10 |
| Magnus (3300) | 0.15 | 0.56* | 0.00 | 0.09 |
| *club median* | *0.55* | *0.72* | *0.69* | *0.70* |

\* on a single instance, which the sample-size guard marks `insufficient` so it never reaches the headline. Under the old constants both accounts scored 1.0 on all four.

The sweep is reproducible: `python scripts/calibrate.py sample | sweep | report` re-runs it end to end and prints the proposed constants, with the anonymized sample from this run kept in `backend/calibration/results.json`.

The pre-calibration constants were all too strict by 2-4x — `endgame` at 0.10 sat *below the lowest rate any of the 15 players produced*, so every player scored 1.0 on it, including a world-championship-level blitz player.

**What the sweep says about each signal's discriminating power** — worth knowing before trusting any one category:

- **Tactical discriminates best.** Under-1100 players miss forcing shots at 1.76x the rate of 1600+ players (0.083 vs 0.047). This is the category the report can most defend.
- **Endgame discriminates weakly** (1.34x) and its distribution is tight (0.100-0.233 across the whole range), so no choice of constant spreads it well. The ≥100cp-in-≤12-pieces trigger fires for nearly everyone; the threshold, not the constant, is what needs revisiting.
- **Time management doesn't track rating at all** (0.91x — strong players flag as often as weak ones). That's consistent with the design: the ratio gate, not the rate, carries the signal, and time trouble isn't a beginner-specific failing.
- **Conversion discriminates mildly** (1.26x), on the smallest denominators (11-17 winning positions per player), so its scores are the noisiest.

One consequence to weigh in the UI: with p90 calibration a typical club player's scores land around 0.55-0.72, so an absolute-scale chart reads as "bad at everything". The ranking between categories is the meaningful part.

*Superseded:* v1 originally specified `score = sum(cpl) / (instances × severity_normalizer)`, which reduces to `avg_cpl / severity_normalizer` — frequency cancels out, so one 300cp miss scored the same as thirty. Worse, a move only becomes an instance once it's already past a centipawn threshold, so the average was always high and every category pinned to 1.0. Running a super-GM's 20 blitz games through it returned "severe" in three of four categories. Severity now earns its keep by deciding what qualifies as an instance; the score is about frequency.

**Two filters on what counts as a mistake at all**, both added after the first run against real games:

- **Playing the engine's own move costs nothing**, by definition. Comparing two separate depth-limited analyses of adjacent positions produces real centipawn swings even when the player found the best move — a 254cp "blunder" for playing the exact move the engine wanted. That noise is loudest in sharp positions, which is precisely where the classifiers look.
- **Already-decided positions don't count.** A move is only examined if there was something real to lose: the player wasn't already winning decisively and still winning (≥ +600 → still ≥ +300), and wasn't already lost (≤ -600). Without this, cleanly won games read as full of blunders. The filter lives in the shared move accessor, so it applies to the time-management buckets too — the flat dataset itself stays raw.

## 16. Backend implementation status

The full v1 backend pipeline is implemented behind the three endpoints from Section 14, with an in-memory job store (no Redis/db, consistent with Section 13):

`fetch_game_counts` → `fetch_last_n_games` → `evaluate_games_with_stockfish` → `classify_weaknesses` → `map_recommendations` → `generate_llm_summary` → `build_report`

Each stage lives in its own module under `backend/app/` (`chesscom`, `engine`, `classify`, `recommend`, `summary`, `report`), with thresholds and tunables in `config.py` and 109 tests in `backend/tests/`.

**Chess.com fetch — implemented and verified against the live API.** The v1 constraints are baked in:

- **No API key, but a descriptive User-Agent header is required** — Chess.com returns 403 without one. Set a real contact address via the `CHESS_COM_CONTACT` env var before deploying.
- **No "last N games" endpoint exists.** Games are exposed only as monthly archives (`/player/{username}/games/archives`), so "last 20 games in a time control" means walking archives backward and filtering on `time_class`. Both the eligibility check and the analysis fetch share `_iter_recent_games`.
- **Username-not-found detection**: a 404 on the archives endpoint distinguishes an unknown username from a real user with zero games.
- **Bounded walking**: counts are capped at 3x `MIN_GAMES_REQUIRED` per bucket and the walk stops after 12 monthly archives, so an active player's whole history is never pulled for an eligibility check. A 60-second cache means the `/analyze` call right after `/eligibility` doesn't re-walk the same archives.
- The earlier caveat about untested field names is resolved: archive URLs, `time_class`, `pgn`, `url` and the 404 behaviour were all confirmed against `api.chess.com` from a real environment.

**Engine stage.** Every position is analysed exactly once, at `ENGINE_DEPTH` (default 12). Evals are recorded from the analyzed player's perspective on *every* ply, so the eval before and after a move gives that move's centipawn loss directly, and the same numbers double as the eval trajectory the conversion check reads. Evals are clamped to ±1500cp before centipawn loss is computed, so a move played in an already-lost position can't register as a five-figure blunder. Finished positions are scored from the game result rather than sent to the engine. The whole stage is time-boxed (`ENGINE_TIMEOUT_S`, default 300s) and a wedged engine is killed rather than waited on — surfacing as the `stockfish_timeout` failure from Section 14.

**Implementation choices worth flagging against Section 15:**

- *Forcing move* (tactical trigger) is detected as: a capture, a check, a promotion, or a move that creates a *new* favourable attack on an opponent piece — one that's undefended, or defended but worth more than its cheapest attacker. That's the "immediate material threat within 1 ply" clause, approximated without a static exchange evaluator.
- *Time management* keeps the Section 15 ratio check as a **gate** rather than a score: the category scores 0 unless low-clock moves are at least 1.5x worse than unhurried ones, and when the gate is met the standard score formula is applied to the costly low-clock moves. A score of 0 with `confidence: ok` therefore means "we had the data, this isn't your problem" — which is different from, and more useful than, "insufficient".
- *Conversion* severity is the size of the eval collapse (peak minus the lowest eval after it) rather than a centipawn-loss sum, with a larger `severity_normalizer` (600) to match. A game that was lost from a winning position produces a large drop naturally, with no special case.
- The report payload carries one field beyond Section 14's shape: `summary_source` (`"llm"` or `"fallback"`), so guardrail catches and budget exhaustion are visible during testing per Section 11. It is not surfaced in the UI: both paths state the same computed facts, so which one wrote the paragraph is an implementation detail rather than something a reader needs disclosed.

**LLM summary + guardrail.** The model receives only computed scores, counts and the already-written recommendation text — never a PGN, move, opening or opponent. Its output is then validated two ways: every number in the summary must appear in the facts it was given, and a blocklist of specificity it has no basis for (opening names, tactical motifs, ratings, opponents) is rejected unless the term appeared in the facts. A rejected summary is retried once with the violations fed back, then replaced by a deterministic paragraph. If no API key is configured the pipeline falls back silently rather than failing the job.

Two deliberate allowances in the number check, both found by running real summaries through it:

- A 0-1 score restated as a percentage passes, since that's a restatement rather than a new claim.
- Numbers are also matched **spelled out** ("in seven spots" was a real model output that digit matching alone waved through), but only from *four* upward. "One", "two" and "three" read as ordinary prose far more often than as claims — "do those two things", "one of those" — and validating them would reject good summaries.

**Verified end to end.** The earlier caveat — engine stage tested only against a stub UCI engine, LLM call only against a stubbed client — is resolved. The pipeline has since run against a real Stockfish 17.1 binary and a live Anthropic key, both natively and inside the Docker image: 20 blitz games in roughly 70 seconds, returning `summary_source: "llm"`. The stub-driven tests remain, so the suite still runs without Stockfish installed.

**Abuse limits.** The service has no accounts to throttle, spends real CPU and real API credit per request, and fetches from Chess.com on a shared IP — so every limit is keyed on the caller's IP or on a global ceiling, and all of it is in-process state (correct for the single instance of Section 13; it silently becomes per-instance if scaled out).

- **Engine concurrency is capped** at `MAX_CONCURRENT_ANALYSES` (default 1) by a semaphore held across the engine stage only. Without it every request spawned its own Stockfish, so a single caller in a loop could exhaust the CPU of the Starter instance for free. Past the cap jobs queue and report `queue_position`; past `MAX_QUEUED_ANALYSES` the endpoint returns 503 rather than accepting work that would starve.
- **Per-IP sliding windows** on both endpoints, in separate buckets so spending the analysis quota doesn't lock someone out of the cheap eligibility check. `X-Forwarded-For` is honoured only when `TRUST_PROXY_HEADER` says a proxy that overwrites it is actually in front — trusting it otherwise would let a caller forge an IP per request and defeat every limit here.
- **Usernames are validated** against `^[A-Za-z0-9_-]{3,25}$` at both the API boundary and the fetch layer. The username is interpolated into the Chess.com request path, where `../` escaped `/pub/player/` and `?` or `#` truncated the path — so an unvalidated caller chose which endpoint we hit. Contained to `api.chess.com` (the base URL is fixed and redirects are not followed), but closed regardless; it also keeps junk out of the counts cache, which is now evicted by TTL rather than growing per distinct username.
- **A rolling daily ceiling on paid LLM calls** (`SUMMARY_DAILY_BUDGET`), counted per call including guardrail retries. Past it the summary degrades to the deterministic paragraph that already exists for the no-API-key case, so the job still returns a report.

Not covered here, and worth doing before any real traffic: distributed abuse needs something in front of the app (Cloudflare's free tier over Render would handle IP and bot rules better than anything in-process), and Chess.com's own rate limits still want backoff handling — being banned there stops the product entirely.

## 17. Frontend implementation status

Built to the Section 8 flow as three views behind a single state machine (`frontend/src/App.tsx`), with a typed client for the Section 14 endpoints in `api.ts` and the step, error and category vocabulary in `copy.ts`.

- **Eligibility gates analysis, as designed.** `/eligibility` runs first and a shortfall never starts a job, so the progress bar only ever appears when a report is actually coming. The alternative time controls come back as buttons that re-submit immediately — the "one click, without leaving the page" requirement in Section 7.
- **The `step` key earns its keep.** Each machine key from Section 14 maps to its own line ("Separating the blunders from the bad luck"), which is what that field was made a key for rather than display text.
- **The sample-size guard is visible in the UI.** A category returning `confidence: "insufficient"` renders an empty track reading "too few to judge" rather than a bar, so a score the sample can't support is never drawn. Ranking mirrors `recommend.rank_categories`, so the highlighted bar always agrees with the headline.

**Deviation from Section 13 — no radar chart.** Four axes make a diamond that is hard to read and easy to misjudge, and the four categories are independent rates rather than a shape worth comparing. The report uses horizontal eval bars instead: more legible at n=4, and the native idiom for a chess evaluation. Recharts is still a dependency, unused, if the radar is wanted later.

**Share affordance** is Section 13's v1 answer — the report page is designed to screenshot cleanly — plus a "Copy result" button that puts the headline and summary on the clipboard. No server-side image generation, as deferred there.

`VITE_API_BASE` points the client at the backend (default `http://localhost:8000`); the backend's `ALLOWED_ORIGINS` already permits the Vite dev origin.

**Not yet verified:** nobody has looked at the rendered page in a browser. The build and typecheck are clean and the report shape is confirmed against real API responses field for field, but the visual layout has had no review.

## 18. Future phases (not v1)

- Rolling/persisted baseline + trend view (recent 20 vs. longer-term).
- Lichess + PGN upload support.
- Expanded taxonomy (positional, opening, defense).
- "Plays like you" / weakness-targeted sparring bot (built on top of the same classification engine).
- Accounts + history tracking over time.
