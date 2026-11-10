import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.logsbee import LogsbeeUserContext


class LogsbeeClient:
    """Small HTTP client for the Logsbee User Management API."""

    def __init__(self) -> None:
        self.base_url = settings.logsbee_user_api_base_url.rstrip("/")
        self.timeout = settings.logsbee_user_api_timeout_seconds

    def get_current_user(self, access_token: str) -> LogsbeeUserContext:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.get(
                    "/api/users/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                )

            if response.status_code in (401, 403):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired Logsbee access token",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if response.is_error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Logsbee User Management API returned an error",
                )

            try:
                return LogsbeeUserContext.model_validate(response.json())
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Logsbee returned an invalid user context",
                )

        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Logsbee User Management API timed out",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Logsbee User Management API is unavailable",
            )

    def get_member_summary(self, access_token: str, user_id) -> dict:
        """Fetch a same-account member identity from Logsbee."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.get(
                    f"/api/users/membership/{user_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if response.status_code in (401, 403):
                raise HTTPException(status_code=403, detail="Unable to verify target user access.")
            if response.status_code == 404:
                return {}
            if response.is_error:
                raise HTTPException(status_code=502, detail="Logsbee could not retrieve member details.")
            return response.json()
        except httpx.TimeoutException:
            raise HTTPException(status_code=503, detail="Logsbee User Management API timed out.")
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Logsbee User Management API is unavailable.")

    def verify_same_account_member(self, access_token: str, user_id) -> None:
        """Ask Logsbee to verify that a target user belongs to the caller's account."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.get(
                    f"/api/users/membership/{user_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if response.status_code in (401, 403):
                raise HTTPException(status_code=403, detail="Unable to verify target user's account membership.")
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Target user is not in your account.")
            if response.is_error:
                raise HTTPException(status_code=502, detail="Logsbee could not verify target user membership.")
        except httpx.TimeoutException:
            raise HTTPException(status_code=503, detail="Logsbee User Management API timed out.")
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Logsbee User Management API is unavailable.")


logsbee_client = LogsbeeClient()


    def request_two_factor_otp(self, access_token: str) -> dict:
        return self._two_factor_request(access_token, "POST", "/api/users/me/two-factor/email", {})

    def verify_two_factor_otp(self, access_token: str, otp: str) -> dict:
        return self._two_factor_request(access_token, "POST", "/api/users/me/two-factor/email", {"otp": otp})

    def disable_two_factor(self, access_token: str) -> dict:
        return self._two_factor_request(access_token, "DELETE", "/api/users/me/two-factor")

    def _two_factor_request(self, access_token: str, method: str, path: str, payload: dict | None = None) -> dict:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.request(
                    method, path,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=payload,
                )
            if response.status_code in (401, 403):
                raise HTTPException(status_code=response.status_code, detail="Logsbee rejected the two-factor verification request.")
            if response.is_error:
                try:
                    detail = response.json().get("detail", "Logsbee could not complete two-factor verification.")
                except ValueError:
                    detail = "Logsbee could not complete two-factor verification."
                raise HTTPException(status_code=response.status_code if response.status_code < 500 else 502, detail=detail)
            return response.json()
        except httpx.TimeoutException:
            raise HTTPException(status_code=503, detail="Logsbee User Management API timed out.")
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Logsbee User Management API is unavailable.")
