import chess
import chess.engine

from app import config
from app.engine import (
    base_seconds,
    evaluate_game,
    is_forcing,
    parse_pgn,
    player_color,
    result_for,
)

PGN_WITH_CLOCKS = """[Event "Live Chess"]
[Site "Chess.com"]
[White "TestPlayer"]
[Black "Rival"]
[Result "0-1"]
[TimeControl "300"]

1. e4 {[%clk 0:04:58]} e5 {[%clk 0:04:57]} 2. Nf3 {[%clk 0:04:40]} Nc6 {[%clk 0:04:50]}
3. Bb5 {[%clk 0:00:20]} a6 {[%clk 0:04:30]} 0-1
"""


class FakeEngine:
    """Returns a scripted eval per position, from the side-to-move's view —
    the same shape python-chess's analyse() gives back."""

    def __init__(self, scores, best_moves=None):
        self.scores = list(scores)
        self.best_moves = best_moves or {}
        self.calls = 0

    async def analyse(self, board, limit):
        score = self.scores[min(self.calls, len(self.scores) - 1)]
        self.calls += 1
        info = {"score": chess.engine.PovScore(chess.engine.Cp(score), board.turn)}
        best = self.best_moves.get(board.fen()) or next(iter(board.legal_moves), None)
        if best:
            info["pv"] = [best]
        return info


def test_header_parsing():
    game = parse_pgn(PGN_WITH_CLOCKS)
    assert player_color(game, "testplayer") == chess.WHITE
    assert player_color(game, "nobody") is None
    assert result_for(game, chess.WHITE) == "loss"
    assert result_for(game, chess.BLACK) == "win"
    assert base_seconds(game) == 300.0


def test_base_seconds_handles_increment_and_daily():
    game = parse_pgn(PGN_WITH_CLOCKS)
    game.headers["TimeControl"] = "180+2"
    assert base_seconds(game) == 180.0
    game.headers["TimeControl"] = "1/86400"
    assert base_seconds(game) is None


async def test_rows_capture_cpl_clock_and_phase():
    game = parse_pgn(PGN_WITH_CLOCKS)
    # Position evals, side-to-move relative: white is fine until ply 5, where
    # white's eval drops by 300 from white's perspective.
    engine = FakeEngine([20, -20, 20, -20, 20, 280, -20])
    rows = await evaluate_game(engine, game, "TestPlayer", game_index=0, game_id="u")

    assert len(rows) == 6
    player_rows = [r for r in rows if r.is_player_move]
    assert len(player_rows) == 3
    assert all(r.player_color == "white" and r.result == "loss" for r in rows)

    # White's third move: eval before +20, after -(-280)... engine returns +280
    # for black to move, i.e. -280 from white's view -> 300 centipawns lost.
    assert player_rows[2].cpl == 300
    assert player_rows[0].cpl == 0

    # Clocks are recorded for the player's own moves only, as a fraction of 300s.
    assert player_rows[0].clock_remaining_s == 298
    assert round(player_rows[2].clock_pct, 3) == round(20 / 300, 3)
    assert all(r.clock_pct is None for r in rows if not r.is_player_move)

    assert rows[0].piece_count == 32
    assert rows[0].san == "e4"
    assert rows[0].move_number == 1


async def test_opponent_moves_carry_player_perspective_evals():
    game = parse_pgn(PGN_WITH_CLOCKS)
    engine = FakeEngine([100, -100, 100, -100, 100, -100, 100])
    rows = await evaluate_game(engine, game, "Rival", game_index=0)

    # Analyzed as black: a +100 score for white to move is -100 for black.
    assert rows[0].eval_before_cp == -100
    assert all(r.cpl is None for r in rows if not r.is_player_move)
    assert all(r.cpl == 0 for r in rows if r.is_player_move)


async def test_game_the_player_did_not_play_is_skipped():
    game = parse_pgn(PGN_WITH_CLOCKS)
    rows = await evaluate_game(FakeEngine([0]), game, "SomeoneElse", game_index=0)
    assert rows == []


def test_is_forcing_detects_captures_checks_and_new_threats():
    board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    assert is_forcing(board, board.parse_san("exd5"))  # capture

    board = chess.Board("rnbqkbnr/ppp2ppp/8/3pp3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3")
    assert is_forcing(board, board.parse_san("Bb5+"))  # check

    # Quiet developing move that attacks nothing.
    board = chess.Board("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    assert not is_forcing(board, board.parse_san("h3"))

    # Nc3 attacks the undefended pawn on b5 — a new material threat.
    board = chess.Board("rnbqkbnr/p1pppppp/8/1p6/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 2")
    assert is_forcing(board, board.parse_san("Nc3"))


async def test_terminal_position_is_scored_without_the_engine():
    game = parse_pgn(
        '[White "P"]\n[Black "Q"]\n[Result "1-0"]\n[TimeControl "60"]\n\n'
        "1. f3 e5 2. g4 Qh4# 0-1\n"
    )
    engine = FakeEngine([0, 0, 0, 0, 0])
    rows = await evaluate_game(engine, game, "Q", game_index=0)

    assert rows[-1].eval_after_cp == config.EVAL_CLAMP_CP  # mate, from Q's view
    assert engine.calls == 4  # the mated position is never sent to the engine


async def test_playing_the_engines_own_move_costs_nothing():
    game = parse_pgn(PGN_WITH_CLOCKS)
    # The stub always names the played move as best, while the evals drift —
    # exactly the search instability that used to score as a blunder.
    best_by_fen = {}
    board = game.board()
    for node in game.mainline():
        best_by_fen[board.fen()] = node.move
        board.push(node.move)

    engine = FakeEngine([1105, -851, 1105, -851, 1105, -851, 1105], best_by_fen)
    rows = await evaluate_game(engine, game, "TestPlayer", game_index=0)

    assert all(r.cpl == 0 for r in rows if r.is_player_move)
