"""Tunable constants for the v1 pipeline (PRD sections 7, 13, 15)."""

import os
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
# Chess.com returns 403 without a descriptive User-Agent. Set a real contact
# address via CHESS_COM_CONTACT before deploying.
CHESS_COM_CONTACT = os.getenv("CHESS_COM_CONTACT", "you@example.com")
CHESS_COM_HEADERS = {"User-Agent": f"chess-weakness-analyzer/0.1 ({CHESS_COM_CONTACT})"}
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
# First-pass constants — the shape of the formula is sound, but these numbers
# want calibrating against accounts spread across the rating range
# (PRD section 15).
SEVERE_RATE = {
    "tactical": 0.06,  # 6 missed shots per 100 moves
    "endgame": 0.10,  # 10 slips per 100 endgame moves
    "time_management": 0.15,  # 15 rushed blunders per 100 low-clock moves
    "conversion": 0.50,  # half of all winning positions thrown away
}

# --- Sample-size guard -------------------------------------------------------
MIN_INSTANCES = 3
LOW_CONFIDENCE_MAX = 5

# --- LLM summary -------------------------------------------------------------
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "claude-opus-5")
SUMMARY_MAX_TOKENS = 2000
SUMMARY_MAX_ATTEMPTS = 2
