from fastapi import APIRouter, Depends, Query
from app.api.deps import get_stockfish
from app.core.chess_utils import parse_fen
from app.schemas import Evaluation
from app.services.stockfish import StockfishService

router = APIRouter(tags=["evaluate"])


@router.get("/evaluate/{fen:path}", response_model=Evaluation)
async def evaluate(
    fen: str,
    depth: int | None = Query(None, ge=1, le=30, description="Profondeur d'analyse"),
    multipv: int | None = Query(None, ge=1, le=5, description="Nombre de meilleures lignes"),
    stockfish: StockfishService = Depends(get_stockfish),
):
    """Évaluation Stockfish de la position, en centipawns du point de vue des Blancs"""
    return await stockfish.evaluate(parse_fen(fen), depth=depth, multipv=multipv)
