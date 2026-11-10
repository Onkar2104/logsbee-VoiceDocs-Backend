from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.current_user import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.schemas.logsbee import LogsbeeUserContext
from app.models.user_preferences import UserPreferences
from app.models.user_settings import UserSettings

router = APIRouter(prefix="/preferences", tags=["User preferences"])


class PreferencesUpdate(BaseModel):
    transcription_language: str | None = Field(default=None, min_length=2, max_length=12, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]+)?$")
    default_language: str | None = Field(default=None, min_length=2, max_length=12, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]+)?$")
    automatic_backup_enabled: bool | None = None


def _get_or_create(db: Session, user_id):
    settings_row = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings_row is None:
        legacy = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
        settings_row = UserSettings(
            user_id=user_id,
            default_language=legacy.transcription_language if legacy else "en",
            automatic_backup_enabled=True,
        )
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


def _serialize(row: UserSettings):
    return {
        "default_language": row.default_language,
        "transcription_language": row.default_language,
        "automatic_backup_enabled": row.automatic_backup_enabled,
        "transcription_provider": settings.transcription_provider.strip().lower(),
    }


@router.get("/")
def get_preferences(db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    row = _get_or_create(db, user.id)
    return _serialize(row)


@router.put("/")
def update_preferences(
    payload: PreferencesUpdate,
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    row = _get_or_create(db, user.id)
    language = payload.default_language or payload.transcription_language
    if language:
        row.default_language = language
    if payload.automatic_backup_enabled is not None:
        row.automatic_backup_enabled = payload.automatic_backup_enabled
    db.commit()
    db.refresh(row)
    return _serialize(row, user)


