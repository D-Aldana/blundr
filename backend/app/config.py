"""Tunable constants for the v1 pipeline (PRD sections 7, 13, 15)."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root, then from wherever the server was started.
# Neither overrides a variable already set in the real environment.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()

MIN_GAMES_REQUIRED = 20
TIME_CONTROLS = ("bullet", "blitz", "rapid")
VALID_TIME_CLASSES = set(TIME_CONTROLS)

# --- Chess.com fetch ---------------------------------------------------------
CHESS_COM_BASE = "https://api.chess.com/pub"
# Chess.com asks for a contact address in the User-Agent so they can reach you
# about traffic from your instance. The placeholder below is accepted, but set
# CHESS_COM_CONTACT to your own address — it's their stated etiquette, and it
# keeps your traffic from being lumped in with every other clone's.
CHESS_COM_CONTACT = os.getenv("CHESS_COM_CONTACT", "you@example.com")
CHESS_COM_HEADERS = {"User-Agent": f"blundr/0.1 ({CHESS_COM_CONTACT})"}
# Bounds on how far back we walk a very active player's monthly archives.
MAX_ARCHIVE_MONTHS = 12
ELIGIBILITY_COUNT_CAP = MIN_GAMES_REQUIRED * 3
GAME_COUNT_CACHE_TTL = 60.0

# --- Engine ------------------------------------------------------------------
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "stockfish")
ENGINE_DEPTH = int(os.getenv("ENGINE_DEPTH", "12"))
ENGINE_THREADS = int(os.getenv("ENGINE_THREADS", "2"))
ENGINE_HASH_MB = int(os.getenv("ENGINE_HASH_MB", "128"))
ENGINE_TIMEOUT_S = float(os.getenv("ENGINE_TIMEOUT_S", "300"))
# Evals are clamped before centipawn loss is computed, so a move played in an
# already-lost position can't contribute a five-figure "mistake".
EVAL_CLAMP_CP = 1500
MATE_SCORE_CP = 10000

# --- Classifier thresholds (PRD section 15) ----------------------------------
# A position this lopsided is already decided; drifting within it isn't a
# weakness, it's engine noise in a game that was over.
DECISIVE_CP = 600

TACTICAL_CPL_THRESHOLD = 150
ENDGAME_CPL_THRESHOLD = 100
ENDGAME_MAX_PIECES = 12
TIME_LOW_BUCKET = 0.25
TIME_HIGH_BUCKET = 0.50
TIME_CPL_THRESHOLD = 100
TIME_RATIO_TRIGGER = 1.5
TIME_MIN_LOW_MOVES = 5
CONVERSION_WINNING_CP = 300
CONVERSION_LOST_CP = 100

# The rate at which a category counts as a severe problem, as a fraction of
# that category's own opportunities: tactical and endgame are per qualifying
# move, time management is per rushed move, conversion is per winning position
# reached. A player at this rate scores 1.0.
#
# Calibrated against 15 real accounts from 612 to 2127 blitz, plus super-GM
# anchors: each value is the 90th-percentile rate among players in the PRD's
# target band, so "severe" means worse than roughly 9 in 10 comparable players
# (PRD section 15). Time management is measured over players who clear its
# ratio gate, since the gate already excludes the rest.
SEVERE_RATE = {
    "tactical": 0.11,  # 11 missed shots per 100 moves
    "endgame": 0.20,  # 20 slips per 100 endgame moves
    "time_management": 0.35,  # 35 blunders per 100 low-clock moves
    "conversion": 0.60,  # 3 of every 5 winning positions thrown away
}

# --- Sample-size guard -------------------------------------------------------
MIN_INSTANCES = 3
LOW_CONFIDENCE_MAX = 5

# --- LLM summary -------------------------------------------------------------
# Which provider writes the closing paragraph. Left unset, the first provider
# whose API key is present wins; set it explicitly to pick one, and to reach
# Ollama at all (it has no key to detect). See app/providers/.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower()
# Unset means "whatever that provider's default is" — see providers/*.DEFAULT_MODEL.
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "").strip()
# Any OpenAI-compatible endpoint: Groq, OpenRouter, Gemini's compat layer,
# LM Studio, vLLM. Unset talks to OpenAI itself.
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
# Generous, because a local model on a laptop CPU is not fast.
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "120"))
SUMMARY_MAX_TOKENS = 2000
SUMMARY_MAX_ATTEMPTS = 2

# --- Abuse limits ------------------------------------------------------------
# No signup means no account to throttle, so every limit below is keyed on
# either the request IP or a global ceiling. All of it is in-process state:
# correct for the single instance PRD section 13 specifies, and it silently
# becomes per-instance if this is ever scaled out.

# Chess.com usernames are 3-25 characters of letters, digits, underscore and
# hyphen. Enforcing that also keeps caller-controlled text out of the request
# path, where "../" or "?" would otherwise choose the endpoint we hit.
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,25}$")

# The engine stage is CPU-bound and runs for tens of seconds, so it gets a hard
# concurrency cap instead of one Stockfish process per request. Past the cap
# jobs queue; past the queue they are refused rather than silently starved.
MAX_CONCURRENT_ANALYSES = int(os.getenv("MAX_CONCURRENT_ANALYSES", "1"))
MAX_QUEUED_ANALYSES = int(os.getenv("MAX_QUEUED_ANALYSES", "8"))

# Per-IP sliding windows: (requests, window_seconds). Sized for the way this
# actually runs — one person on their own machine, analyzing their account and
# their friends' — so the limits are a runaway-loop backstop, not a ration.
# Lower them substantially if you ever put an instance on the open internet.
RATE_LIMIT_ANALYZE = (int(os.getenv("RATE_LIMIT_ANALYZE", "50")), 3600.0)
RATE_LIMIT_ELIGIBILITY = (int(os.getenv("RATE_LIMIT_ELIGIBILITY", "200")), 3600.0)

# Only trust X-Forwarded-For when a proxy that overwrites it is actually in
# front (Render, Cloudflare). Trusting it otherwise lets a caller forge an IP
# per request and defeat every limit above.
TRUST_PROXY_HEADER = os.getenv("TRUST_PROXY_HEADER", "").lower() in ("1", "true", "yes")

# Ceiling on paid LLM calls per rolling 24h. Past it the summary degrades to
# the deterministic paragraph rather than the job failing — the fallback path
# already exists for the no-API-key case.
SUMMARY_DAILY_BUDGET = int(os.getenv("SUMMARY_DAILY_BUDGET", "200"))
