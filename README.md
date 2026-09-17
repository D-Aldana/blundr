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
├── frontend/         (not yet scaffolded — React + Tailwind + Recharts per PRD)
└── docs/
    └── prd.md
```

## Status

Backend pipeline is complete and tested end to end: eligibility check,
Chess.com fetch (verified against the live API), Stockfish evaluation,
the four classifiers, recommendation mapping, and the LLM summary with its
hallucination guardrail. Frontend is not started.

Two paths have only been exercised against stubs, not the real thing — a
Stockfish binary and a configured Anthropic API key. See `docs/prd.md` §16.

## Backend: local dev setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

You also need a Stockfish binary on PATH:

```bash
brew install stockfish      # macOS
apt install stockfish       # Debian/Ubuntu
```

### Tests

```bash
cd backend && ./venv/bin/python -m pytest
```

The engine tests drive a stub UCI engine, so the suite runs without Stockfish
installed.

### Configuration

All optional — every value has a working default.

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

## API

Three endpoints, per PRD §14:

```bash
curl -X POST localhost:8000/eligibility -H 'content-type: application/json' \
  -d '{"username":"hikaru","time_control":"blitz"}'

curl -X POST localhost:8000/analyze -H 'content-type: application/json' \
  -d '{"username":"hikaru","time_control":"blitz"}'

curl localhost:8000/analyze/<job_id>
```
