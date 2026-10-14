import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import ollama
from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError

from app.config import settings

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
            return "Clé API du modèle de langage invalide."
        if status == 429:
            return "Trop de demandes au modèle de langage : réessaie dans une minute."
        return f"Le modèle de langage a répondu une erreur {status}."
    if isinstance(exc, ollama.ResponseError):
        if exc.status_code == 404:
            return f"Modèle absent d'Ollama : lancer 'ollama pull {settings.ollama_model}'."
        return f"Ollama a répondu une erreur : {exc.error}"
    if isinstance(exc, (httpx.HTTPError, ConnectionError)):
        return "Modèle de langage injoignable (Ollama est-il lancé sur la machine ?)."
    return "Erreur inattendue du coach."


async def stream_agent(
    graph, fen: str, moves: list[str], question: str | None, timeout_seconds: float, max_steps: int
) -> AsyncIterator[dict[str, Any]]:
    inputs = {"messages": [], "fen": fen, "moves": moves, "question": question, "steps": 0}
    config = {"recursion_limit": 2 * max_steps + 4}
    tools_used: list[str] = []
    try:
        async with asyncio.timeout(timeout_seconds):
            async for mode, chunk in graph.astream(inputs, config=config, stream_mode=["messages", "updates"]):
                if mode == "messages":
                    message, metadata = chunk
                    # Seul le nœud de rédaction est streamé (pas le JSON des décisions)
                    if metadata.get("langgraph_node") == "answer" and isinstance(message, AIMessage):
                        if text := _text(message.content):
                            yield {"event": "token", "text": text}
                    continue
                for node, update in chunk.items():
                    if node in ("read_position", "decide") and update.get("messages"):
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
        if isinstance(exc, (TimeoutError, httpx.HTTPError, ConnectionError, ollama.ResponseError)):
            logger.warning("Agent en erreur : %r", exc)
        else:
            logger.exception("Agent en erreur")
        yield {"event": "error", "message": _error_message(exc)}
