from fastapi import Depends, Request

from app.config import settings
from app.core.errors import AgentUnavailableError, VectorStoreError
from app.services.lichess import LichessExplorerService
from app.services.position_analysis import PositionAnalysisService
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


def get_position_analysis(
    lichess: LichessExplorerService = Depends(get_lichess),
    stockfish: StockfishService = Depends(get_stockfish),
) -> PositionAnalysisService:
    return PositionAnalysisService(settings, lichess, stockfish)


def get_agent(request: Request):
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise AgentUnavailableError("Coach indisponible : modèle de langage non configuré (voir LLM_PROVIDER dans le README)")
    return agent
