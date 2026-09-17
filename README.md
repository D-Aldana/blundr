# Chess Weakness Analyzer

Free, no-signup tool that takes a Chess.com username, analyzes the last 20
games in a time control with Stockfish, and produces a shareable report card
of chess fundamentals weaknesses (tactics, endgame technique, time
management, conversion) with specific, evidence-backed practice
recommendations.

See [`docs/prd.md`](docs/prd.md) for the full product spec — problem, scope,
taxonomy, pipeline, tech stack, API contract, and classifier thresholds.

## Structure

```
.
├── backend/          FastAPI app: eligibility check, analysis pipeline, API
│   ├── app/
│   │   ├── main.py       endpoints + in-memory job store
│   │   ├── config.py     thresholds and tunables (PRD §15)
│   │   ├── chesscom.py   Chess.com archive fetch
│   │   ├── engine.py     Stockfish evaluation -> flat per-move dataset
│   │   ├── classify.py   deterministic weakness classifiers
│   │   ├── recommend.py  worst categories -> evidence-backed advice
│   │   ├── summary.py    LLM summary + output-validation guardrail
│   │   └── report.py     final report payload
│   └── tests/
├── frontend/         Vite + React + TS + Tailwind
│   └── src/
│       ├── api.ts        typed client for the three endpoints
│       ├── copy.ts       step/error keys -> display text
│       └── components/   Scoresheet (form), Analyzing, Report
├── docs/
│   └── prd.md
├── docker-compose.yml   both services, no local toolchain needed
└── Makefile             native setup and dev loop
```

## Status

Frontend covers the full v1 flow: landing form, eligibility gate with
one-click alternative time controls, polled progress, and the report view.
Backend pipeline is complete and tested end to end: eligibility check,
Chess.com fetch (verified against the live API), Stockfish evaluation,
the four classifiers, recommendation mapping, and the LLM summary with its
hallucination guardrail.

Verified end to end against a real Stockfish binary and a live Anthropic key:
20 blitz games in about 70 seconds, `summary_source: "llm"`.

## Running it

### With Docker — nothing to install

Stockfish, Python and Node all live in the images, so Docker is the only
prerequisite.

```bash
git clone https://github.com/D-Aldana/chess-weakness-analyzer.git
cd chess-weakness-analyzer
docker compose up
```

Open http://localhost:5173. Both services hot-reload from your working tree.

An Anthropic key is optional — without one the summary falls back to a
deterministic paragraph. To add it: `cp .env.example .env` and fill it in
before starting.

### Natively — faster to develop against

```bash
make setup    # checks your toolchain, then installs everything
make dev      # both servers in one terminal; ctrl-c stops both
```

`make setup` needs Python 3.10+, Node 20+ and Stockfish, and tells you exactly
what to install for anything missing. `make` on its own lists every target.

### Tests

```bash
make test
```

The engine tests drive a stub UCI engine, so the suite runs without Stockfish
installed.

### Configuration

Copy `.env.example` to `.env` at the repo root and fill in what you need —
it's loaded automatically at startup and is gitignored. A real environment
variable always wins over the file.

All values are optional — every one has a working default.

| Variable | Default | Notes |
|---|---|---|
| `STOCKFISH_PATH` | `stockfish` | Path to the engine binary |
| `ENGINE_DEPTH` | `12` | Lower is faster, less precise (PRD §12) |
| `ENGINE_THREADS` / `ENGINE_HASH_MB` | `2` / `128` | Engine resources |
| `ENGINE_TIMEOUT_S` | `300` | Whole-stage cap; a wedged engine fails the job |
| `CHESS_COM_CONTACT` | `you@example.com` | **Set before deploying** — Chess.com requires a real contact in the User-Agent |
| `ANTHROPIC_API_KEY` | unset | Without it the summary falls back to a deterministic paragraph |
| `SUMMARY_MODEL` | `claude-opus-5` | |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated CORS origins |

## Recalibrating the weakness scores

Category scores are rates measured against per-category constants in
`config.SEVERE_RATE`, set from real accounts across the rating range. To
re-derive them:

```bash
python scripts/calibrate.py sample    # bucket club members by blitz rating
python scripts/calibrate.py sweep     # run the pipeline over the sample (~1 min/player)
python scripts/calibrate.py report    # rate distributions + proposed constants
```

The anonymized sample behind the current constants is in `calibration/`.
See `docs/prd.md` §15 for what the numbers mean and which categories
discriminate well.

## API

Three endpoints, per PRD §14:

```bash
curl -X POST localhost:8000/eligibility -H 'content-type: application/json' \
  -d '{"username":"hikaru","time_control":"blitz"}'

curl -X POST localhost:8000/analyze -H 'content-type: application/json' \
  -d '{"username":"hikaru","time_control":"blitz"}'

curl localhost:8000/analyze/<job_id>
```
