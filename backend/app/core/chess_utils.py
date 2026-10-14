import chess
from app.core.errors import InvalidFenError


def parse_fen(fen: str) -> chess.Board:
    fen = fen.strip().replace("_", " ")
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise InvalidFenError(f"FEN invalide : {exc}") from exc

    if not board.is_valid():
        raise InvalidFenError(f"Position illégale : {board.status()!r}")
    return board

def uci_to_san(board: chess.Board, uci: str) -> str | None:
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return None
    if move not in board.legal_moves:
        return None
    return board.san(move)
