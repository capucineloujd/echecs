"""Agent coach : LangGraph, le LLM choisit ses outils.

    START ──► read_position ──► tools ──► decide ──(outil choisi)──► tools ──┐
                                            ▲  └──(« répondre »)──► answer ──► END
                                            └─────────────────────────────────┘

- read_position : la lecture de la position (get_position_moves : théorie Lichess ou
  Stockfish) est garantie au départ.
- decide : à chaque tour, le LLM DOIT choisir explicitement (sortie structurée) un outil
  ou « répondre ». Plus fiable qu'un appel d'outil facultatif avec un petit modèle local,
  qui a tendance à répondre sans vérifier.
- answer : le LLM rédige le conseil (streamé) à partir des résultats d'outils.
- Au-delà de `max_steps` décisions, ou si un outil est redemandé à l'identique : réponse.
"""

import logging
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, Field, ValidationError

from app.agent.prompts import ANSWER_PROMPT, DECISION_PROMPT, describe_position

logger = logging.getLogger(__name__)

FIRST_TOOL = "get_position_moves"
# Argument attendu par chaque outil que le LLM peut choisir
TOOL_ARGUMENTS = {"evaluate_position": "move_san", "search_opening_knowledge": "query", "find_videos": "opening"}


class Decision(BaseModel):
    """Prochaine étape de l'agent."""

    reason: str = Field(description="Pourquoi cette étape, en une phrase courte")
    tool: Literal["evaluate_position", "search_opening_knowledge", "find_videos", "answer"]
    argument: str | None = Field(
        None, description="Coup à vérifier (evaluate_position), requête (search_opening_knowledge) ou ouverture (find_videos)"
    )


class AgentState(MessagesState):
    fen: str
    moves: list[str]
    question: str | None
    steps: int
    ready: bool


def build_agent_graph(model: BaseChatModel, tools: list, max_steps: int = 4):
    decider = model.with_structured_output(Decision)

    async def read_position(state: AgentState) -> dict[str, Any]:
        question = HumanMessage(describe_position(state["fen"], state.get("moves", []), state.get("question")))
        call = AIMessage(content="", tool_calls=[{"name": FIRST_TOOL, "args": {}, "id": "read_position"}])
        return {"messages": [question, call], "steps": 0, "ready": False}

    async def decide(state: AgentState) -> dict[str, Any]:
        steps = state.get("steps", 0)
        if steps >= max_steps:
            return {"ready": True}
        try:
            decision: Decision = await decider.ainvoke([SystemMessage(DECISION_PROMPT), *state["messages"]])
        except (OutputParserException, ValidationError) as exc:
            # Décision illisible (JSON invalide) : on répond avec ce qu'on a plutôt que d'échouer
            logger.warning("Décision de l'agent illisible, passage à la réponse : %s", exc)
            return {"ready": True, "steps": steps + 1}
        if decision is None or decision.tool == "answer":
            return {"ready": True, "steps": steps + 1}

        args = {TOOL_ARGUMENTS[decision.tool]: decision.argument} if decision.argument else {}
        already_done = any(
            isinstance(m, AIMessage) and any(c["name"] == decision.tool and c["args"] == args for c in m.tool_calls)
            for m in state["messages"]
        )
        if already_done:
            return {"ready": True, "steps": steps + 1}
        call = {"name": decision.tool, "args": args, "id": f"step-{steps}"}
        return {"messages": [AIMessage(content="", tool_calls=[call])], "steps": steps + 1}

    async def answer(state: AgentState) -> dict[str, Any]:
        messages = [SystemMessage(ANSWER_PROMPT), *_as_text(state["messages"]), _reminder(state)]
        response = await model.ainvoke(messages)
        return {"messages": [response]}

    def route(state: AgentState) -> str:
        return "answer" if state.get("ready") else "tools"

    graph = StateGraph(AgentState)
    graph.add_node("read_position", read_position)
    graph.add_node("decide", decide)
    graph.add_node("answer", answer)
    # Une erreur d'outil (Lichess en panne...) devient un résultat, que le LLM voit au tour suivant
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "read_position")
    graph.add_edge("read_position", "tools")
    graph.add_edge("tools", "decide")
    graph.add_conditional_edges("decide", route, ["tools", "answer"])
    graph.add_edge("answer", END)
    return graph.compile()


def _reminder(state: AgentState) -> HumanMessage:
    """Rappel placé en dernier (là où un petit modèle est le plus attentif) : les faits
    établis par l'analyse de départ, que la réponse ne doit pas contredire."""
    analysis = next((m.content for m in state["messages"] if isinstance(m, ToolMessage)), "")
    facts = [line for line in analysis.splitlines() if line.startswith(("Source choisie", "Ouverture", "Coup de référence"))]
    in_theory = analysis.startswith("Source choisie : théorie")
    question = state.get("question") or "que dois-je jouer ici, et pourquoi ?"
    return HumanMessage(
        "Rappel avant de rédiger :\n"
        + "\n".join(facts)
        + f"\nLa position de l'élève est {'dans la théorie' if in_theory else 'sortie de la théorie'}."
        + f"\nQuestion de l'élève : {question}\nRédige maintenant ta réponse."
    )


def _as_text(messages: list) -> list:
    """Pour la rédaction, les appels d'outils deviennent du texte simple : le modèle n'a plus
    d'outils à ce stade, et certains refusent un historique d'appels sans outils déclarés."""
    converted = []
    for message in messages:
        if isinstance(message, ToolMessage):
            converted.append(HumanMessage(f"Résultat de l'outil {message.name} :\n{message.content}"))
        elif isinstance(message, AIMessage) and message.tool_calls:
            continue
        else:
            converted.append(message)
    return converted
