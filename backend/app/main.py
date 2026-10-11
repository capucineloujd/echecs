import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import asyncio
from app.api.v1 import evaluate, health, moves, vector_search, videos
from app.config import settings
from app.core.errors import (
    EngineError,
    InvalidFenError,
    LichessAuthError,
    LichessRateLimitError,
    LichessUnavailableError,
    VectorStoreError,
)
from app.services.lichess import LichessExplorerService
from app.rag.catalog import OpeningCatalog
from app.rag.graph import build_rag_graph
from app.services.cache import MongoCache
from app.services.stockfish import StockfishService
from app.services.youtube import YouTubeService
from app.services.vector_store import VectorStoreService


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.lichess = LichessExplorerService(settings)
    app.state.stockfish = StockfishService(settings)
    try:
        await app.state.stockfish.start()
    except EngineError as exc:
        # L'API démarre quand même : le moteur sera relancé à la 1ere requête
        logger.error("%s", exc)
    app.state.cache = MongoCache(settings.mongo_uri, settings.mongo_db)
    catalog = OpeningCatalog.load()
    app.state.youtube = YouTubeService(settings, app.state.cache, catalog)
    app.state.vector_store = VectorStoreService(settings.milvus_uri, settings.milvus_collection)
    try:
        # Import tardif : torch est long à charger, inutile pour /moves et /evaluate
        from app.services.embeddings import EmbeddingService

        embedder = await asyncio.to_thread(
            EmbeddingService,
            settings.embedding_model,
            settings.embedding_batch_size,
            settings.embedding_threads,
            settings.embedding_query_instruction,
        )
        app.state.rag_graph = build_rag_graph(embedder, app.state.vector_store, catalog, app.state.youtube)
    except Exception as exc:
        # L'API reste utilisable sans RAG : /vector-search renverra 503
        logger.error("RAG désactivé : %s", exc)
    yield
    app.state.vector_store.close()
    await app.state.cache.close()
    await app.state.stockfish.stop()
    await app.state.lichess.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(moves.router, prefix=settings.api_v1_prefix)
app.include_router(evaluate.router, prefix=settings.api_v1_prefix)
app.include_router(vector_search.router, prefix=settings.api_v1_prefix)
app.include_router(videos.router, prefix=settings.api_v1_prefix)


@app.exception_handler(InvalidFenError)
async def invalid_fen_handler(request: Request, exc: InvalidFenError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(LichessRateLimitError)
async def rate_limit_handler(request: Request, exc: LichessRateLimitError):
    return JSONResponse(
        status_code=503, content={"detail": str(exc)}, headers={"Retry-After": str(exc.retry_after)}
    )


@app.exception_handler(LichessAuthError)
async def lichess_auth_handler(request: Request, exc: LichessAuthError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(LichessUnavailableError)
@app.exception_handler(EngineError)
@app.exception_handler(VectorStoreError)
async def unavailable_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/")
def hello():
    return {"message": "Hello World"}
