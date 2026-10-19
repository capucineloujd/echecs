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
    """Conseil du coach en SSE (événements tool_start, tool_end, token, done ou error)"""
    fen = parse_fen(request.fen).fen()  # 422 si FEN invalide

    async def events():
        async for event in stream_agent(
            agent, fen, request.moves, request.question, settings.agent_timeout_seconds, settings.agent_max_steps
        ):
            name = event.pop("event")
            yield f"event: {name}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    # pour que nginx ne bufferise pas le flux
    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
