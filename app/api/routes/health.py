from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Application liveness")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "voicedocs-api"}


@router.get("/health/ready", summary="Application readiness")
def readiness_check() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except SQLAlchemyError:
        # Do not expose database credentials or internal exception details.
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "database": "unavailable"},
        )
