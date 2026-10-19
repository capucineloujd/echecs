from fastapi import APIRouter, Depends

from app.api.deps import get_catalog
from app.rag.catalog import OpeningCatalog
from app.schemas import OpeningRef

router = APIRouter(tags=["openings"])


@router.get("/openings", response_model=list[OpeningRef])
async def list_openings(catalog: OpeningCatalog = Depends(get_catalog)):
    """Liste des ouverture du catalogue"""
    return [
        OpeningRef(slug=o.slug, name=o.name, eco=o.eco, moves=o.moves, fen=o.fen)
        for o in sorted(catalog.openings.values(), key=lambda o: o.eco)
    ]
