from typing import Literal
from pydantic import BaseModel, Field


class Opening(BaseModel):
    eco: str
    name: str


class TheoryMove(BaseModel):
    uci: str
    san: str
    games: int
    white_wins: int
    draws: int
    black_wins: int
    white_pct: float = Field(description="% de victoires des Blancs")
    draw_pct: float
    black_pct: float
    average_rating: int | None = None


class Score(BaseModel):
    """Évaluation du point de vue des Blancs (positif = avantage Blancs)."""

    centipawns: int | None = None
    mate: int | None = Field(None, description="Mat en N coups (négatif = les Noirs matent)")


class EngineLine(BaseModel):
    rank: int
    score: Score
    pv_san: list[str] = Field(description="Variante principale en notation SAN")


class Evaluation(BaseModel):
    fen: str
    side_to_move: Literal["white", "black"]
    depth: int
    score: Score
    best_move_uci: str | None
    best_move_san: str | None
    lines: list[EngineLine]
    game_over: str | None = Field(None, description="checkmate, stalemate... si la partie est finie")


class MovesResponse(BaseModel):
    fen: str
    source: Literal["lichess", "stockfish"]
    in_theory: bool
    database: str
    opening: Opening | None = None
    total_games: int = 0
    moves: list[TheoryMove] = []
    engine: Evaluation | None = Field(None, description="Rempli quand la position est hors théorie")
    warning: str | None = None
