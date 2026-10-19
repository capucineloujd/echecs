from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_rag_graph
from app.config import settings
from app.schemas import OpeningRef, VectorSearchResponse

router = APIRouter(tags=["rag"])


@router.get("/vector-search", response_model=VectorSearchResponse)
async def vector_search(
    query: str = Query(..., min_length=2, max_length=500, description="Question ou nom d'ouverture"),
    opening: str | None = Query(None, description="Restreindre à une ouverture (slug ou nom, ex: espagnole)"),
    top_k: int = Query(settings.rag_top_k, ge=1, le=20),
    videos: bool = Query(True, description="Proposer des vidéos YouTube sur l'ouverture détectée"),
    graph=Depends(get_rag_graph),
):
    """Recherche dans les articles indexé dans Milvus"""
    state = await graph.ainvoke(
        {
            "query": query,
            "opening": opening,
            "top_k": top_k,
            "min_score": settings.rag_min_score,
            "include_videos": videos,
        }
    )
    detected = state.get("detected")
    return VectorSearchResponse(
        query=query,
        detected_opening=OpeningRef(**{k: v for k, v in asdict(detected).items() if k not in ("aliases", "name_en")}) if detected else None,
        filtered_by_opening=bool(detected) and not state.get("widened", False),
        results=state["results"],
        context=state["context"],
        videos=state.get("videos"),
    )
