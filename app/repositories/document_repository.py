import uuid

from sqlalchemy.orm import Session

from app.models.document import Document, DocumentShare


class DocumentRepository:
    @staticmethod
    def create(db: Session, document: Document) -> Document:
        db.add(document)
        db.commit()
        db.refresh(document)
        return document

    @staticmethod
    def get_active_by_id(db: Session, document_id: uuid.UUID) -> Document | None:
        return db.query(Document).filter(
            Document.id == document_id,
            Document.is_deleted.is_(False),
        ).first()

    @staticmethod
    def list_for_user(db: Session, user_id: uuid.UUID, account_id: uuid.UUID) -> list[Document]:
        return (
            db.query(Document)
            .outerjoin(DocumentShare, DocumentShare.document_id == Document.id)
            .filter(
                Document.account_id == account_id,
                Document.is_deleted.is_(False),
                (Document.owner_user_id == user_id) | (DocumentShare.shared_with_user_id == user_id),
            )
            .distinct()
            .order_by(Document.updated_at.desc())
            .all()
        )

    @staticmethod
    def get_share(db: Session, document_id: uuid.UUID, user_id: uuid.UUID) -> DocumentShare | None:
        return db.query(DocumentShare).filter(
            DocumentShare.document_id == document_id,
            DocumentShare.shared_with_user_id == user_id,
        ).first()

    @staticmethod
    def create_share(db: Session, share: DocumentShare) -> DocumentShare:
        db.add(share)
        db.commit()
        db.refresh(share)
        return share

    @staticmethod
    def list_shares(db: Session, document_id: uuid.UUID) -> list[DocumentShare]:
        return db.query(DocumentShare).filter(DocumentShare.document_id == document_id).order_by(DocumentShare.created_at.desc()).all()

    @staticmethod
    def delete_share(db: Session, share: DocumentShare) -> None:
        db.delete(share)
        db.commit()

    @staticmethod
    def commit(db: Session) -> None:
        db.commit()
