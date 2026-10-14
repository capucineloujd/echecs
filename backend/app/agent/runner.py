"""Exécution de l'agent en flux d'événements, pour l'affichage au fil de l'eau dans l'interface."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError

logger = logging.getLogger(__name__)


def _text(content: Any) -> str:
    # Mistral renvoie une chaîne ; certains modèles renvoient une liste de blocs typés
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")


def _error_message(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "Le coach met trop de temps à répondre, réessaie."
    if isinstance(exc, GraphRecursionError):
        return "Le coach n'a pas réussi à conclure son analyse."
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401:
            return "Clé API Mistral invalide (MISTRAL_API_KEY)."
        if status == 429:
            return "Trop de demandes au modèle Mistral : réessaie dans une minute."
        return f"Le service Mistral a répondu une erreur {status}."
    if isinstance(exc, httpx.HTTPError):
        return "Service Mistral injoignable."
    return "Erreur inattendue du coach."


async def stream_agent(
    graph, fen: str, moves: list[str], question: str | None, timeout_seconds: float, max_steps: int
) -> AsyncIterator[dict[str, Any]]:
    """Événements : tool_start, tool_end, token, done, ou error (toujours en dernier)."""
    inputs = {"messages": [], "fen": fen, "moves": moves, "question": question, "steps": 0}
    config = {"recursion_limit": 2 * max_steps + 4}
    tools_used: list[str] = []
    try:
        async with asyncio.timeout(timeout_seconds):
            async for mode, chunk in graph.astream(inputs, config=config, stream_mode=["messages", "updates"]):
                if mode == "messages":
                    message, metadata = chunk
                    # Morceaux (AIMessageChunk) si le modèle streame, message complet sinon
                    if metadata.get("langgraph_node") == "agent" and isinstance(message, AIMessage):
                        if text := _text(message.content):
                            yield {"event": "token", "text": text}
                    continue
                for node, update in chunk.items():
                    if node == "agent":
                        for call in update["messages"][-1].tool_calls:
                            tools_used.append(call["name"])
                            yield {"event": "tool_start", "id": call["id"], "name": call["name"], "args": call["args"]}
                    elif node == "tools":
                        for message in update["messages"]:
                            yield {
                                "event": "tool_end",
                                "id": message.tool_call_id,
                                "name": message.name,
                                "status": message.status,
                            }
        yield {"event": "done", "tools_used": tools_used}
    except Exception as exc:  # le flux HTTP est déjà ouvert : l'erreur est envoyée comme un événement
        if isinstance(exc, (TimeoutError, httpx.HTTPError)):
            logger.warning("Agent en erreur : %r", exc)
        else:
            logger.exception("Agent en erreur")
        yield {"event": "error", "message": _error_message(exc)}
