import asyncio
import logging
import chess
import chess.engine
from app.config import Settings
from app.core.errors import EngineError
from app.schemas import EngineLine, Evaluation, Score

logger = logging.getLogger(__name__)



class StockfishService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._engine: chess.engine.UciProtocol | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        try:
            _, self._engine = await chess.engine.popen_uci(self._settings.stockfish_path)
            await self._engine.configure(
                {"Threads": self._settings.stockfish_threads, "Hash": self._settings.stockfish_hash_mb}
            )
            logger.info("Stockfish démarré : %s", self._engine.id.get("name"))
        except (FileNotFoundError, chess.engine.EngineError) as exc:
            self._engine = None
            raise EngineError(f"Impossible de lancer Stockfish ({self._settings.stockfish_path})") from exc

    async def stop(self) -> None:
        if self._engine is not None:
            try:
                await self._engine.quit()
            except chess.engine.EngineTerminatedError:
                pass
            self._engine = None

    async def evaluate(self, board: chess.Board, depth: int | None = None, multipv: int | None = None) -> Evaluation:
        depth = depth or self._settings.stockfish_depth
        multipv = multipv or self._settings.stockfish_multipv

        if board.is_game_over():
            return self._game_over_evaluation(board)

        limit = chess.engine.Limit(depth=depth, time=self._settings.stockfish_time_limit_seconds)
        async with self._lock:
            if self._engine is None:
                await self.start()
            try:
                infos = await self._engine.analyse(board, limit, multipv=multipv)
            except (chess.engine.EngineTerminatedError, chess.engine.EngineError) as exc:
                self._engine = None
                raise EngineError("Stockfish a planté pendant l'analyse") from exc

        lines = [
            EngineLine(rank=rank, score=self._score(info), pv_san=self._pv_san(board, info.get("pv", [])))
            for rank, info in enumerate(infos, start=1)
        ]
        best = infos[0].get("pv", [None])[0]
        return Evaluation(
            fen=board.fen(),
            side_to_move="white" if board.turn == chess.WHITE else "black",
            depth=infos[0].get("depth", 0),
            score=lines[0].score,
            best_move_uci=best.uci() if best else None,
            best_move_san=board.san(best) if best else None,
            lines=lines,
        )

    @staticmethod
    def _score(info: chess.engine.InfoDict) -> Score:
        score = info["score"].white()
        if score.is_mate():
            return Score(mate=score.mate())
        return Score(centipawns=score.score())

    @staticmethod
    def _pv_san(board: chess.Board, pv: list[chess.Move]) -> list[str]:
        sans, b = [], board.copy(stack=False)
        for move in pv:
            sans.append(b.san(move))
            b.push(move)
        return sans

    @staticmethod
    def _game_over_evaluation(board: chess.Board) -> Evaluation:
        outcome = board.outcome()
        # partie finie : mat ou nulle
        score = Score(centipawns=0) if outcome.winner is None else Score(mate=0)
        return Evaluation(
            fen=board.fen(),
            side_to_move="white" if board.turn == chess.WHITE else "black",
            depth=0,
            score=score,
            best_move_uci=None,
            best_move_san=None,
            lines=[],
            game_over=outcome.termination.name.lower(),
        )
