from fastapi import FastAPI

from app.api.v1 import health
from app.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(health.router, prefix=settings.api_v1_prefix)


@app.get("/")
def hello():
    return {"message": "Hello World"}
