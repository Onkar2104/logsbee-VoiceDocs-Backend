import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.current_user import get_access_token, get_current_user
from app.db.session import get_db
from app.schemas.document import (
    DocumentCreate, DocumentUpdate, DocumentResponse,
    DocumentShareCreate, DocumentShareResponse, EditRequestDecision,
)
from app.schemas.logsbee import LogsbeeUserContext
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(data: DocumentCreate, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.create(db, data, user)


@router.get("/", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.list_for_user(db, user)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.get(db, document_id, user)


@router.put("/{document_id}", response_model=DocumentResponse)
def update_document(document_id: uuid.UUID, data: DocumentUpdate, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.update(db, document_id, data, user)


@router.delete("/{document_id}")
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.delete(db, document_id, user)


@router.post("/{document_id}/shares", response_model=DocumentShareResponse, status_code=status.HTTP_201_CREATED)
def share_document(document_id: uuid.UUID, data: DocumentShareCreate, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user), token: str = Depends(get_access_token)):
    return DocumentService.share(db, document_id, data.user_id, user, token)


@router.post("/{document_id}/edit-requests", response_model=DocumentShareResponse)
def request_edit_access(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.request_edit(db, document_id, user)


@router.patch("/{document_id}/edit-requests/{target_user_id}", response_model=DocumentShareResponse)
def decide_edit_access(document_id: uuid.UUID, target_user_id: uuid.UUID, data: EditRequestDecision, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.decide_edit_request(db, document_id, target_user_id, data.decision, user)


@router.get("/{document_id}/shares", response_model=list[DocumentShareResponse])
def list_document_shares(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.list_shares(db, document_id, user)


@router.delete("/{document_id}/shares/{target_user_id}")
def revoke_document_share(document_id: uuid.UUID, target_user_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.revoke_share(db, document_id, target_user_id, user)
