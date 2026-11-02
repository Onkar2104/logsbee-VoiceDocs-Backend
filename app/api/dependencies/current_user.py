from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.integrations.logsbee.client import logsbee_client
from app.schemas.logsbee import LogsbeeUserContext

bearer_scheme = HTTPBearer(auto_error=False)


def get_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def get_current_user(access_token: str = Depends(get_access_token)) -> LogsbeeUserContext:
    return logsbee_client.get_current_user(access_token)
