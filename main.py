from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.me import router as me_router
from app.api.routes.documents import router as documents_router
from app.models.document import Document, DocumentShare
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="0.1.0",
)

# Browser origins are configured through CORS_ORIGINS in the environment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(me_router, prefix=settings.api_v1_prefix)
app.include_router(documents_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["Root"])
def root() -> dict[str, str]:
    return {"message": "Welcome to VoiceDocs API", "docs": "/docs"}
