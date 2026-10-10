import shutil
import chess
import pytest
from app.config import Settings
from app.services.stockfish import StockfishService

STOCKFISH = shutil.which("stockfish") or shutil.which("/usr/games/stockfish")
pytestmark = pytest.mark.skipif(STOCKFISH is None, reason="Stockfish non installé")

@pytest.fixture
async def engine():
    service = StockfishService(Settings(stockfish_path=STOCKFISH, stockfish_depth=10))
    await service.start()
    yield service
    await service.stop()


async def test_starting_position_is_balanced(engine):
    evaluation = await engine.evaluate(chess.Board(), multipv=2)
    assert abs(evaluation.score.centipawns) < 100
    assert len(evaluation.lines) == 2
    assert evaluation.best_move_san

async def test_score_is_from_white_point_of_view(engine):
    # les Blancs ont une dame de +, trait aux Noirs : le score doit rester positif
    board = chess.Board("4k3/8/8/8/8/8/8/3QK3 b - - 0 1")
    evaluation = await engine.evaluate(board)
    assert evaluation.side_to_move == "black"
    assert evaluation.score.mate is not None and evaluation.score.mate > 0 or evaluation.score.centipawns > 500



async def test_mate_in_one(engine):
    board = chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
    evaluation = await engine.evaluate(board)
    assert evaluation.score.mate == 1
    assert evaluation.best_move_san == "Ra8#"

async def test_game_over_position(engine):
    board = chess.Board("R5k1/5ppp/8/8/8/8/8/6K1 b - - 1 1")
    evaluation = await engine.evaluate(board)
    assert evaluation.game_over == "checkmate"
    assert evaluation.lines == []
