import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentShare
from app.models.document_format_version import DocumentFormatVersion
from app.models.google_drive import AudioRecording
from app.models.user_settings import UserSettings
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.services.google_drive_service import GoogleDriveService
from app.services.legal_document_catalog import validate_document_metadata


class DocumentService:
    @staticmethod
    def _automatic_backup_enabled(db: Session, user_id: uuid.UUID) -> bool:
        row = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        return row.automatic_backup_enabled if row else True

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
        try:
            legal_metadata = validate_document_metadata(
                data.formatting_mode, data.jurisdiction, data.legal_category, data.document_type
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        remote = None
        if cls._automatic_backup_enabled(db, uuid.UUID(user.id)):
            try:
                remote = GoogleDriveService.upload_document(db, user.id, str(document_id), title, data.content)
            except HTTPException:
                remote = None
        document = Document(
            id=document_id,
            title=title,
            content=data.content,
            **legal_metadata,
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
    def list_for_user(cls, db: Session, user, access_token: str, scope: str = "my", page: int = 1, page_size: int = 10, search: str | None = None, legal_category: str | None = None, document_type: str | None = None):
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

        # Build filter choices from the complete scope before applying active filters.
        filter_rows = query.with_entities(Document.legal_category, Document.document_type).distinct().all()
        available_filters = {
            "legal_categories": sorted({row[0] for row in filter_rows if row[0]}),
            "document_types": sorted({row[1] for row in filter_rows if row[1]}),
        }

        if search and search.strip():
            term = search.strip()
            query = query.filter(
                Document.title.ilike(f"%{term}%")
                | Document.content.ilike(f"%{term}%")
            )
        if legal_category:
            query = query.filter(Document.legal_category == legal_category)
        if document_type:
            query = query.filter(Document.document_type == document_type)

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
                "formatting_mode": document.formatting_mode,
                "jurisdiction": document.jurisdiction,
                "legal_category": document.legal_category,
                "document_type": document.document_type,
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
            "filters": available_filters,
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
        # Database content is canonical. Fetch from Drive only for legacy records
        # created before database fallback storage was introduced.
        if not document.content and document.drive_file_id:
            try:
                document.content = GoogleDriveService.download_document(
                    db, str(document.owner_user_id), document.drive_file_id
                )
                # Backfill legacy Drive-only documents into the database once.
                db.commit()
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
            # Hydrate legacy Drive-only records before attempting an update.
            original_content = cls._with_content(db, document).content
            try:
                if document.drive_file_id:
                    remote = GoogleDriveService.update_drive_document(
                        db, str(document.owner_user_id), document.drive_file_id, document.title, original_content
                    )
                else:
                    remote = GoogleDriveService.upload_document(
                        db, str(document.owner_user_id), str(document.id), document.title, original_content
                    )
            except HTTPException:
                raise HTTPException(status_code=502, detail="Google Drive is unavailable. Your document remains safely stored in VoiceDocs.")
            if not remote:
                raise HTTPException(status_code=409, detail="Connect Google Drive to back up this document.")
            document.drive_file_id = remote["id"]
            document.drive_web_view_link = remote.get("webViewLink") or document.drive_web_view_link
            document.content = original_content
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
        metadata_fields = {"formatting_mode", "jurisdiction", "legal_category", "document_type"}
        if metadata_fields.intersection(changes):
            candidate = {
                "formatting_mode": changes.get("formatting_mode", document.formatting_mode),
                "jurisdiction": changes.get("jurisdiction", document.jurisdiction),
                "legal_category": changes.get("legal_category", document.legal_category),
                "document_type": changes.get("document_type", document.document_type),
            }
            try:
                changes.update(validate_document_metadata(
                    candidate["formatting_mode"], candidate["jurisdiction"],
                    candidate["legal_category"], candidate["document_type"],
                ))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        title = changes.get("title", document.title)
        content = changes.get("content")
        if content is None:
            content = cls._with_content(db, document).content
        document.title = title
        document.content = content
        document.backup_status = "not_backed_up"
        document.updated_by = uuid.UUID(user.id)
        document.updated_at = datetime.now(timezone.utc)

        # Commit the canonical VoiceDocs copy before attempting Google Drive.
        # Network failures must not prevent the user's document edits from saving.
        DocumentRepository.commit(db)
        db.refresh(document)

        if cls._automatic_backup_enabled(db, document.owner_user_id):
            try:
                if document.drive_file_id:
                    remote = GoogleDriveService.update_drive_document(
                        db, str(document.owner_user_id), document.drive_file_id, title, content
                    )
                else:
                    remote = GoogleDriveService.upload_document(
                        db, str(document.owner_user_id), str(document.id), title, content
                    )
                if remote:
                    document.drive_file_id = remote["id"]
                    document.drive_web_view_link = remote.get("webViewLink") or document.drive_web_view_link
                    document.backup_status = "backed_up"
                    document.last_backup_at = datetime.now(timezone.utc)
                    DocumentRepository.commit(db)
                    db.refresh(document)
            except HTTPException:
                db.rollback()
                document = DocumentRepository.get_active_by_id(db, document_id)
        return cls._with_content(db, document)

    @classmethod
    def _get_account_document(cls, db: Session, document_id: uuid.UUID, user, include_deleted: bool = False):
        account_id = cls._require_account(user)
        query = db.query(Document).filter(Document.id == document_id, Document.account_id == account_id)
        if not include_deleted:
            query = query.filter(Document.is_deleted.is_(False))
        document = query.first()
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        if not cls._can_manage(document, user):
            raise HTTPException(status_code=403, detail="Only the document owner or Account Admin can manage this document.")
        return document

    @classmethod
    def _delete_document_drive_backups(cls, db: Session, document: Document) -> list[str]:
        """Delete linked Drive files, retaining failed IDs for a safe retry."""
        failures = []
        versions = db.query(DocumentFormatVersion).filter(
            DocumentFormatVersion.document_id == document.id
        ).all()
        recordings = db.query(AudioRecording).filter(AudioRecording.document_id == document.id).all()
        targets = [(document, document.drive_file_id)]
        targets.extend((version, version.drive_file_id) for version in versions)
        targets.extend((recording, recording.drive_file_id) for recording in recordings)
        for row, file_id in targets:
            if not file_id:
                continue
            owner_id = str(document.owner_user_id) if row is document or isinstance(row, DocumentFormatVersion) else str(row.user_id)
            try:
                GoogleDriveService.delete_drive_file(db, owner_id, file_id)
                row.drive_file_id = None
                if hasattr(row, "drive_web_view_link"):
                    row.drive_web_view_link = None
                if hasattr(row, "backup_status"):
                    row.backup_status = "not_backed_up"
            except HTTPException:
                failures.append(file_id)
        db.commit()
        return failures

    @classmethod
    def delete(cls, db: Session, document_id: uuid.UUID, user):
        document = cls._get_account_document(db, document_id, user)
        document.is_deleted = True
        document.deleted_at = datetime.now(timezone.utc)
        document.deleted_by = uuid.UUID(user.id)
        db.commit()
        return {"message": "Document moved to Trash.", "restore_days": 30}

    @classmethod
    def list_trash(cls, db: Session, user, page: int = 1, page_size: int = 10):
        account_id = cls._require_account(user)
        query = db.query(Document).filter(Document.account_id == account_id, Document.is_deleted.is_(True))
        if not cls._is_admin(user):
            query = query.filter(Document.owner_user_id == uuid.UUID(user.id))
        total = query.count()
        items = query.order_by(Document.deleted_at.desc(), Document.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        pages = (total + page_size - 1) // page_size
        return {
            "items": [{
                "id": item.id, "title": item.title, "owner_user_id": item.owner_user_id,
                "deleted_at": item.deleted_at, "deleted_by": item.deleted_by,
                "drive_cleanup_pending": False,
                "expires_at": item.deleted_at + __import__("datetime").timedelta(days=30) if item.deleted_at else None,
                "days_remaining": max(0, 30 - ((datetime.now(timezone.utc) - (item.deleted_at.replace(tzinfo=timezone.utc) if item.deleted_at and item.deleted_at.tzinfo is None else item.deleted_at)).days)) if item.deleted_at else 30,
                "created_at": item.created_at, "updated_at": item.updated_at,
            } for item in items],
            "pagination": {
                "page": page, "page_size": page_size, "total_records": total,
                "total_pages": pages, "has_next": page < pages, "has_previous": page > 1,
            },
        }

    @classmethod
    def restore_document(cls, db: Session, document_id: uuid.UUID, user):
        document = cls._get_account_document(db, document_id, user, include_deleted=True)
        if not document.is_deleted:
            raise HTTPException(status_code=409, detail="Document is not in Trash.")
        deleted_at = document.deleted_at.replace(tzinfo=timezone.utc) if document.deleted_at and document.deleted_at.tzinfo is None else document.deleted_at
        if deleted_at and deleted_at + __import__("datetime").timedelta(days=30) <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="The 30-day restore period has expired.")
        document.is_deleted = False
        document.deleted_at = None
        document.deleted_by = None
        document.backup_status = "not_backed_up" if not document.drive_file_id else document.backup_status
        db.commit()
        return {"message": "Document restored successfully.", "id": document.id}

    @classmethod
    def permanently_delete_document(cls, db: Session, document_id: uuid.UUID, user):
        document = cls._get_account_document(db, document_id, user, include_deleted=True)
        if not document.is_deleted:
            raise HTTPException(status_code=409, detail="Move the document to Trash before permanently deleting it.")
        failures = cls._delete_document_drive_backups(db, document)
        if failures:
            raise HTTPException(status_code=502, detail=f"{len(failures)} Google Drive backup(s) could not be deleted. Retry permanent deletion after reconnecting Google Drive.")
        db.query(AudioRecording).filter(AudioRecording.document_id == document.id).delete(synchronize_session=False)
        document.active_format_version_id = None
        db.flush()
        db.delete(document)
        db.commit()
        return {"message": "Document permanently deleted."}

    @classmethod
    def list_deleted_versions(cls, db: Session, document_id: uuid.UUID, user):
        document = cls._get_account_document(db, document_id, user, include_deleted=True)
        versions = db.query(DocumentFormatVersion).filter(
            DocumentFormatVersion.document_id == document.id,
            DocumentFormatVersion.is_deleted.is_(True),
        ).order_by(DocumentFormatVersion.deleted_at.desc()).all()
        return {"items": [{
            "id": item.id, "version_number": item.version_number,
            "deleted_at": item.deleted_at, "created_at": item.created_at,
        } for item in versions]}

    @classmethod
    def delete_version(cls, db: Session, document_id: uuid.UUID, version_id: uuid.UUID, user):
        document = cls._get_account_document(db, document_id, user)
        version = db.query(DocumentFormatVersion).filter(
            DocumentFormatVersion.id == version_id,
            DocumentFormatVersion.document_id == document.id,
            DocumentFormatVersion.is_deleted.is_(False),
        ).first()
        if version is None:
            raise HTTPException(status_code=404, detail="Formatted version not found.")
        if document.active_format_version_id == version.id:
            raise HTTPException(status_code=409, detail="Select another formatted version before moving the active version to Trash.")
        version.is_deleted = True
        version.deleted_at = datetime.now(timezone.utc)
        version.deleted_by = uuid.UUID(user.id)
        db.commit()
        return {"message": "Formatted version moved to Trash."}

    @classmethod
    def restore_version(cls, db: Session, document_id: uuid.UUID, version_id: uuid.UUID, user):
        document = cls._get_account_document(db, document_id, user)
        version = db.query(DocumentFormatVersion).filter(
            DocumentFormatVersion.id == version_id,
            DocumentFormatVersion.document_id == document.id,
            DocumentFormatVersion.is_deleted.is_(True),
        ).first()
        if version is None:
            raise HTTPException(status_code=404, detail="Deleted formatted version not found.")
        deleted_at = version.deleted_at.replace(tzinfo=timezone.utc) if version.deleted_at and version.deleted_at.tzinfo is None else version.deleted_at
        if deleted_at and deleted_at + __import__("datetime").timedelta(days=30) <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="The 30-day restore period has expired.")
        version.is_deleted = False
        version.deleted_at = None
        version.deleted_by = None
        version.backup_status = "not_backed_up" if not version.drive_file_id else version.backup_status
        db.commit()
        return {"message": "Formatted version restored.", "id": version.id}

    @classmethod
    def permanently_delete_version(cls, db: Session, document_id: uuid.UUID, version_id: uuid.UUID, user):
        document = cls._get_account_document(db, document_id, user)
        version = db.query(DocumentFormatVersion).filter(
            DocumentFormatVersion.id == version_id,
            DocumentFormatVersion.document_id == document.id,
            DocumentFormatVersion.is_deleted.is_(True),
        ).first()
        if version is None:
            raise HTTPException(status_code=404, detail="Deleted formatted version not found.")
        if version.drive_file_id:
            GoogleDriveService.delete_drive_file(db, str(document.owner_user_id), version.drive_file_id)
        db.delete(version)
        db.commit()
        return {"message": "Formatted version permanently deleted."}


    @classmethod
    def list_all_deleted_versions(cls, db: Session, user):
        account_id = cls._require_account(user)
        query = db.query(DocumentFormatVersion, Document).join(
            Document, Document.id == DocumentFormatVersion.document_id
        ).filter(
            Document.account_id == account_id,
            DocumentFormatVersion.is_deleted.is_(True),
            Document.is_deleted.is_(False),
        )
        if not cls._is_admin(user):
            query = query.filter(Document.owner_user_id == uuid.UUID(user.id))
        rows = query.order_by(DocumentFormatVersion.deleted_at.desc()).limit(500).all()
        now = datetime.now(timezone.utc)
        items = []
        for version, document in rows:
            deleted_at = version.deleted_at.replace(tzinfo=timezone.utc) if version.deleted_at and version.deleted_at.tzinfo is None else version.deleted_at
            days = max(0, 30 - (now - deleted_at).days) if deleted_at else 30
            items.append({
                "id": version.id, "document_id": document.id, "document_title": document.title,
                "version_number": version.version_number, "deleted_at": version.deleted_at,
                "expires_at": deleted_at + __import__("datetime").timedelta(days=30) if deleted_at else None,
                "days_remaining": days, "drive_cleanup_pending": bool(version.drive_file_id),
            })
        return {"items": items}

    @classmethod
    def purge_expired_trash(cls, db: Session) -> dict:
        now = datetime.now(timezone.utc)
        cutoff = now - __import__("datetime").timedelta(days=30)
        deleted_documents = deleted_audio = deleted_versions = 0
        documents = db.query(Document).filter(
            Document.is_deleted.is_(True), Document.deleted_at <= cutoff
        ).all()
        for document in documents:
            failures = cls._delete_document_drive_backups(db, document)
            if failures:
                continue
            db.query(AudioRecording).filter(AudioRecording.document_id == document.id).delete(synchronize_session=False)
            document.active_format_version_id = None
            db.flush()
            db.delete(document)
            db.commit()
            deleted_documents += 1

        versions = db.query(DocumentFormatVersion).join(
            Document, Document.id == DocumentFormatVersion.document_id
        ).filter(
            DocumentFormatVersion.is_deleted.is_(True),
            DocumentFormatVersion.deleted_at <= cutoff,
            Document.is_deleted.is_(False),
        ).all()
        for version in versions:
            document = db.get(Document, version.document_id)
            if version.drive_file_id:
                try:
                    GoogleDriveService.delete_drive_file(db, str(document.owner_user_id), version.drive_file_id)
                except HTTPException:
                    continue
            db.delete(version)
            db.commit()
            deleted_versions += 1

        audio_items = db.query(AudioRecording).filter(
            AudioRecording.is_deleted.is_(True), AudioRecording.deleted_at <= cutoff
        ).all()
        for audio in audio_items:
            if audio.drive_file_id:
                try:
                    GoogleDriveService.delete_drive_file(db, str(audio.user_id), audio.drive_file_id)
                except HTTPException:
                    continue
            db.delete(audio)
            db.commit()
            deleted_audio += 1
        return {"documents": deleted_documents, "audio": deleted_audio, "versions": deleted_versions}

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
