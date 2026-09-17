"""Shared data shapes for the analysis pipeline."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MoveRow:
    """One ply of one game — the flat dataset every classifier reads (PRD section 10).

    Evals are always from the analyzed player's perspective, including on the
    opponent's moves, so a game's eval trajectory can be read straight off the
    rows in ply order.
    """

    game_index: int
    game_id: str
    player_color: str  # "white" | "black"
    result: str  # "win" | "loss" | "draw", from the player's perspective
    ply: int
    move_number: int
    is_player_move: bool
    san: str
    piece_count: int  # before the move
    eval_before_cp: int
    eval_after_cp: int
    cpl: Optional[int] = None  # player moves only
    best_move_san: Optional[str] = None
    # None where the move was accurate enough that no classifier can use it.
    best_is_forcing: Optional[bool] = None
    clock_remaining_s: Optional[float] = None
    clock_pct: Optional[float] = None


@dataclass
class CategoryResult:
    name: str
    score: float
    confidence: str  # "ok" | "low" | "insufficient"
    instances: int
    details: dict = field(default_factory=dict)

    def to_payload(self) -> dict:
        """The four fields the PRD's report shape exposes — details stay internal."""
        return {
            "name": self.name,
            "score": round(self.score, 2),
            "confidence": self.confidence,
            "instances": self.instances,
        }


@dataclass
class Recommendation:
    category: str
    text: str
    evidence: str

    def to_payload(self) -> dict:
        return {"category": self.category, "text": self.text, "evidence": self.evidence}


@dataclass
class SummaryResult:
    text: str
    source: str  # "llm" | "fallback"
    violations: list = field(default_factory=list)
