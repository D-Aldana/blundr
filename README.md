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
├── backend/         FastAPI app: eligibility check, analysis pipeline, API
│   ├── app/
│   │   └── main.py
│   └── requirements.txt
├── frontend/         (not yet scaffolded — React + Tailwind + Recharts per PRD)
└── docs/
    └── prd.md
```

## Status

Early scaffold. Backend has working eligibility/analysis endpoints and a
real Chess.com API fetch stage; Stockfish evaluation, classification,
recommendation mapping, and the LLM summary stage are still stubs. See
`docs/prd.md` Section 16 for current implementation status and known caveats
(the Chess.com fetch code has not yet been tested against the live API from
this environment — verify before relying on it).

## Backend: local dev setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

You'll also need a Stockfish binary installed and on PATH once the
evaluation stage is filled in (`apt install stockfish` / `brew install
stockfish`).
