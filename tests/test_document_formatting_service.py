import os

# The application settings object is loaded at import time.
_TEST_SETTINGS = {
    "APP_NAME": "VoiceDocs tests",
    "API_V1_PREFIX": "/api",
    "ENVIRONMENT": "test",
    "DEBUG": "false",
    "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/voicedocs_test",
    "LOGSBEE_USER_API_BASE_URL": "http://localhost:8000/api",
    "LOGSBEE_USER_API_TIMEOUT_SECONDS": "5",
    "CORS_ORIGINS": "http://localhost:5173",
    "GOOGLE_CLIENT_ID": "test-client",
    "GOOGLE_CLIENT_SECRET": "test-secret",
    "GOOGLE_REDIRECT_URI": "http://localhost/callback",
    "GOOGLE_TOKEN_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    "FRONTEND_APP_URL": "http://localhost:5173",
    "TRANSCRIPTION_PROVIDER": "browser",
    "WHISPER_MODEL_SIZE": "small",
    "WHISPER_DEVICE": "cpu",
    "WHISPER_COMPUTE_TYPE": "int8",
    "WHISPER_CPU_THREADS": "1",
    "WHISPER_BATCH_SIZE": "1",
    "INDICCONFORMER_DEVICE": "cpu",
}
for _key, _value in _TEST_SETTINGS.items():
    os.environ.setdefault(_key, _value)

import pytest
from fastapi import HTTPException

from app.services.document_formatting_service import DocumentFormattingService, sanitize_editor_html


def test_sanitizer_keeps_supported_formatting_and_removes_unsafe_markup():
    html, plain = sanitize_editor_html(
        '<h2>Meeting</h2><p><strong>मराठी</strong> text <script>alert(1)</script></p>'
    )

    assert "<h2>Meeting</h2>" in html
    assert "<strong>मराठी</strong>" in html
    assert "<script>" not in html
    assert "alert(1)" not in plain
    assert "मराठी" in plain


def test_sanitizer_removes_javascript_links():
    html, _ = sanitize_editor_html('<p><a href="javascript:alert(1)">open</a></p>')

    assert "javascript:" not in html
    assert "<a>" in html


def test_sanitizer_preserves_small_embedded_images_and_rejects_remote_images():
    pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/WioAAAAASUVORK5CYII="
    html, plain = sanitize_editor_html(
        f'<p>Before</p><img src="data:image/png;base64,{pixel}" alt="sample"><p>After</p>'
    )
    assert f'data:image/png;base64,{pixel}' in html
    assert "Before" in plain and "After" in plain

    remote_html, _ = sanitize_editor_html(
        '<p>Text</p><img src="https://example.com/image.png">'
    )
    assert "<img" not in remote_html


def test_docx_backup_embeds_sanitized_image():
    from io import BytesIO
    from zipfile import ZipFile

    from app.services.docx_converter import html_to_docx

    pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/WioAAAAASUVORK5CYII="
    output = html_to_docx(f'<p>Image:</p><img src="data:image/png;base64,{pixel}">')
    with ZipFile(BytesIO(output)) as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())


def test_sanitizer_rejects_empty_content():
    with pytest.raises(HTTPException) as error:
        sanitize_editor_html("<p><br></p>")

    assert error.value.status_code == 422


def test_structured_output_validation_preserves_non_english_text():
    result = DocumentFormattingService._validate_result({
        "blocks": [
            {"type": "heading", "text": "बैठक"},
            {"type": "paragraph", "text": "आजची बैठक उद्या सकाळी आहे."},
        ]
    })

    assert result["blocks"][0]["text"] == "बैठक"
    assert result["blocks"][1]["text"] == "आजची बैठक उद्या सकाळी आहे."


def test_structured_output_rejects_unknown_block_type():
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService._validate_result({
            "blocks": [{"type": "script", "text": "bad"}]
        })

    assert error.value.status_code == 502

def test_document_and_format_version_relationships_are_unambiguous():
    from sqlalchemy.orm import configure_mappers

    from app.models.document import Document
    from app.models.document_format_version import DocumentFormatVersion

    configure_mappers()
    assert hasattr(Document, "format_versions")
    assert hasattr(Document, "active_format_version")
    assert hasattr(DocumentFormatVersion, "document")

def test_formatted_docx_backup_preserves_headings_lists_and_inline_emphasis():
    from io import BytesIO

    from docx import Document

    from app.services.docx_converter import html_to_docx

    output = html_to_docx(
        "<h1>बैठक</h1><p><strong>महत्त्वाचे</strong> मुद्दे</p>"
        "<ul><li>पहिला मुद्दा</li><li>दुसरा मुद्दा</li></ul>"
    )
    document = Document(BytesIO(output))

    assert document.paragraphs[0].style.name == "Heading 1"
    assert document.paragraphs[0].text == "बैठक"
    assert document.paragraphs[1].text == "महत्त्वाचे मुद्दे"
    assert document.paragraphs[1].runs[0].bold is True
    assert document.paragraphs[2].style.name == "List Bullet"
    assert document.paragraphs[2].text == "पहिला मुद्दा"
    assert document.paragraphs[3].style.name == "List Bullet"
    assert document.paragraphs[3].text == "दुसरा मुद्दा"



def test_format_edit_permissions_allow_owner_account_admin_and_approved_share(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.api.routes.documents import _require_format_edit_access
    from app.repositories.document_repository import DocumentRepository
    from app.services.document_service import DocumentService

    owner_id = uuid4()
    admin_id = uuid4()
    editor_id = uuid4()
    viewer_id = uuid4()
    document = SimpleNamespace(owner_user_id=owner_id, id=uuid4())
    db = object()

    owner = SimpleNamespace(id=str(owner_id), role=SimpleNamespace(name="user"))
    account_admin = SimpleNamespace(id=str(admin_id), role=SimpleNamespace(name="admin"))
    approved_editor = SimpleNamespace(id=str(editor_id), role=SimpleNamespace(name="user"))
    view_only = SimpleNamespace(id=str(viewer_id), role=SimpleNamespace(name="user"))

    shares = {
        editor_id: SimpleNamespace(edit_request_status="approved"),
        viewer_id: SimpleNamespace(edit_request_status="pending"),
    }
    monkeypatch.setattr(
        DocumentRepository,
        "get_share",
        lambda _db, _document_id, target_id: shares.get(target_id),
    )

    assert DocumentService._can_manage(document, owner)
    assert DocumentService._can_manage(document, account_admin)
    _require_format_edit_access(db, document, owner)
    _require_format_edit_access(db, document, account_admin)
    _require_format_edit_access(db, document, approved_editor)

    with pytest.raises(HTTPException) as error:
        _require_format_edit_access(db, document, view_only)
    assert error.value.status_code == 403


def test_super_admin_role_is_not_treated_as_account_admin():
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services.document_service import DocumentService

    document = SimpleNamespace(owner_user_id=uuid4())
    super_admin = SimpleNamespace(id=str(uuid4()), role=SimpleNamespace(name="Super admin"))
    assert DocumentService._can_manage(document, super_admin) is False
