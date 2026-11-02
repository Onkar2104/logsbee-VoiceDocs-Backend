from fastapi import APIRouter, Depends

from app.api.dependencies.current_user import get_current_user
from app.schemas.logsbee import LogsbeeUserContext

router = APIRouter(tags=["Authentication"])


@router.get("/me", response_model=LogsbeeUserContext, summary="Get authenticated user")
def read_current_user(
    current_user: LogsbeeUserContext = Depends(get_current_user),
) -> LogsbeeUserContext:
    return current_user
