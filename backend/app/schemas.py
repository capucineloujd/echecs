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
    """Point de vue des Blancs"""

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


class OpeningRef(BaseModel):
    slug: str
    name: str
    eco: str
    moves: str
    fen: str


class Passage(BaseModel):
    score: float = Field(description="Similarité cosinus (1 = identique)")
    opening_slug: str
    opening_name: str
    eco: str
    section: str
    source: Literal["wikibooks", "wikipedia_fr"]
    lang: str
    url: str
    text: str


class VectorSearchResponse(BaseModel):
    query: str
    detected_opening: OpeningRef | None = Field(None, description="Ouverture reconnue dans la question")
    filtered_by_opening: bool = Field(description="La recherche a été restreinte à cette ouverture")
    results: list[Passage]
    context: str = Field(description="Passages formatés, prêts pour un prompt LLM")
    videos: "VideosResponse | None" = Field(None, description="Vidéos de l'ouverture détectée")


class Video(BaseModel):
    id: str
    title: str
    channel: str
    channel_id: str
    published_at: str
    duration_seconds: int
    duration: str
    views: int
    likes: int | None = None
    language: str
    thumbnail_url: str | None = None
    watch_url: str
    embed_url: str = Field(description="URL à mettre dans une iframe pour lire la vidéo dans l'application")
    score: float


class VideosResponse(BaseModel):
    opening: str
    opening_slug: str | None = None
    status: Literal["ok", "no_results", "quota_exceeded", "unavailable"]
    message: str | None = None
    videos: list[Video] = []
    fallback_search_url: str = Field(description="Recherche YouTube à proposer si aucune vidéo n'est retenu")
    cached: bool = False
    quota_units_used: int = 0


class AgentRequest(BaseModel):
    fen: str = Field(description="Position à analyser")
    moves: list[str] = Field([], max_length=300, description="Coups joués jusqu'ici (SAN), pour le contexte")
    question: str | None = Field(None, max_length=500, description="Question de l'élève (facultative)")
