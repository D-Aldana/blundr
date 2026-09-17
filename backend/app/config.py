"""Tunable constants for the v1 pipeline (PRD sections 7, 13, 15)."""

import os

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

# Per-category constant that puts scores in a roughly comparable 0-1 range.
# Known simplification — recalibrate against real game data (PRD section 15).
SEVERITY_NORMALIZER = {
    "tactical": 300,
    "endgame": 200,
    "time_management": 250,
    "conversion": 600,
}

# --- Sample-size guard -------------------------------------------------------
MIN_INSTANCES = 3
LOW_CONFIDENCE_MAX = 5

# --- LLM summary -------------------------------------------------------------
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "claude-opus-5")
SUMMARY_MAX_TOKENS = 2000
SUMMARY_MAX_ATTEMPTS = 2
