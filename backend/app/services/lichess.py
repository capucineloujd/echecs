import asyncio
import logging
import time
import chess
import httpx
from app.config import Settings
from app.core.chess_utils import uci_to_san
from app.core.errors import LichessAuthError, LichessRateLimitError, LichessUnavailableError
from app.schemas import Opening, TheoryMove

logger = logging.getLogger(__name__)


class ExplorerResult:
    def __init__(self, opening: Opening | None, total_games: int, moves: list[TheoryMove]):
        self.opening = opening
        self.total_games = total_games
        self.moves = moves


class LichessExplorerService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._settings = settings
        headers = {"Accept": "application/json"}
        if settings.lichess_token:
            headers["Authorization"] = f"Bearer {settings.lichess_token}"
        self._client = client or httpx.AsyncClient(
            base_url=settings.lichess_explorer_url,
            headers=headers,
            timeout=settings.lichess_timeout_seconds,
        )
        self._lock = asyncio.Lock()
        self._blocked_until = 0.0
        self._cache: dict[tuple[str, str], tuple[float, ExplorerResult]] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def get_theory_moves(self, board: chess.Board, database: str | None = None) -> ExplorerResult:
        database = database or self._settings.lichess_database
        # on enlève les compteurs de coups de la clé
        key = (database, " ".join(board.fen().split()[:4]))

        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        data = await self._request(database, board.fen())
        result = self._parse(board, data)
        self._cache[key] = (time.monotonic() + self._settings.lichess_cache_ttl_seconds, result)
        return result

    async def _request(self, database: str, fen: str) -> dict:
        params = {"fen": fen, "moves": self._settings.lichess_max_moves, "topGames": 0, "recentGames": 0}
        if database == "lichess":
            params["speeds"] = self._settings.lichess_speeds
            params["ratings"] = self._settings.lichess_ratings

        async with self._lock:
            remaining = self._blocked_until - time.monotonic()
            if remaining > 0:
                raise LichessRateLimitError(retry_after=int(remaining) + 1)

            try:
                response = await self._client.get(f"/{database}", params=params)
            except httpx.TimeoutException as exc:
                raise LichessUnavailableError("Lichess n'a pas répondu à temps") from exc
            except httpx.HTTPError as exc:
                raise LichessUnavailableError(f"Erreur réseau vers Lichess : {exc}") from exc

            if response.status_code == 429:
                cooldown = self._retry_after(response)
                self._blocked_until = time.monotonic() + cooldown
                logger.warning("Lichess 429 : pause de %s s", cooldown)
                raise LichessRateLimitError(retry_after=cooldown)

        if response.status_code == 401:
            raise LichessAuthError("Token Lichess absent ou invalide (variable LICHESS_TOKEN)")
        if response.status_code >= 400:
            raise LichessUnavailableError(f"Lichess a répondu {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            raise LichessUnavailableError("Réponse Lichess illisible") from exc

    def _retry_after(self, response: httpx.Response) -> int:
        minimum = self._settings.lichess_rate_limit_cooldown_seconds
        try:
            return max(int(response.headers.get("Retry-After", minimum)), minimum)
        except ValueError:
            return minimum

    @staticmethod
    def _parse(board: chess.Board, data: dict) -> ExplorerResult:
        moves = []
        for m in data.get("moves", []):
            san = uci_to_san(board, m.get("uci", ""))
            if san is None:
                logger.warning("Coup illégal ignoré depuis Lichess : %s", m.get("uci"))
                continue
            white, draws, black = m.get("white", 0), m.get("draws", 0), m.get("black", 0)
            games = white + draws + black
            if games == 0:
                continue
            moves.append(
                TheoryMove(
                    uci=m["uci"],
                    san=san,
                    games=games,
                    white_wins=white,
                    draws=draws,
                    black_wins=black,
                    white_pct=round(100 * white / games, 1),
                    draw_pct=round(100 * draws / games, 1),
                    black_pct=round(100 * black / games, 1),
                    average_rating=m.get("averageRating"),
                )
            )

        opening = data.get("opening")
        return ExplorerResult(
            opening=Opening(**opening) if opening else None,
            total_games=data.get("white", 0) + data.get("draws", 0) + data.get("black", 0),
            moves=moves,
        )
