from fastapi import Request
from app.core.errors import VectorStoreError
from app.services.lichess import LichessExplorerService
from app.services.stockfish import StockfishService

def get_lichess(request: Request) -> LichessExplorerService:
    return request.app.state.lichess


def get_stockfish(request: Request) -> StockfishService:
    return request.app.state.stockfish


def get_rag_graph(request: Request):
    graph = getattr(request.app.state, "rag_graph", None)
    if graph is None:
        raise VectorStoreError("Recherche vectorielle indisponible (modèle ou Milvus non initialisé)")
    return graph


def get_youtube(request: Request):
    return request.app.state.youtube


def get_catalog(request: Request):
    return request.app.state.catalog
