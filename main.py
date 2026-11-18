import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.me import router as me_router
from app.api.routes.documents import router as documents_router
from app.api.routes.transcriptions import router as transcriptions_router
from app.api.routes.google_drive import router as google_drive_router
from app.api.routes.preferences import router as preferences_router
from app.models.document import Document, DocumentShare
from app.models.document_format_version import DocumentFormatVersion
from app.models.google_drive import AudioRecording, GoogleDriveConnection, GoogleOAuthState
from app.models.user_preferences import UserPreferences
from app.models.user_settings import UserSettings
from app.core.config import settings


logger = logging.getLogger(__name__)
_trash_purge_task = None


async def _purge_expired_trash_periodically():
    from app.db.session import SessionLocal
    from app.services.document_service import DocumentService

    while True:
        db = SessionLocal()
        try:
            result = DocumentService.purge_expired_trash(db)
            if any(result.values()):
                logger.info("Expired VoiceDocs Trash items permanently deleted: %s", result)
        except Exception:
            db.rollback()
            logger.exception("Scheduled VoiceDocs Trash cleanup failed")
        finally:
            db.close()
        await asyncio.sleep(3600)


app = FastAPI(title=settings.app_name, debug=settings.debug, version="0.1.0")


@app.on_event("startup")
async def start_trash_cleanup():
    global _trash_purge_task
    _trash_purge_task = asyncio.create_task(_purge_expired_trash_periodically())


@app.on_event("shutdown")
async def stop_trash_cleanup():
    global _trash_purge_task
    if _trash_purge_task:
        _trash_purge_task.cancel()
        try:
            await _trash_purge_task
        except asyncio.CancelledError:
            pass
        _trash_purge_task = None


app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(me_router, prefix=settings.api_v1_prefix)
app.include_router(documents_router, prefix=settings.api_v1_prefix)
app.include_router(transcriptions_router, prefix=settings.api_v1_prefix)
app.include_router(google_drive_router, prefix=settings.api_v1_prefix)
app.include_router(preferences_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["Root"])
def root() -> dict[str, str]:
    return {"message": "Welcome to VoiceDocs API", "docs": "/docs"}
