import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.google_drive import AudioRecording, GoogleDriveConnection, GoogleOAuthState
from app.services.docx_converter import html_to_docx, docx_to_html

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"


class GoogleDriveService:
    @staticmethod
    def _configured() -> None:
        if not all((settings.google_client_id, settings.google_client_secret,
                    settings.google_redirect_uri, settings.google_token_encryption_key)):
            raise HTTPException(status_code=503, detail="Google Drive integration is not configured.")

    @staticmethod
    def _fernet() -> Fernet:
        GoogleDriveService._configured()
        try:
            return Fernet(settings.google_token_encryption_key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=503, detail="Google token encryption key is invalid.") from exc

    @staticmethod
    def _user_id(value: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(status_code=400, detail="The authenticated user ID is not a valid UUID.") from exc

    @staticmethod
    def connection(db: Session, user_id: str) -> GoogleDriveConnection | None:
        return db.scalar(select(GoogleDriveConnection).where(
            GoogleDriveConnection.user_id == GoogleDriveService._user_id(user_id)
        ))

    @staticmethod
    def authorization_url(db: Session, user_id: str) -> str:
        GoogleDriveService._configured()
        state = secrets.token_urlsafe(40)
        db.query(GoogleOAuthState).filter(
            GoogleOAuthState.user_id == GoogleDriveService._user_id(user_id)
        ).delete(synchronize_session=False)
        db.add(GoogleOAuthState(
            state=state,
            user_id=GoogleDriveService._user_id(user_id),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        ))
        db.commit()
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email https://www.googleapis.com/auth/drive.file",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return AUTH_URL + "?" + urlencode(params)

    @staticmethod
    def _request_token(data: dict) -> dict:
        try:
            response = httpx.post(TOKEN_URL, data=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Google OAuth request failed.") from exc

    @staticmethod
    def _drive_request(method: str, url: str, token: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        try:
            response = httpx.request(method, url, headers=headers, timeout=90, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Google Drive request failed.") from exc

    @staticmethod
    def _create_folder(token: str) -> str:
        response = GoogleDriveService._drive_request(
            "POST", f"{DRIVE_API}/files", token,
            params={"fields": "id"},
            json={"name": "VoiceDocs Recordings", "mimeType": "application/vnd.google-apps.folder"},
        )
        return response.json()["id"]

    @staticmethod
    def complete_oauth(db: Session, code: str, state: str) -> str:
        GoogleDriveService._configured()
        record = db.get(GoogleOAuthState, state)
        if not record:
            raise HTTPException(status_code=400, detail="Google authorization state is invalid or expired.")
        expiry = record.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry < datetime.now(timezone.utc):
            db.delete(record)
            db.commit()
            raise HTTPException(status_code=400, detail="Google authorization state is invalid or expired.")
        user_id = record.user_id
        db.delete(record)
        db.commit()

        tokens = GoogleDriveService._request_token({
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
        access_token = tokens.get("access_token")
        if not access_token:
            raise HTTPException(status_code=502, detail="Google did not return an access token.")

        try:
            profile = httpx.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}, timeout=20,
            )
            profile.raise_for_status()
            email = profile.json().get("email", "Google account")
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Could not read the connected Google account.") from exc

        existing = db.scalar(select(GoogleDriveConnection).where(
            GoogleDriveConnection.user_id == user_id
        ))
        refresh_token = tokens.get("refresh_token")
        if not refresh_token and existing:
            refresh_token = GoogleDriveService._fernet().decrypt(
                existing.encrypted_refresh_token.encode()
            ).decode()
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Google did not return a refresh token. Reconnect and approve access.")

        folder_id = GoogleDriveService._create_folder(access_token)
        encrypted = GoogleDriveService._fernet().encrypt(refresh_token.encode()).decode()
        if existing:
            existing.google_email = email
            existing.encrypted_refresh_token = encrypted
            existing.recordings_folder_id = folder_id
        else:
            db.add(GoogleDriveConnection(
                user_id=user_id, google_email=email,
                encrypted_refresh_token=encrypted, recordings_folder_id=folder_id,
            ))
        db.commit()
        return email

    @staticmethod
    def _access_token(db: Session, connection: GoogleDriveConnection) -> str:
        try:
            refresh_token = GoogleDriveService._fernet().decrypt(
                connection.encrypted_refresh_token.encode()
            ).decode()
        except InvalidToken as exc:
            raise HTTPException(status_code=503, detail="Stored Google credentials cannot be decrypted. Reconnect Google Drive.") from exc
        tokens = GoogleDriveService._request_token({
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        token = tokens.get("access_token")
        if not token:
            raise HTTPException(status_code=502, detail="Google did not return an access token.")
        return token

    @staticmethod
    def upload_recording(
        db: Session, user_id: str, audio: bytes, filename: str, mime_type: str,
        duration: float | None = None, language: str | None = None,
        transcript: str | None = None,
    ) -> dict | None:
        connection = GoogleDriveService.connection(db, user_id)
        if not connection:
            return None
        token = GoogleDriveService._access_token(db, connection)
        safe_name = (filename or "recording.webm").replace("/", "_").replace(chr(92), "_")[:240]
        boundary = "voicedocs_" + secrets.token_hex(16)
        metadata = json.dumps({
            "name": safe_name, "parents": [connection.recordings_folder_id]
        }).encode("utf-8")
        marker = boundary.encode("ascii")
        body = (
            b"--" + marker + b"\r\n"
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            + metadata + b"\r\n"
            b"--" + marker + b"\r\n"
            + f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8")
            + audio + b"\r\n"
            b"--" + marker + b"--"
        )
        response = GoogleDriveService._drive_request(
            "POST", f"{UPLOAD_API}/files", token,
            params={"uploadType": "multipart", "fields": "id,name,mimeType,size"},
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            content=body,
        )
        remote = response.json()
        item = AudioRecording(
            user_id=GoogleDriveService._user_id(user_id),
            drive_file_id=remote["id"],
            file_name=remote.get("name", safe_name),
            mime_type=remote.get("mimeType", mime_type),
            file_size=int(remote.get("size", len(audio))),
            duration_seconds=duration, language=language, transcript=transcript,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return {"id": str(item.id), "file_name": item.file_name, "drive_file_id": item.drive_file_id, "backup_status": item.backup_status}

    @staticmethod
    def _documents_folder(db: Session, connection: GoogleDriveConnection, token: str) -> str:
        if connection.documents_folder_id:
            return connection.documents_folder_id
        response = GoogleDriveService._drive_request(
            "POST", f"{DRIVE_API}/files", token,
            params={"fields": "id"},
            json={"name": "VoiceDocs Documents", "mimeType": "application/vnd.google-apps.folder"},
        )
        connection.documents_folder_id = response.json()["id"]
        db.commit()
        return connection.documents_folder_id

    @staticmethod
    def upload_document(db: Session, owner_user_id: str, document_id: str, title: str, content: str) -> dict:
        connection = GoogleDriveService.connection(db, owner_user_id)
        if not connection:
            raise HTTPException(status_code=409, detail="Connect Google Drive before creating or saving a document.")
        token = GoogleDriveService._access_token(db, connection)
        folder_id = GoogleDriveService._documents_folder(db, connection, token)
        safe_title = (title or "Untitled document").replace("/", "_").replace(chr(92), "_").strip()[:220]
        filename = f"{safe_title or 'Untitled document'}.docx"
        docx_content = html_to_docx(content)
        boundary = "voicedocs_" + secrets.token_hex(16)
        marker = boundary.encode("ascii")
        metadata = json.dumps({
            "name": filename,
            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "parents": [folder_id],
        }).encode("utf-8")
        body = (
            b"--" + marker + b"\r\n"
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            + metadata + b"\r\n"
            b"--" + marker + b"\r\n"
            b"Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
            + docx_content + b"\r\n"
            b"--" + marker + b"--"
        )
        response = GoogleDriveService._drive_request(
            "POST", f"{UPLOAD_API}/files", token,
            params={"uploadType": "multipart", "fields": "id,name,webViewLink,mimeType"},
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            content=body,
        )
        return response.json()

    @staticmethod
    def update_drive_document(db: Session, owner_user_id: str, drive_file_id: str, title: str, content: str) -> dict:
        connection = GoogleDriveService.connection(db, owner_user_id)
        if not connection:
            raise HTTPException(status_code=409, detail="Reconnect the document owner's Google Drive to save changes.")
        token = GoogleDriveService._access_token(db, connection)
        safe_title = (title or "Untitled document").replace("/", "_").replace(chr(92), "_").strip()[:220]
        boundary = "voicedocs_" + secrets.token_hex(16)
        marker = boundary.encode("ascii")
        metadata = json.dumps({"name": f"{safe_title or 'Untitled document'}.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}).encode("utf-8")
        body = (
            b"--" + marker + b"\r\n"
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            + metadata + b"\r\n"
            b"--" + marker + b"\r\n"
            b"Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
            + html_to_docx(content) + b"\r\n"
            b"--" + marker + b"--"
        )
        response = GoogleDriveService._drive_request(
            "PATCH", f"{UPLOAD_API}/files/{drive_file_id}", token,
            params={"uploadType": "multipart", "fields": "id,name,webViewLink,mimeType"},
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            content=body,
        )
        return response.json()

    @staticmethod
    def download_document(db: Session, owner_user_id: str, drive_file_id: str) -> str:
        connection = GoogleDriveService.connection(db, owner_user_id)
        if not connection:
            raise HTTPException(status_code=409, detail="Reconnect the document owner's Google Drive to access this document.")
        token = GoogleDriveService._access_token(db, connection)
        metadata = GoogleDriveService._drive_request(
            "GET", f"{DRIVE_API}/files/{drive_file_id}", token,
            params={"fields": "mimeType,name"},
        ).json()
        response = GoogleDriveService._drive_request(
            "GET", f"{DRIVE_API}/files/{drive_file_id}", token, params={"alt": "media"}
        )
        # Read existing HTML backups during the transition; new saves convert
        # them to DOCX through update_drive_document.
        if metadata.get("mimeType") == "text/html" or (metadata.get("name") or "").lower().endswith(".html"):
            return response.content.decode("utf-8")
        return docx_to_html(response.content)

    @staticmethod
    def recordings(db: Session, user_id: str, page: int = 1, page_size: int = 10) -> dict:
        user_uuid = GoogleDriveService._user_id(user_id)
        base_query = select(AudioRecording).where(AudioRecording.user_id == user_uuid)
        total_records = db.scalar(
            select(func.count()).select_from(AudioRecording).where(AudioRecording.user_id == user_uuid)
        ) or 0
        items = list(db.scalars(
            base_query.order_by(AudioRecording.created_at.desc(), AudioRecording.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ))
        total_pages = (total_records + page_size - 1) // page_size
        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_records": total_records,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            },
        }

    @staticmethod
    def download(db: Session, user_id: str, recording_id: uuid.UUID) -> tuple[bytes, str, str]:
        item = db.scalar(select(AudioRecording).where(
            AudioRecording.id == recording_id,
            AudioRecording.user_id == GoogleDriveService._user_id(user_id),
        ))
        if not item:
            raise HTTPException(status_code=404, detail="Recording not found.")
        connection = GoogleDriveService.connection(db, user_id)
        if not connection:
            raise HTTPException(status_code=409, detail="Reconnect Google Drive to access this recording.")
        token = GoogleDriveService._access_token(db, connection)
        response = GoogleDriveService._drive_request(
            "GET", f"{DRIVE_API}/files/{item.drive_file_id}", token,
            params={"alt": "media"},
        )
        return response.content, item.file_name, item.mime_type

    @staticmethod
    def delete(db: Session, user_id: str, recording_id: uuid.UUID) -> None:
        item = db.scalar(select(AudioRecording).where(
            AudioRecording.id == recording_id,
            AudioRecording.user_id == GoogleDriveService._user_id(user_id),
        ))
        if not item:
            raise HTTPException(status_code=404, detail="Recording not found.")
        connection = GoogleDriveService.connection(db, user_id)
        if connection:
            token = GoogleDriveService._access_token(db, connection)
            GoogleDriveService._drive_request(
                "DELETE", f"{DRIVE_API}/files/{item.drive_file_id}", token
            )
        db.delete(item)
        db.commit()
