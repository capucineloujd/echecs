"""Agent coach : boucle ReAct LangGraph, le LLM choisit ses outils.

    START ──► agent ──(appels d'outils ?)──► tools ──┐
                ▲  └──(réponse finale)──► END       │
                └───────────────────────────────────┘

Au-delà de `max_steps` tours d'outils, l'agent est rappelé sans outils : il doit conclure.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.prompts import SYSTEM_PROMPT, describe_position


class AgentState(MessagesState):
    fen: str
    moves: list[str]
    question: str | None
    steps: int


def build_agent_graph(model: BaseChatModel, tools: list, max_steps: int = 4):
    model_with_tools = model.bind_tools(tools)

    async def agent(state: AgentState) -> dict[str, Any]:
        messages = state["messages"]
        new_messages = []
        if not messages:
            # Premier tour : la position est décrite une seule fois, puis gardée dans l'historique
            new_messages = [HumanMessage(describe_position(state["fen"], state.get("moves", []), state.get("question")))]
            messages = new_messages
        steps = state.get("steps", 0)
        llm = model_with_tools if steps < max_steps else model
        response = await llm.ainvoke([SystemMessage(SYSTEM_PROMPT), *messages])
        return {"messages": [*new_messages, response], "steps": steps + 1}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    # Une erreur d'outil (Lichess en panne...) est renvoyée au LLM, qui peut en choisir un autre
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition, ["tools", END])
    graph.add_edge("tools", "agent")
    return graph.compile()
