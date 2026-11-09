from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.current_user import get_current_user
from app.db.session import get_db
from app.schemas.logsbee import LogsbeeUserContext
from app.models.user_preferences import UserPreferences

router = APIRouter(prefix="/preferences", tags=["User preferences"])


class PreferencesUpdate(BaseModel):
    transcription_language: str = Field(min_length=2, max_length=12, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]+)?$")


def _get_or_create(db: Session, user_id):
    preferences = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    if preferences is None:
        preferences = UserPreferences(user_id=user_id, transcription_language="en")
        db.add(preferences)
        db.commit()
        db.refresh(preferences)
    return preferences


@router.get("/")
def get_preferences(
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    preferences = _get_or_create(db, user.id)
    return {"transcription_language": preferences.transcription_language}


@router.put("/")
def update_preferences(
    payload: PreferencesUpdate,
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    preferences = _get_or_create(db, user.id)
    preferences.transcription_language = payload.transcription_language
    db.commit()
    db.refresh(preferences)
    return {"transcription_language": preferences.transcription_language}
