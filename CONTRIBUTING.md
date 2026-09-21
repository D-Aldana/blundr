# Contributing

Thanks for looking. Blundr is a small project with a narrow purpose: take a
Chess.com username, analyze 20 games, and hand back an honest report card.
Contributions that sharpen that are very welcome. Contributions that widen it
are worth an issue first — see [Scope](#scope).

No contributor agreement, no checklist to sign. Open an issue, or just send a
pull request.

## Getting set up

The README covers [running it](README.md#running-it) — `docker compose up`
needs nothing installed, `make setup && make dev` is faster to develop
against. `make` on its own lists every target.

You don't need an API key. Without one the summary falls back to a
deterministic paragraph, and every other part of the report is unaffected.
You don't need Stockfish either unless you're touching the engine stage — the
tests drive a stub UCI binary.

## What has to pass

The same three commands CI runs:

```bash
make test                      # backend pytest
cd frontend && npm run lint    # oxlint
cd frontend && npm run build   # tsc -b && vite build — this is the type check
```

New behavior wants a test. The suite is fast and hermetic: nothing in it
reaches Chess.com, a real engine, or an LLM, and it should stay that way —
`backend/tests/conftest.py` has the fixtures for faking all three.

## Where things live

```
backend/app/
  main.py         endpoints, job store, concurrency and rate limits
  config.py       every threshold and tunable, read from the environment
  chesscom.py     archive fetch
  engine.py       Stockfish -> a flat per-move dataset
  classify.py     that dataset -> four category scores
  recommend.py    worst categories -> evidence-backed advice
  summary.py      LLM closing paragraph + the validator that checks it
  providers/      anthropic / openai / ollama behind one interface
  report.py       the payload the frontend renders

frontend/src/
  api.ts          typed client for the three endpoints
  copy.ts         step and error keys -> display text
  components/     Scoresheet (form), Analyzing, Report
```

The rule the pipeline is built around: **the LLM never sees a move.** It gets
your computed scores and writes prose about them, and a validator checks that
prose back against the numbers. Everything that decides what a weakness *is*
stays deterministic, in `classify.py` and `recommend.py`. Changes that blur
that line are the ones most likely to get pushback.

## Good places to start

- **Another LLM provider.** One module in `backend/app/providers/` exporting
  `DEFAULT_MODEL`, `is_configured()` and an async `complete(system, user,
  model)`. `ollama.py` is the shortest example. Register it in `PROVIDERS`.
- **Copy.** The report's wording does a lot of work, and plenty of it can be
  said better. `frontend/src/copy.ts` and `backend/app/recommend.py`.
- **Calibration.** Category scores are rates measured against constants in
  `config.SEVERE_RATE`, derived from a sample of real accounts. More data
  across more of the rating range makes them better — see
  [Recalibrating](README.md#recalibrating-the-weakness-scores).
- **Classifier thresholds.** PRD §15 documents what each number means and
  which categories discriminate well. Some discriminate poorly; that's an
  open problem, not a settled design.

If you hit something confusing while running it, that's worth an issue on its
own. Confusing is a bug here.

## Scope

[`docs/prd.md`](docs/prd.md) is the spec — problem, taxonomy, pipeline, API
contract, thresholds. Two sections say what's deliberately out: §4 non-goals
and §18 future phases. Something in §18 isn't unwelcome, it's just a bigger
conversation than a pull request — open an issue and let's talk about it
first.

Accounts, history, storing anything about a user: no. The tool asks for a
username and forgets it.

## Style

Match the code already there. A few things that aren't obvious from reading
it:

- Comments explain *why*, where the why isn't evident. Don't restate the
  code, don't comment every section, and leave it out when it adds nothing.
- Backend dependencies are pinned, so a fresh clone resolves what the project
  was built against. Keep new ones pinned too, and prefer not adding one —
  `httpx` is already there and covers most of what a new dependency would.
- Every config value has a working default. Nothing should require setup to
  run.

## Commits and pull requests

Commit subjects are single-line conventional commits, scoped to what changed:

```
fix(recommend): stop reporting a clamped eval swing as pawns
feat(classify): report where each weakness concentrates, not just how often
docs(prd): drop the stale caveat about the report page being unreviewed
```

Write the subject as what the change does for someone using it, not what you
edited. No body needed unless there's a why that doesn't fit.

Pull requests: say what changed and why, and mention anything you weren't
sure about — an open question in the description is more useful than a
confident guess. Small and focused beats comprehensive.
