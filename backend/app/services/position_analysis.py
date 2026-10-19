import logging

import chess

from app.config import Settings

from app.core.errors import LichessRateLimitError, LichessUnavailableError
from app.schemas import MovesResponse
from app.services.lichess import LichessExplorerService
from app.services.stockfish import StockfishService

logger = logging.getLogger(__name__)


class PositionAnalysisService:
    def __init__(self, settings: Settings, lichess: LichessExplorerService, stockfish: StockfishService):
        self._settings = settings
        self._lichess = lichess
        self._stockfish = stockfish

    async def analyze(self, board: chess.Board, database: str | None = None) -> MovesResponse:
        database = database or self._settings.lichess_database

        warning = None
        try:
            theory = await self._lichess.get_theory_moves(board, database)
        except (LichessUnavailableError, LichessRateLimitError) as exc:
            logger.warning("Lichess indisponible, repli sur Stockfish : %s", exc)
            theory, warning = None, f"Lichess indisponible ({exc}), évaluation Stockfish à la place"

        if theory and theory.total_games >= self._settings.theory_min_games and theory.moves:
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
            engine=await self._stockfish.evaluate(board),
            warning=warning,
        )
