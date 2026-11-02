import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = ""


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    owner_user_id: uuid.UUID
    account_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    updated_by: uuid.UUID | None = None


class DocumentShareCreate(BaseModel):
    user_id: uuid.UUID


class EditRequestDecision(BaseModel):
    decision: Literal["approved", "rejected"]


class DocumentShareResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    shared_with_user_id: uuid.UUID
    shared_by_user_id: uuid.UUID
    edit_request_status: str
    edit_approved_by: uuid.UUID | None
    edit_approved_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
