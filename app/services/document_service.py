import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentShare
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentCreate, DocumentUpdate


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
        document = Document(
            title=data.title.strip(),
            content=data.content,
            owner_user_id=uuid.UUID(user.id),
            account_id=account_id,
        )
        return DocumentRepository.create(db, document)

    @classmethod
    def list_for_user(cls, db: Session, user, access_token: str):
        account_id = cls._require_account(user)
        if cls._is_admin(user):
            documents = (
                db.query(Document)
                .filter(Document.account_id == account_id, Document.is_deleted.is_(False))
                .order_by(Document.updated_at.desc())
                .all()
            )
        else:
            documents = DocumentRepository.list_for_user(db, uuid.UUID(user.id), account_id)

        from app.integrations.logsbee.client import logsbee_client
        results = []
        current_user_id = uuid.UUID(user.id)
        for document in documents:
            item = {
                "id": document.id,
                "title": document.title,
                "content": document.content,
                "owner_user_id": document.owner_user_id,
                "account_id": document.account_id,
                "created_at": document.created_at,
                "updated_at": document.updated_at,
                "updated_by": document.updated_by,
                "shared_by_user_id": None,
                "shared_by_name": None,
            }
            share = DocumentRepository.get_share(db, document.id, current_user_id)
            if share:
                item["shared_by_user_id"] = share.shared_by_user_id
                member = logsbee_client.get_member_summary(access_token, share.shared_by_user_id)
                if member:
                    item["shared_by_name"] = " ".join(
                        part for part in [member.get("first_name"), member.get("last_name")] if part
                    ) or member.get("email")
            results.append(item)
        return results

    @classmethod
    def get(cls, db: Session, document_id: uuid.UUID, user):
        return cls._get_visible_document(db, document_id, user)

    @classmethod
    def update(cls, db: Session, document_id: uuid.UUID, data: DocumentUpdate, user):
        document = cls._get_visible_document(db, document_id, user)
        if not cls._can_manage(document, user):
            share = DocumentRepository.get_share(db, document.id, uuid.UUID(user.id))
            if share is None or share.edit_request_status != "approved":
                raise HTTPException(status_code=403, detail="Edit access has not been approved.")
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(document, field, value)
        document.updated_by = uuid.UUID(user.id)
        document.updated_at = datetime.now(timezone.utc)
        DocumentRepository.commit(db)
        db.refresh(document)
        return document

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
