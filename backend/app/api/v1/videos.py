from fastapi import APIRouter, Depends, Path

from app.api.deps import get_youtube
from app.schemas import VideosResponse
from app.services.youtube import YouTubeService

router = APIRouter(tags=["videos"])



@router.get("/videos/{opening}", response_model=VideosResponse)
async def get_videos(
    opening: str = Path(..., min_length=2, max_length=120, description="Slug (espagnole), nom ou nom Lichess de l'ouverture"),
    youtube: YouTubeService = Depends(get_youtube),
):
    """Vidéos YouTube d'une ouverture (toujours 200, voir status)"""
    return await youtube.find_videos(opening)
