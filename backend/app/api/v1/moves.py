from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_position_analysis
from app.core.chess_utils import parse_fen
from app.schemas import MovesResponse
from app.services.position_analysis import PositionAnalysisService

router = APIRouter(tags=["moves"])


# {fen:path}: une FEN contient des "/", qu'un paramètre classique refuserait
@router.get("/moves/{fen:path}", response_model=MovesResponse)
async def get_moves(
    fen: str,
    database: Literal["masters", "lichess"] | None = Query(None, description="Base Lichess à interroger"),
    analysis: PositionAnalysisService = Depends(get_position_analysis),
):
    """Coups théoriques depuis Lichess. Hors théorie (ou Lichess indisponible) : Stockfish prend le relais."""
    return await analysis.analyze(parse_fen(fen), database)
