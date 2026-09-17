"""Stockfish evaluation stage: PGNs in, one flat MoveRow per ply out.

Every position is analysed exactly once. Because evals are recorded from the
analyzed player's perspective, the eval of the position before a move and the
eval of the position after it give that move's centipawn loss directly, and the
same numbers double as the game's eval trajectory for the conversion check.
"""

import asyncio
import io
import logging
from typing import Callable, Optional

import chess
import chess.engine
import chess.pgn

from . import config
from .models import MoveRow

log = logging.getLogger(__name__)

ENGINE_QUIT_TIMEOUT_S = 5.0

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}


class NoAnalyzableGames(Exception):
    """Every PGN failed to parse, or none of them were the player's games."""


def parse_pgn(pgn_text: str) -> Optional[chess.pgn.Game]:
    return chess.pgn.read_game(io.StringIO(pgn_text))


def player_color(game: chess.pgn.Game, username: str) -> Optional[bool]:
    target = username.strip().lower()
    if game.headers.get("White", "").lower() == target:
        return chess.WHITE
    if game.headers.get("Black", "").lower() == target:
        return chess.BLACK
    return None


def result_for(game: chess.pgn.Game, color: bool) -> str:
    result = game.headers.get("Result", "*")
    if result == "1/2-1/2":
        return "draw"
    if result == "1-0":
        return "win" if color == chess.WHITE else "loss"
    if result == "0-1":
        return "win" if color == chess.BLACK else "loss"
    return "unknown"


def base_seconds(game: chess.pgn.Game) -> Optional[float]:
    """Starting clock from the PGN TimeControl header ("180+2", "300", "1/86400")."""
    raw = game.headers.get("TimeControl", "")
    base = raw.split("+")[0].strip()
    if not base.isdigit():
        return None
    seconds = float(base)
    return seconds if seconds > 0 else None


def _clamp(cp: int) -> int:
    return max(-config.EVAL_CLAMP_CP, min(config.EVAL_CLAMP_CP, cp))


def _score_cp(info: dict, color: bool) -> int:
    score = info.get("score")
    if score is None:
        return 0
    return _clamp(score.pov(color).score(mate_score=config.MATE_SCORE_CP))


def _best_move(info: dict) -> Optional[chess.Move]:
    pv = info.get("pv")
    return pv[0] if pv else None


def _centipawn_loss(eval_before: int, eval_after: int, played_best: bool) -> int:
    """Playing the engine's own choice costs nothing by definition. Scoring it
    otherwise just measures search instability between two separate
    depth-limited analyses, which is loudest in exactly the sharp positions
    the classifiers care about."""
    if played_best:
        return 0
    return max(0, eval_before - eval_after)


def _terminal_eval(board: chess.Board, color: bool) -> int:
    """Eval of a finished position, so we never ask the engine about one."""
    outcome = board.outcome(claim_draw=True)
    if outcome is None or outcome.winner is None:
        return 0
    return config.EVAL_CLAMP_CP if outcome.winner == color else -config.EVAL_CLAMP_CP


def _hangs(board: chess.Board, square: int, attacker_color: bool) -> bool:
    """Is the piece on `square` attacked favourably by `attacker_color`?"""
    piece = board.piece_at(square)
    if piece is None or piece.color == attacker_color or piece.piece_type == chess.KING:
        return False
    attackers = board.attackers(attacker_color, square)
    if not attackers:
        return False
    cheapest = min(PIECE_VALUES[board.piece_type_at(sq)] for sq in attackers)
    undefended = not board.attackers(not attacker_color, square)
    return undefended or PIECE_VALUES[piece.piece_type] > cheapest


def is_forcing(board: chess.Board, move: chess.Move) -> bool:
    """Capture, check, promotion, or a move creating a new material threat
    within 1 ply (PRD section 15, tactical trigger)."""
    if board.is_capture(move) or move.promotion or board.gives_check(move):
        return True

    mover = board.turn
    after = board.copy(stack=False)
    after.push(move)
    for square in after.piece_map():
        if _hangs(after, square, mover) and not _hangs(board, square, mover):
            return True
    return False


