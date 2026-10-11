"""Graphe LangGraph de recherche documentaire sur les ouvertures.

                  ┌──► find_videos ─────────────────────────► END
    detect_opening┤
                  └──► retrieve ──┬──► format_results ──► END
                          ▲       │
                          └─ widen_search (si le filtre par ouverture ne donne rien)

Les deux branches s'exécutent en parallèle.
"""

from typing import TYPE_CHECKING, TypedDict

from langgraph.graph import END, START, StateGraph

from app.rag.catalog import OpeningCatalog, OpeningInfo
from app.schemas import VideosResponse
from app.services.vector_store import VectorStoreService

if TYPE_CHECKING:
    # Évite de charger torch à l'import du module
    from app.services.embeddings import EmbeddingService
    from app.services.youtube import YouTubeService


class RagState(TypedDict, total=False):
    query: str
    opening: str | None  # ouverture demandée explicitement (slug ou nom)
    top_k: int
    min_score: float
    include_videos: bool
    detected: OpeningInfo | None
    filter_slug: str | None
    widened: bool
    hits: list[dict]
    results: list[dict]
    context: str
    videos: VideosResponse | None


def build_rag_graph(
    embedder: "EmbeddingService",
    store: VectorStoreService,
    catalog: OpeningCatalog,
    youtube: "YouTubeService | None" = None,
):
    async def detect_opening(state: RagState) -> RagState:
        explicit = state.get("opening")
        detected = catalog.get(explicit) if explicit else catalog.detect(state["query"])
        return {"detected": detected, "filter_slug": detected.slug if detected else None, "widened": False}

    async def retrieve(state: RagState) -> RagState:
        vector = await embedder.aembed_query(state["query"])
        # On demande un peu plus que top_k : le formatage filtre ensuite les doublons et scores faibles
        hits = await store.asearch(vector, top_k=state["top_k"] * 2, opening_slug=state.get("filter_slug"))
        return {"hits": hits}

    async def find_videos(state: RagState) -> RagState:
        # Vidéos seulement si une ouverture est identifiée : une requête vague coûterait du quota pour rien
        detected = state.get("detected")
        if youtube is None or detected is None or not state.get("include_videos", True):
            return {"videos": None}
        return {"videos": await youtube.find_videos(detected.slug)}

    async def widen_search(state: RagState) -> RagState:
        return {"filter_slug": None, "widened": True}

    def route_after_retrieve(state: RagState) -> str:
        relevant = [h for h in state["hits"] if h["score"] >= state["min_score"]]
        if not relevant and state.get("filter_slug") and not state.get("widened"):
            return "widen_search"
        return "format_results"

    async def format_results(state: RagState) -> RagState:
        seen, results = set(), []
        for hit in sorted(state["hits"], key=lambda h: h["score"], reverse=True):
            if hit["score"] < state["min_score"] or hit["text"] in seen:
                continue
            seen.add(hit["text"])
            results.append({**hit, "score": round(hit["score"], 4)})
            if len(results) == state["top_k"]:
                break

        # Contexte prêt à être injecté dans le prompt d'un LLM (étape suivante)
        context = "\n\n".join(
            f"[{i}] {r['opening_name']} ({r['eco']}) — {r['section']} — source : {r['url']}\n{r['text']}"
            for i, r in enumerate(results, start=1)
        )
        return {"results": results, "context": context}

    graph = StateGraph(RagState)
    graph.add_node("detect_opening", detect_opening)
    graph.add_node("retrieve", retrieve)
    graph.add_node("find_videos", find_videos)
    graph.add_node("widen_search", widen_search)
    graph.add_node("format_results", format_results)

    graph.add_edge(START, "detect_opening")
    graph.add_edge("detect_opening", "retrieve")
    graph.add_edge("detect_opening", "find_videos")
    graph.add_edge("find_videos", END)
    graph.add_conditional_edges("retrieve", route_after_retrieve, ["widen_search", "format_results"])
    graph.add_edge("widen_search", "retrieve")
    graph.add_edge("format_results", END)
    return graph.compile()
