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
            response = getattr(exc, "response", None)
            google_error = ""
            if response is not None:
                try:
                    payload = response.json()
                    google_error = payload.get("error_description") or payload.get("error") or ""
                except ValueError:
                    google_error = ""
            reason = f" Google response: {google_error}." if google_error else ""
            status_code = response.status_code if response is not None else 502
            raise HTTPException(
                status_code=502,
                detail=f"Google OAuth token refresh failed (HTTP {status_code}).{reason}",
            ) from exc

    @staticmethod
    def _drive_request(method: str, url: str, token: str, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        try:
            response = httpx.request(method, url, headers=headers, timeout=90, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            response = getattr(exc, "response", None)
            google_error = ""
            if response is not None:
                try:
                    payload = response.json()
                    error_data = payload.get("error", {})
                    if isinstance(error_data, dict):
                        google_error = error_data.get("message") or error_data.get("status") or ""
                    elif isinstance(error_data, str):
                        google_error = error_data
                except ValueError:
                    google_error = ""
            reason = f" Google response: {google_error}." if google_error else ""
            status_code = response.status_code if response is not None else 502
            raise HTTPException(
                status_code=502,
                detail=f"Google Drive API request failed (HTTP {status_code}).{reason}",
            ) from exc

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
        transcript: str | None = None, document_id: uuid.UUID | None = None,
        recording_id: uuid.UUID | None = None,
    ) -> dict | None:
        connection = GoogleDriveService.connection(db, user_id)
        if not connection:
            return None
        token = GoogleDriveService._access_token(db, connection)
        safe_name = (filename or "recording.webm").replace("/", "_").replace(chr(92), "_")[:240]
        boundary = "voicedocs_" + secrets.token_hex(16)
        metadata = json.dumps({"name": safe_name, "parents": [connection.recordings_folder_id]}).encode("utf-8")
        marker = boundary.encode("ascii")
        body = (
            b"--" + marker + b"\r\n"
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n" + metadata + b"\r\n"
            b"--" + marker + b"\r\n"
            + f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8") + audio + b"\r\n"
            b"--" + marker + b"--"
        )
        response = GoogleDriveService._drive_request(
            "POST", f"{UPLOAD_API}/files", token,
            params={"uploadType": "multipart", "fields": "id,name,mimeType,size"},
            headers={"Content-Type": f"multipart/related; boundary={boundary}"}, content=body,
        )
        remote = response.json()
        item = db.get(AudioRecording, recording_id) if recording_id else None
        if item is None:
            item = AudioRecording(
                user_id=GoogleDriveService._user_id(user_id),
                document_id=document_id,
                file_name=remote.get("name", safe_name),
                mime_type=remote.get("mimeType", mime_type),
                file_size=int(remote.get("size", len(audio))),
                duration_seconds=duration, language=language, transcript=transcript,
            )
            db.add(item)
        item.drive_file_id = remote["id"]
        item.backup_status = "backed_up"
        item.last_backup_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(item)
        return {"id": str(item.id), "file_name": item.file_name,
                "drive_file_id": item.drive_file_id, "backup_status": item.backup_status}

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
    def upload_formatted_version(db: Session, owner_user_id: str, document_id: str, version_number: int, title: str, content_html: str) -> dict:
        """Create a separate DOCX file for one formatted document version."""
        return GoogleDriveService.upload_document(
            db,
            owner_user_id,
            f"{document_id}-formatted-v{version_number}",
            f"{title} - Formatted v{version_number}",
            content_html,
        )

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
        base_query = select(AudioRecording).where(AudioRecording.user_id == user_uuid, AudioRecording.is_deleted.is_(False))
        total_records = db.scalar(
            select(func.count()).select_from(AudioRecording).where(AudioRecording.user_id == user_uuid, AudioRecording.is_deleted.is_(False))
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
    def backup_recording(db: Session, user_id: str, recording_id: uuid.UUID) -> dict:
        item = db.scalar(select(AudioRecording).where(
            AudioRecording.id == recording_id,
            AudioRecording.user_id == GoogleDriveService._user_id(user_id),
            AudioRecording.is_deleted.is_(False),
        ))
        if not item:
            raise HTTPException(status_code=404, detail="Recording not found.")
        if item.backup_status == "backed_up" and item.drive_file_id:
            return {"backup_status": "backed_up", "message": "Recording is already backed up."}
        if item.file_data is None:
            raise HTTPException(status_code=409, detail="The database copy of this recording is unavailable.")
        saved = GoogleDriveService.upload_recording(
            db=db, user_id=user_id, audio=item.file_data, filename=item.file_name,
            mime_type=item.mime_type, duration=item.duration_seconds,
            language=item.language, transcript=item.transcript,
            document_id=item.document_id, recording_id=item.id,
        )
        if not saved:
            raise HTTPException(status_code=409, detail="Connect Google Drive to back up this recording.")
        return {"backup_status": "backed_up", "message": "Recording backed up to Google Drive."}

    @staticmethod
    def download(db: Session, user_id: str, recording_id: uuid.UUID) -> tuple[bytes, str, str]:
        item = db.scalar(select(AudioRecording).where(
            AudioRecording.id == recording_id,
            AudioRecording.user_id == GoogleDriveService._user_id(user_id),
        ))
        if not item:
            raise HTTPException(status_code=404, detail="Recording not found.")
        if item.file_data is not None:
            return item.file_data, item.file_name, item.mime_type
        connection = GoogleDriveService.connection(db, user_id)
        if not connection or not item.drive_file_id:
            raise HTTPException(status_code=409, detail="Recording is not backed up and its database copy is unavailable.")
        token = GoogleDriveService._access_token(db, connection)
        response = GoogleDriveService._drive_request(
            "GET", f"{DRIVE_API}/files/{item.drive_file_id}", token, params={"alt": "media"}
        )
        return response.content, item.file_name, item.mime_type

    @staticmethod
    def delete_drive_file(db: Session, owner_user_id: str, drive_file_id: str) -> None:
        """Permanently remove a VoiceDocs-owned backup from the document owner's Drive."""
        if not drive_file_id:
            return
        connection = GoogleDriveService.connection(db, owner_user_id)
        if not connection:
            raise HTTPException(
                status_code=409,
                detail="Reconnect the document owner's Google Drive to remove its backup.",
            )
        token = GoogleDriveService._access_token(db, connection)
        try:
            response = httpx.delete(
                f"{DRIVE_API}/files/{drive_file_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            # A missing file is already in the desired deleted state.
            if response.status_code == 404:
                return
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="A Google Drive backup could not be deleted.") from exc


    @staticmethod
    def _can_manage_recording(db: Session, item: AudioRecording, user) -> bool:
        if item.user_id == GoogleDriveService._user_id(user.id):
            return True
        if item.document_id:
            from app.models.document import Document
            from app.services.document_service import DocumentService
            document = db.query(Document).filter(
                Document.id == item.document_id,
                Document.account_id == DocumentService._require_account(user),
            ).first()
            return bool(document and DocumentService._is_admin(user))
        return False

    @staticmethod
    def trash_recording(db: Session, recording_id: uuid.UUID, user) -> dict:
        item = db.get(AudioRecording, recording_id)
        if not item or not GoogleDriveService._can_manage_recording(db, item, user):
            raise HTTPException(status_code=404, detail="Audio recording not found.")
        if item.is_deleted:
            raise HTTPException(status_code=409, detail="Audio recording is already in Trash.")
        item.is_deleted = True
        item.deleted_at = datetime.now(timezone.utc)
        item.deleted_by = GoogleDriveService._user_id(user.id)
        db.commit()
        return {"message": "Audio recording moved to Trash.", "id": item.id}

    @staticmethod
    def list_audio_trash(db: Session, user, page: int = 1, page_size: int = 10) -> dict:
        from app.models.document import Document
        from app.services.document_service import DocumentService
        account_id = DocumentService._require_account(user)
        query = db.query(AudioRecording).filter(AudioRecording.is_deleted.is_(True))
        if DocumentService._is_admin(user):
            query = query.outerjoin(Document, AudioRecording.document_id == Document.id).filter(
                (Document.account_id == account_id) | (AudioRecording.user_id == GoogleDriveService._user_id(user.id))
            )
        else:
            query = query.filter(AudioRecording.user_id == GoogleDriveService._user_id(user.id))
        total = query.count()
        items = query.order_by(AudioRecording.deleted_at.desc(), AudioRecording.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        pages = (total + page_size - 1) // page_size
        return {"items": [{
            "id": item.id, "file_name": item.file_name, "file_size": item.file_size,
            "mime_type": item.mime_type, "document_id": item.document_id,
            "deleted_at": item.deleted_at,
            "drive_cleanup_pending": bool(item.drive_file_id),
            "expires_at": item.deleted_at + timedelta(days=30) if item.deleted_at else None,
            "days_remaining": max(0, (30 - (datetime.now(timezone.utc) - (item.deleted_at.replace(tzinfo=timezone.utc) if item.deleted_at.tzinfo is None else item.deleted_at)).days)) if item.deleted_at else 30,
        } for item in items], "pagination": {
            "page": page, "page_size": page_size, "total_records": total,
            "total_pages": pages, "has_next": page < pages, "has_previous": page > 1,
        }}

    @staticmethod
    def restore_recording(db: Session, recording_id: uuid.UUID, user) -> dict:
        item = db.get(AudioRecording, recording_id)
        if not item or not item.is_deleted or not GoogleDriveService._can_manage_recording(db, item, user):
            raise HTTPException(status_code=404, detail="Deleted audio recording not found.")
        deleted_at = item.deleted_at.replace(tzinfo=timezone.utc) if item.deleted_at and item.deleted_at.tzinfo is None else item.deleted_at
        if deleted_at and deleted_at + timedelta(days=30) <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="The 30-day restore period has expired.")
        item.is_deleted = False
        item.deleted_at = None
        item.deleted_by = None
        db.commit()
        return {"message": "Audio recording restored.", "id": item.id}

    @staticmethod
    def permanently_delete_recording(db: Session, recording_id: uuid.UUID, user) -> dict:
        item = db.get(AudioRecording, recording_id)
        if not item or not item.is_deleted or not GoogleDriveService._can_manage_recording(db, item, user):
            raise HTTPException(status_code=404, detail="Deleted audio recording not found.")
        if item.drive_file_id:
            GoogleDriveService.delete_drive_file(db, str(item.user_id), item.drive_file_id)
        db.delete(item)
        db.commit()
        return {"message": "Audio recording permanently deleted."}

    @staticmethod
    def delete(db: Session, user_id: str, recording_id: uuid.UUID) -> None:
        item = db.scalar(select(AudioRecording).where(
            AudioRecording.id == recording_id,
            AudioRecording.user_id == GoogleDriveService._user_id(user_id),
            AudioRecording.is_deleted.is_(False),
        ))
        if not item:
            raise HTTPException(status_code=404, detail="Recording not found.")
        connection = GoogleDriveService.connection(db, user_id)
        if connection and item.drive_file_id:
            token = GoogleDriveService._access_token(db, connection)
            GoogleDriveService._drive_request(
                "DELETE", f"{DRIVE_API}/files/{item.drive_file_id}", token
            )
        db.delete(item)
        db.commit()
