import chess
import httpx
import pytest
import respx

from app.config import Settings
from app.core.errors import LichessAuthError, LichessRateLimitError, LichessUnavailableError
from app.services.lichess import LichessExplorerService

URL = "https://explorer.lichess.ovh"

E4_RESPONSE = {
    "white": 600,
    "draws": 300,
    "black": 100,
    "opening": {"eco": "B00", "name": "King's Pawn Game"},
    "moves": [
        {"uci": "c7c5", "san": "c5", "white": 300, "draws": 150, "black": 50, "averageRating": 2450},
        {"uci": "e7e5", "san": "e5", "white": 300, "draws": 150, "black": 50, "averageRating": 2440},
        {"uci": "e2e4", "san": "e4", "white": 1, "draws": 0, "black": 0},  # illégal : doit être ignoré
    ],
}


@pytest.fixture
def board():
    b = chess.Board()
    b.push_san("e4")
    return b


@pytest.fixture
def service():
    return LichessExplorerService(Settings(lichess_token="test", lichess_rate_limit_cooldown_seconds=60))


@respx.mock
async def test_parses_moves_and_drops_illegal(service, board):
    route = respx.get(f"{URL}/masters").mock(return_value=httpx.Response(200, json=E4_RESPONSE))

    result = await service.get_theory_moves(board)

    assert result.opening.eco == "B00"
    assert result.total_games == 1000
    assert [m.san for m in result.moves] == ["c5", "e5"]
    assert result.moves[0].white_pct == 60.0
    assert route.calls[0].request.headers["Authorization"] == "Bearer test"


@respx.mock
async def test_uses_cache(service, board):
    route = respx.get(f"{URL}/masters").mock(return_value=httpx.Response(200, json=E4_RESPONSE))

    await service.get_theory_moves(board)
    await service.get_theory_moves(board)

    assert route.call_count == 1


@respx.mock
async def test_rate_limit_blocks_following_requests(service, board):
    route = respx.get(f"{URL}/masters").mock(return_value=httpx.Response(429))

    with pytest.raises(LichessRateLimitError) as exc:
        await service.get_theory_moves(board)
    assert exc.value.retry_after == 60

    # Pendant la pause, on ne rappelle pas Lichess du tout
    with pytest.raises(LichessRateLimitError):
        await service.get_theory_moves(chess.Board())
    assert route.call_count == 1


@respx.mock
async def test_timeout(service, board):
    respx.get(f"{URL}/masters").mock(side_effect=httpx.ReadTimeout("trop long"))
    with pytest.raises(LichessUnavailableError):
        await service.get_theory_moves(board)


@respx.mock
async def test_unauthorized(service, board):
    respx.get(f"{URL}/masters").mock(return_value=httpx.Response(401))
    with pytest.raises(LichessAuthError):
        await service.get_theory_moves(board)


@respx.mock
async def test_server_error(service, board):
    respx.get(f"{URL}/masters").mock(return_value=httpx.Response(502))
    with pytest.raises(LichessUnavailableError):
        await service.get_theory_moves(board)
