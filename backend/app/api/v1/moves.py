import logging
from typing import Literal
from fastapi import APIRouter, Depends, Query
from app.api.deps import get_lichess, get_stockfish
from app.config import settings
from app.core.chess_utils import parse_fen
from app.core.errors import LichessRateLimitError, LichessUnavailableError
from app.schemas import MovesResponse
from app.services.lichess import LichessExplorerService
from app.services.stockfish import StockfishService


logger = logging.getLogger(__name__)

router = APIRouter(tags=["moves"])


# {fen:path}: une FEN contient des "/", qu'un paramètre classique refuserait
@router.get("/moves/{fen:path}", response_model=MovesResponse)
async def get_moves(
    fen: str,
    database: Literal["masters", "lichess"] | None = Query(None, description="Base Lichess à interroger"),
    lichess: LichessExplorerService = Depends(get_lichess),
    stockfish: StockfishService = Depends(get_stockfish),
):
    """Coups théoriques depuis Lichess. Hors théorie (ou Lichess indisponible) :Stockfish prend le relais."""
    board = parse_fen(fen)
    database = database or settings.lichess_database

    warning = None
    try:
        theory = await lichess.get_theory_moves(board, database)
    except (LichessUnavailableError, LichessRateLimitError) as exc:
        logger.warning("Lichess indisponible, repli sur Stockfish : %s", exc)
        theory, warning = None, f"Lichess indisponible ({exc}), évaluation Stockfish à la place"

    if theory and theory.total_games >= settings.theory_min_games and theory.moves:
        return MovesResponse(
            fen=board.fen(),
            source="lichess",
            in_theory=True,
            database=database,
            opening=theory.opening,
            total_games=theory.total_games,
            moves=theory.moves,
        )

    return MovesResponse(
        fen=board.fen(),
        source="stockfish",
        in_theory=False,
        database=database,
        opening=theory.opening if theory else None,
        total_games=theory.total_games if theory else 0,
        moves=theory.moves if theory else [],
        engine=await stockfish.evaluate(board),
        warning=warning,
    )
