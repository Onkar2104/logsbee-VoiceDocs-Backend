from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.current_user import get_access_token, get_current_user
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
            two_factor_enabled=False,
        )
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


def _serialize(row: UserSettings, user: LogsbeeUserContext):
    return {
        "default_language": row.default_language,
        "transcription_language": row.default_language,
        "automatic_backup_enabled": row.automatic_backup_enabled,
        "two_factor_enabled": bool(user.is_two_factor_authenticated),
        "transcription_provider": settings.transcription_provider.strip().lower(),
    }


@router.get("/")
def get_preferences(db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    row = _get_or_create(db, user.id)
    row.two_factor_enabled = bool(user.is_two_factor_authenticated)
    db.commit()
    return _serialize(row, user)


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
    row.two_factor_enabled = bool(user.is_two_factor_authenticated)
    db.commit()
    db.refresh(row)
    return _serialize(row, user)



@router.post("/two-factor/request")
def request_two_factor_otp(
    access_token: str = Depends(get_access_token),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    from app.integrations.logsbee.client import logsbee_client
    if not user.is_email_verified:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Verify your email address before enabling two-factor authentication.")
    return logsbee_client.request_two_factor_otp(access_token)


class TwoFactorVerify(BaseModel):
    otp: str = Field(pattern=r"^[0-9]{6}$")


@router.post("/two-factor/verify")
def verify_two_factor_otp(
    payload: TwoFactorVerify,
    db: Session = Depends(get_db),
    access_token: str = Depends(get_access_token),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    from app.integrations.logsbee.client import logsbee_client
    result = logsbee_client.verify_two_factor_otp(access_token, payload.otp)
    row = _get_or_create(db, user.id)
    row.two_factor_enabled = True
    db.commit()
    return {"two_factor_enabled": True, "message": result.get("message", "Two-factor authentication enabled.")}


@router.delete("/two-factor")
def disable_two_factor(
    db: Session = Depends(get_db),
    access_token: str = Depends(get_access_token),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    from app.integrations.logsbee.client import logsbee_client
    result = logsbee_client.disable_two_factor(access_token)
    row = _get_or_create(db, user.id)
    row.two_factor_enabled = False
    db.commit()
    return {"two_factor_enabled": False, "message": result.get("message", "Two-factor authentication disabled.")}
