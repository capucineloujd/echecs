import chess
import pytest
from app.core.chess_utils import parse_fen, uci_to_san
from app.core.errors import InvalidFenError

START = chess.STARTING_FEN


def test_parse_valid_fen():
    assert parse_fen(START).fen() == START


def test_parse_lichess_url_style_fen():
    assert parse_fen(START.replace(" ", "_")).fen() == START


@pytest.mark.parametrize(
    "fen",
    [
        "pas une fen",
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP w KQkq - 0 1",
        "8/8/8/8/8/8/8/8 w - - 0 1",
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1 x",
    ],
)
def test_parse_invalid_fen(fen):
    with pytest.raises(InvalidFenError):
        parse_fen(fen)


def test_uci_to_san():
    board = chess.Board()
    assert uci_to_san(board, "g1f3") == "Nf3"
    assert uci_to_san(board, "e2e5") is None
    assert uci_to_san(board, "nimporte") is None
