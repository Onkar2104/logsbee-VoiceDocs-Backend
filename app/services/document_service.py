import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentShare
from app.models.google_drive import AudioRecording
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.services.google_drive_service import GoogleDriveService


class DocumentService:
    @staticmethod
    def _is_admin(user) -> bool:
        return bool(user.role and user.role.name.strip().lower() == "admin")

    @staticmethod
    def _require_account(user) -> uuid.UUID:
        if not user.account_id:
            raise HTTPException(status_code=403, detail="An account-scoped user is required.")
        return uuid.UUID(user.account_id)

    @classmethod
    def _can_manage(cls, document: Document, user) -> bool:
        return document.owner_user_id == uuid.UUID(user.id) or cls._is_admin(user)

    @classmethod
    def _get_visible_document(cls, db: Session, document_id: uuid.UUID, user) -> Document:
        account_id = cls._require_account(user)
        document = DocumentRepository.get_active_by_id(db, document_id)
        if document is None or document.account_id != account_id:
            raise HTTPException(status_code=404, detail="Document not found.")
        if cls._can_manage(document, user):
            return document
        share = DocumentRepository.get_share(db, document.id, uuid.UUID(user.id))
        if share is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        return document

    @classmethod
    def create(cls, db: Session, data: DocumentCreate, user):
        account_id = cls._require_account(user)
        document_id = uuid.uuid4()
        title = data.title.strip()
        remote = None
        try:
            remote = GoogleDriveService.upload_document(db, user.id, str(document_id), title, data.content)
        except HTTPException:
            remote = None
        document = Document(
            id=document_id,
            title=title,
            content="" if remote else data.content,
            owner_user_id=uuid.UUID(user.id),
            account_id=account_id,
            drive_file_id=remote.get("id") if remote else None,
            drive_web_view_link=remote.get("webViewLink") if remote else None,
            backup_status="backed_up" if remote else "not_backed_up",
            last_backup_at=datetime.now(timezone.utc) if remote else None,
        )
        try:
            db.add(document)
            db.commit()
            db.refresh(document)
            return cls._with_content(db, document)
        except Exception:
            db.rollback()
            raise

    @classmethod
    def list_for_user(cls, db: Session, user, access_token: str, scope: str = "my", page: int = 1, page_size: int = 10):
        account_id = cls._require_account(user)
        current_user_id = uuid.UUID(user.id)

        query = db.query(Document).filter(
            Document.account_id == account_id,
            Document.is_deleted.is_(False),
        )
        if scope == "my":
            query = query.filter(Document.owner_user_id == current_user_id)
        elif scope == "shared":
            query = (
                query.join(DocumentShare, DocumentShare.document_id == Document.id)
                .filter(DocumentShare.shared_with_user_id == current_user_id)
            )
        elif scope == "shared_by_me":
            query = (
                query.join(DocumentShare, DocumentShare.document_id == Document.id)
                .filter(DocumentShare.shared_by_user_id == current_user_id)
                .distinct()
            )
        else:
            raise HTTPException(status_code=400, detail="Scope must be 'my', 'shared', or 'shared_by_me'.")

        total_records = query.order_by(None).count()
        documents = (
            query.order_by(Document.updated_at.desc(), Document.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        from app.integrations.logsbee.client import logsbee_client
        results = []
        member_cache = {}
        for document in documents:
            item = {
                "id": document.id,
                "title": document.title,
                "content": document.content,
                "backup_status": document.backup_status,
                "drive_web_view_link": document.drive_web_view_link,
                "audio_backup_status": "not_backed_up" if db.query(AudioRecording.id).filter(AudioRecording.document_id == document.id, AudioRecording.backup_status != "backed_up").count() else "backed_up",
                "owner_user_id": document.owner_user_id,
                "account_id": document.account_id,
                "created_at": document.created_at,
                "updated_at": document.updated_at,
                "updated_by": document.updated_by,
                "shared_by_user_id": None,
                "shared_by_name": None,
            }
            if scope == "shared":
                share = DocumentRepository.get_share(db, document.id, current_user_id)
                if share:
                    item["shared_by_user_id"] = share.shared_by_user_id
                    sender_id = str(share.shared_by_user_id)
                    if sender_id not in member_cache:
                        member_cache[sender_id] = logsbee_client.get_member_summary(
                            access_token, share.shared_by_user_id
                        )
                    member = member_cache[sender_id]
                    if member:
                        item["shared_by_name"] = " ".join(
                            part for part in [member.get("first_name"), member.get("last_name")] if part
                        ) or member.get("email")
            results.append(item)
        total_pages = (total_records + page_size - 1) // page_size
        return {
            "items": results,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_records": total_records,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            },
        }


    @classmethod
    def get_sharing_summary(cls, db: Session, user):
        account_id = cls._require_account(user)
        current_user_id = uuid.UUID(user.id)
        shared_by_me_count = (
            db.query(Document.id)
            .join(DocumentShare, DocumentShare.document_id == Document.id)
            .filter(
                Document.account_id == account_id,
                Document.is_deleted.is_(False),
                DocumentShare.shared_by_user_id == current_user_id,
            )
            .distinct()
            .count()
        )
        return {"shared_by_me_count": shared_by_me_count}

    @classmethod
    def _with_content(cls, db: Session, document: Document) -> Document:
        if document.drive_file_id:
            try:
                document.content = GoogleDriveService.download_document(
                    db, str(document.owner_user_id), document.drive_file_id
                )
            except HTTPException:
                if not document.content:
                    raise
        pending_audio = db.query(AudioRecording.id).filter(
            AudioRecording.document_id == document.id,
            AudioRecording.backup_status != "backed_up",
        ).count()
        document.audio_backup_status = "not_backed_up" if pending_audio else "backed_up"
        return document

    @classmethod
    def backup(cls, db: Session, document_id: uuid.UUID, user):
        document = cls._get_visible_document(db, document_id, user)
        if not cls._can_manage(document, user):
            raise HTTPException(status_code=403, detail="Only the owner or Account Admin can back up this document.")
        if document.backup_status != "backed_up":
            try:
                if document.drive_file_id:
                    remote = GoogleDriveService.update_drive_document(
                        db, str(document.owner_user_id), document.drive_file_id, document.title, document.content
                    )
                else:
                    remote = GoogleDriveService.upload_document(
                        db, str(document.owner_user_id), str(document.id), document.title, document.content
                    )
            except HTTPException:
                raise HTTPException(status_code=502, detail="Google Drive is unavailable. Your document remains safely stored in VoiceDocs.")
            if not remote:
                raise HTTPException(status_code=409, detail="Connect Google Drive to back up this document.")
            document.drive_file_id = remote["id"]
            document.drive_web_view_link = remote.get("webViewLink") or document.drive_web_view_link
            document.content = ""
            document.backup_status = "backed_up"
            document.last_backup_at = datetime.now(timezone.utc)
            db.commit()
        audio_items = db.query(AudioRecording).filter(
            AudioRecording.document_id == document.id,
            AudioRecording.backup_status != "backed_up",
        ).all()
        audio_backed_up = 0
        for audio in audio_items:
            try:
                saved = GoogleDriveService.upload_recording(
                    db=db, user_id=str(audio.user_id), audio=audio.file_data or b"",
                    filename=audio.file_name, mime_type=audio.mime_type,
                    duration=audio.duration_seconds, language=audio.language,
                    transcript=audio.transcript, document_id=document.id, recording_id=audio.id,
                )
                if saved:
                    audio_backed_up += 1
            except HTTPException:
                db.rollback()
        audio_pending = db.query(AudioRecording).filter(
            AudioRecording.document_id == document.id,
            AudioRecording.backup_status != "backed_up",
        ).count()
        return {"backed_up": audio_pending == 0, "backup_status": document.backup_status, "audio_backup_status": "not_backed_up" if audio_pending else "backed_up", "audio_backed_up": audio_backed_up, "audio_pending": audio_pending}

    @classmethod
    def get(cls, db: Session, document_id: uuid.UUID, user):
        document = cls._get_visible_document(db, document_id, user)
        return cls._with_content(db, document)

    @classmethod
    def update(cls, db: Session, document_id: uuid.UUID, data: DocumentUpdate, user):
        document = cls._get_visible_document(db, document_id, user)
        if not cls._can_manage(document, user):
            share = DocumentRepository.get_share(db, document.id, uuid.UUID(user.id))
            if share is None or share.edit_request_status != "approved":
                raise HTTPException(status_code=403, detail="Edit access has not been approved.")
        changes = data.model_dump(exclude_unset=True)
        title = changes.get("title", document.title)
        content = changes.get("content")
        if content is None:
            content = cls._with_content(db, document).content
        remote = None
        try:
            if document.drive_file_id:
                remote = GoogleDriveService.update_drive_document(
                    db, str(document.owner_user_id), document.drive_file_id, title, content
                )
            else:
                remote = GoogleDriveService.upload_document(
                    db, str(document.owner_user_id), str(document.id), title, content
                )
        except HTTPException:
            remote = None
        document.title = title
        if remote:
            document.drive_file_id = remote["id"]
            document.content = ""
            document.drive_web_view_link = remote.get("webViewLink") or document.drive_web_view_link
            document.backup_status = "backed_up"
            document.last_backup_at = datetime.now(timezone.utc)
        else:
            document.content = content
            document.backup_status = "not_backed_up"
        document.updated_by = uuid.UUID(user.id)
        document.updated_at = datetime.now(timezone.utc)
        DocumentRepository.commit(db)
        db.refresh(document)
        return cls._with_content(db, document)

    @classmethod
    def delete(cls, db: Session, document_id: uuid.UUID, user):
        document = cls._get_visible_document(db, document_id, user)
        if not cls._can_manage(document, user):
            raise HTTPException(status_code=403, detail="Only the document owner or Account Admin can delete it.")
        document.is_deleted = True
        document.deleted_at = datetime.now(timezone.utc)
        document.deleted_by = uuid.UUID(user.id)
        DocumentRepository.commit(db)
        return {"message": "Document deleted successfully."}

    @classmethod
    def share(cls, db: Session, document_id: uuid.UUID, target_user_id: uuid.UUID, user, access_token: str):
        document = cls._get_visible_document(db, document_id, user)
        if not cls._can_manage(document, user):
            raise HTTPException(status_code=403, detail="Only the owner or Account Admin can share this document.")
        if target_user_id == document.owner_user_id:
            raise HTTPException(status_code=400, detail="The document owner already has access.")
        from app.integrations.logsbee.client import logsbee_client
        logsbee_client.verify_same_account_member(access_token, target_user_id)
        existing = DocumentRepository.get_share(db, document.id, target_user_id)
        if existing:
            raise HTTPException(status_code=409, detail="Document is already shared with this user.")
        share = DocumentShare(
            document_id=document.id,
            shared_with_user_id=target_user_id,
            shared_by_user_id=uuid.UUID(user.id),
        )
        try:
            return DocumentRepository.create_share(db, share)
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Document is already shared with this user.")

    @classmethod
    def request_edit(cls, db: Session, document_id: uuid.UUID, user):
        document = cls._get_visible_document(db, document_id, user)
        share = DocumentRepository.get_share(db, document.id, uuid.UUID(user.id))
        if share is None:
            raise HTTPException(status_code=403, detail="Only a shared user can request edit access.")
        if share.edit_request_status == "approved":
            raise HTTPException(status_code=409, detail="Edit access is already approved.")
        if share.edit_request_status == "pending":
            raise HTTPException(status_code=409, detail="An edit request is already pending.")
        share.edit_request_status = "pending"
        DocumentRepository.commit(db)
        db.refresh(share)
        return share

    @classmethod
    def decide_edit_request(cls, db: Session, document_id: uuid.UUID, target_user_id: uuid.UUID, decision: str, user):
        document = cls._get_visible_document(db, document_id, user)
        if not cls._can_manage(document, user):
            raise HTTPException(status_code=403, detail="Only the owner or Account Admin can review edit requests.")
        share = DocumentRepository.get_share(db, document.id, target_user_id)
        if share is None or share.edit_request_status != "pending":
            raise HTTPException(status_code=404, detail="Pending edit request not found.")
        share.edit_request_status = decision
        share.edit_approved_by = uuid.UUID(user.id) if decision == "approved" else None
        share.edit_approved_at = datetime.now(timezone.utc) if decision == "approved" else None
        DocumentRepository.commit(db)
        db.refresh(share)
        return share

    @classmethod
    def list_shares(cls, db: Session, document_id: uuid.UUID, user):
        document = cls._get_visible_document(db, document_id, user)
        if not cls._can_manage(document, user):
            raise HTTPException(status_code=403, detail="Only the owner or Account Admin can view sharing settings.")
        return DocumentRepository.list_shares(db, document.id)

    @classmethod
    def revoke_share(cls, db: Session, document_id: uuid.UUID, target_user_id: uuid.UUID, user):
        document = cls._get_visible_document(db, document_id, user)
        if not cls._can_manage(document, user):
            raise HTTPException(status_code=403, detail="Only the owner or Account Admin can revoke sharing.")
        share = DocumentRepository.get_share(db, document.id, target_user_id)
        if share is None:
            raise HTTPException(status_code=404, detail="Document share not found.")
        DocumentRepository.delete_share(db, share)
        return {"message": "Document access revoked successfully."}