async def evaluate_game(
    engine, game: chess.pgn.Game, username: str, game_index: int, game_id: str = ""
) -> list[MoveRow]:
    color = player_color(game, username)
    if color is None:
        log.warning("game %s: %s played neither side, skipping", game_index, username)
        return []

    limit = chess.engine.Limit(depth=config.ENGINE_DEPTH)
    result = result_for(game, color)
    start_seconds = base_seconds(game)

    board = game.board()
    if board.is_game_over():
        return []

    rows: list[MoveRow] = []
    info = await engine.analyse(board, limit)

    for ply, node in enumerate(game.mainline(), start=1):
        move = node.move
        if move not in board.legal_moves:
            log.warning("game %s: illegal move at ply %s, truncating", game_index, ply)
            break

        is_player_move = board.turn == color
        eval_before = _score_cp(info, color)
        best = _best_move(info)
        best_san = board.san(best) if best else None
        forcing = is_forcing(board, best) if (is_player_move and best) else None
        san = board.san(move)
        played_best = best is not None and move == best
        piece_count = len(board.piece_map())
        move_number = board.fullmove_number

        board.push(move)
        if board.is_game_over():
            eval_after = _terminal_eval(board, color)
            info = {}
        else:
            info = await engine.analyse(board, limit)
            eval_after = _score_cp(info, color)

        clock = node.clock()
        clock_pct = None
        if clock is not None and start_seconds:
            clock_pct = min(1.0, clock / start_seconds)

        rows.append(
            MoveRow(
                game_index=game_index,
                game_id=game_id,
                player_color="white" if color == chess.WHITE else "black",
                result=result,
                ply=ply,
                move_number=move_number,
                is_player_move=is_player_move,
                san=san,
                piece_count=piece_count,
                eval_before_cp=eval_before,
                eval_after_cp=eval_after,
                cpl=_centipawn_loss(eval_before, eval_after, played_best)
                if is_player_move
                else None,
                best_move_san=best_san,
                best_is_forcing=forcing,
                clock_remaining_s=clock if is_player_move else None,
                clock_pct=clock_pct if is_player_move else None,
            )
        )

    return rows


async def evaluate_games_with_stockfish(
    games: list[dict],
    username: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> list[MoveRow]:
    """Run every game through Stockfish and return the flat per-move dataset.

    The whole stage is time-boxed: a wedged or misbehaving engine has to fail
    the job rather than leave it running forever.
    """
    transport, engine = await chess.engine.popen_uci(config.STOCKFISH_PATH)
    try:
        await engine.configure(
            {"Threads": config.ENGINE_THREADS, "Hash": config.ENGINE_HASH_MB}
        )
        rows = await asyncio.wait_for(
            _evaluate_all(engine, games, username, progress_cb),
            timeout=config.ENGINE_TIMEOUT_S,
        )
    finally:
        # A wedged engine won't answer "quit" either — don't let shutdown
        # swallow the timeout we just raised.
        try:
            await asyncio.wait_for(engine.quit(), timeout=ENGINE_QUIT_TIMEOUT_S)
        except (asyncio.TimeoutError, chess.engine.EngineError):
            transport.kill()

    if not rows:
        raise NoAnalyzableGames("no games could be parsed and evaluated")
    return rows


async def _evaluate_all(engine, games, username, progress_cb) -> list[MoveRow]:
    rows: list[MoveRow] = []
    total = len(games)
    for index, game_data in enumerate(games):
        pgn = game_data["pgn"] if isinstance(game_data, dict) else game_data
        game = parse_pgn(pgn)
        if game is not None:
            game_id = game_data.get("url", "") if isinstance(game_data, dict) else ""
            rows.extend(await evaluate_game(engine, game, username, index, game_id))
        if progress_cb:
            progress_cb(index + 1, total)
    return rows
