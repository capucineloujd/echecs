import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.runner import stream_agent
from app.api.deps import get_agent
from app.config import settings
from app.core.chess_utils import parse_fen
from app.schemas import AgentRequest

router = APIRouter(tags=["agent"])


@router.post("/agent/analyze")
async def analyze(request: AgentRequest, agent=Depends(get_agent)):
    """Le coach (LLM local Ollama ou Mistral) analyse la position : il choisit ses outils (Lichess, Stockfish, articles, vidéos)
    puis rédige un conseil. Réponse en flux SSE :

    - `tool_start` / `tool_end` : outil appelé par l'agent ;
    - `token` : morceau de la réponse ;
    - `done` (liste des outils utilisés) ou `error` (message), toujours en dernier.
    """
    fen = parse_fen(request.fen).fen()  # FEN invalide : 422 avant d'ouvrir le flux

    async def events():
        async for event in stream_agent(
            agent, fen, request.moves, request.question, settings.agent_timeout_seconds, settings.agent_max_steps
        ):
            name = event.pop("event")
            yield f"event: {name}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    # X-Accel-Buffering : nginx transmet chaque événement immédiatement au lieu de bufferiser
    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
