from fastapi import APIRouter
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/healthcheck")
def healthcheck():
    return {"status": "ok", "service": settings.app_name, "env": settings.app_env}
