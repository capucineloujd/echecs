import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.api.v1 import evaluate, health, moves
from app.config import settings
from app.core.errors import (
    EngineError,
    InvalidFenError,
    LichessAuthError,
    LichessRateLimitError,
    LichessUnavailableError,
)
from app.services.lichess import LichessExplorerService
from app.services.stockfish import StockfishService


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
    yield
    await app.state.stockfish.stop()
    await app.state.lichess.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(moves.router, prefix=settings.api_v1_prefix)
app.include_router(evaluate.router, prefix=settings.api_v1_prefix)


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
async def unavailable_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/")
def hello():
    return {"message": "Hello World"}
