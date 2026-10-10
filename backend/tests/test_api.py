import chess
import pytest
from fastapi.testclient import TestClient
from app.api.deps import get_lichess, get_stockfish
from app.core.errors import LichessRateLimitError
from app.main import app
from app.schemas import Evaluation, Opening, Score, TheoryMove
from app.services.lichess import ExplorerResult

E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

class FakeLichess:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    async def get_theory_moves(self, board, database=None):
        if self.error:
            raise self.error
        return self.result


class FakeStockfish:
    calls = 0

    async def evaluate(self, board, depth=None, multipv=None):
        FakeStockfish.calls += 1
        return Evaluation(
            fen=board.fen(),
            side_to_move="white" if board.turn else "black",
            depth=depth or 12,
            score=Score(centipawns=35),
            best_move_uci="e7e5",
            best_move_san="e5",
            lines=[],
        )


THEORY = ExplorerResult(
    opening=Opening(eco="B00", name="King's Pawn Game"),
    total_games=1000,
    moves=[
        TheoryMove(uci="c7c5", san="c5", games=500, white_wins=300, draws=150, black_wins=50,
                   white_pct=60, draw_pct=30, black_pct=10)
    ],
)


@pytest.fixture
def client():
    FakeStockfish.calls = 0
    app.dependency_overrides[get_stockfish] = lambda: FakeStockfish()
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_lichess(**kwargs):
    app.dependency_overrides[get_lichess] = lambda: FakeLichess(**kwargs)


def test_moves_in_theory(client):
    use_lichess(result=THEORY)
    response = client.get(f"/api/v1/moves/{E4_FEN}")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "lichess" and body["in_theory"] is True
    assert body["opening"]["eco"] == "B00"
    assert body["moves"][0]["san"] == "c5"
    assert body["engine"] is None
    assert FakeStockfish.calls == 0


def test_moves_out_of_theory_falls_back_to_stockfish(client):
    use_lichess(result=ExplorerResult(opening=None, total_games=0, moves=[]))
    body = client.get(f"/api/v1/moves/{E4_FEN}").json()
    assert body["source"] == "stockfish" and body["in_theory"] is False
    assert body["engine"]["score"]["centipawns"] == 35


def test_moves_lichess_down_falls_back_with_warning(client):
    use_lichess(error=LichessRateLimitError(retry_after=60))
    body = client.get(f"/api/v1/moves/{E4_FEN}").json()
    assert body["source"] == "stockfish"
    assert "Lichess indisponible" in body["warning"]


def test_moves_accepts_underscores(client):
    use_lichess(result=THEORY)
    assert client.get(f"/api/v1/moves/{E4_FEN.replace(' ', '_')}").status_code == 200


def test_invalid_fen_returns_422(client):
    use_lichess(result=THEORY)
    response = client.get("/api/v1/moves/pas-une-fen")
    assert response.status_code == 422
    assert "FEN invalide" in response.json()["detail"]


def test_evaluate(client):
    body = client.get(f"/api/v1/evaluate/{chess.STARTING_FEN}?depth=12").json()
    assert body["score"]["centipawns"] == 35
    assert body["depth"] == 12


def test_evaluate_rejects_bad_depth(client):
    assert client.get(f"/api/v1/evaluate/{chess.STARTING_FEN}?depth=99").status_code == 422
