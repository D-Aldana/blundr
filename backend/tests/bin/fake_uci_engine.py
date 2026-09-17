#!/usr/bin/env python3
"""A minimal UCI engine, so the real popen_uci/configure/analyse/quit path can
be tested without a Stockfish binary on PATH. Replies with a fixed score and
the position's first legal move, which is enough to drive the stage."""

import os
import sys
import time

import chess


def main():
    board = chess.Board()
    while True:
        # readline rather than iterating stdin: iteration read-aheads and the
        # driver would deadlock waiting for a response.
        line = sys.stdin.readline()
        if not line:
            return
        command = line.strip()

        if command == "uci":
            print("id name FakeFish")
            print("option name Threads type spin default 1 min 1 max 512")
            print("option name Hash type spin default 16 min 1 max 4096")
            print("uciok")
        elif command == "isready":
            print("readyok")
        elif command.startswith("position"):
            board = _board_from(command)
        elif command.startswith("go"):
            if os.environ.get("FAKE_ENGINE_STALL"):
                time.sleep(10)  # never answers — exercises the stage timeout
            best = next(iter(board.legal_moves), None)
            if best is None:
                print("bestmove 0000")
            else:
                print(f"info depth 12 score cp 25 pv {best.uci()}")
                print(f"bestmove {best.uci()}")
        elif command == "quit":
            return
        sys.stdout.flush()


def _board_from(command: str) -> chess.Board:
    parts = command.split()
    moves = parts[parts.index("moves") + 1 :] if "moves" in parts else []
    if "fen" in parts:
        fen_end = parts.index("moves") if "moves" in parts else len(parts)
        board = chess.Board(" ".join(parts[parts.index("fen") + 1 : fen_end]))
    else:
        board = chess.Board()
    for move in moves:
        board.push_uci(move)
    return board


if __name__ == "__main__":
    main()
