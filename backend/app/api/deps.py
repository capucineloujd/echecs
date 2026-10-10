from fastapi import Request
from app.services.lichess import LichessExplorerService
from app.services.stockfish import StockfishService

def get_lichess(request: Request) -> LichessExplorerService:
    return request.app.state.lichess


def get_stockfish(request: Request) -> StockfishService:
    return request.app.state.stockfish
