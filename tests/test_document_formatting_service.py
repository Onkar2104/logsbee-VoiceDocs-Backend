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
    pixel = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg=="
    html, plain = sanitize_editor_html(
        f'<p>Before</p><img src="data:image/png;base64,{pixel}" alt="sample"><p>After</p>'
    )
    assert f'data:image/png;base64,{pixel}' in html
    assert "</img>" not in html
    assert "Before" in plain and "After" in plain

    remote_html, _ = sanitize_editor_html(
        '<p>Text</p><img src="https://example.com/image.png">'
    )
    assert "<img" not in remote_html


def test_embedded_images_keep_their_original_position_after_formatting(monkeypatch):
    import json
    import httpx
    from app.core.config import settings

    pixel = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg=="
    original = f'<p>Before image</p><img src="data:image/png;base64,{pixel}" alt="diagram"><p>After image</p>'
    source, images = DocumentFormattingService.prepare_source_with_image_placeholders(original)

    assert "Before image" in source
    assert "After image" in source
    marker = next(iter(images))
    assert source.index("Before image") < source.index(marker) < source.index("After image")

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    class FormattedResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "blocks": [
                    {"type": "paragraph", "text": "Before image"},
                    {"type": "paragraph", "text": marker},
                    {"type": "paragraph", "text": "After image"},
                ]
            })}]}}]}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: FormattedResponse())
    _, formatted_html = DocumentFormattingService.format_transcript(source)
    restored = DocumentFormattingService.restore_embedded_images(formatted_html, images)

    assert restored.index("Before image") < restored.index("<img") < restored.index("After image")
    assert f'data:image/png;base64,{pixel}' in restored


def test_image_restoration_rejects_missing_or_duplicated_placeholder():
    image = '<img src="data:image/png;base64,valid">'
    with pytest.raises(HTTPException) as missing:
        DocumentFormattingService.restore_embedded_images("<p>Text</p>", {"VOICEDOCS_EMBEDDED_IMAGE_0000": image})
    assert missing.value.status_code == 502

    with pytest.raises(HTTPException) as duplicated:
        DocumentFormattingService.restore_embedded_images(
            "<p>VOICEDOCS_EMBEDDED_IMAGE_0000 VOICEDOCS_EMBEDDED_IMAGE_0000</p>",
            {"VOICEDOCS_EMBEDDED_IMAGE_0000": image},
        )
    assert duplicated.value.status_code == 502


def test_docx_backup_embeds_sanitized_image():
    from io import BytesIO
    from zipfile import ZipFile

    from app.services.docx_converter import html_to_docx

    pixel = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg=="
    output = html_to_docx(f'<p>Image:</p><img src="data:image/png;base64,{pixel}">')
    with ZipFile(BytesIO(output)) as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())


def test_sanitizer_rejects_empty_content():
    with pytest.raises(HTTPException) as error:
        sanitize_editor_html("<p><br></p>")

    assert error.value.status_code == 422


def test_formatted_html_groups_consecutive_numbered_and_bulleted_items():
    html = DocumentFormattingService._to_html({
        "blocks": [
            {"type": "number", "text": "पहिला मुद्दा"},
            {"type": "number", "text": "दुसरा मुद्दा"},
            {"type": "bullet", "text": "उपमुद्दा अ"},
            {"type": "bullet", "text": "उपमुद्दा ब"},
            {"type": "number", "text": "तिसरा मुद्दा"},
        ]
    })

    assert html.count("<ol>") == 2
    assert html.count("<ul>") == 1
    assert html.count("<li>") == 5
    assert "<ol><li>पहिला मुद्दा</li><li>दुसरा मुद्दा</li></ol>" in html
    assert "<ul><li>उपमुद्दा अ</li><li>उपमुद्दा ब</li></ul>" in html
    assert html.endswith("<ol><li>तिसरा मुद्दा</li></ol>")


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

def test_backend_docx_export_writer_preserves_ordered_list_numbering():
    from io import BytesIO

    from docx import Document
    from app.services.docx_converter import html_to_docx

    output = html_to_docx(
        "<h1>बैठक</h1><ol><li>पहिला मुद्दा</li><li>दुसरा मुद्दा</li><li>तिसरा मुद्दा</li></ol>"
        "<ul><li>अतिरिक्त मुद्दा</li></ul>"
    )
    document = Document(BytesIO(output))

    numbered = [paragraph for paragraph in document.paragraphs if paragraph.style.name == "List Number"]
    bullets = [paragraph for paragraph in document.paragraphs if paragraph.style.name == "List Bullet"]
    assert [paragraph.text for paragraph in numbered] == ["पहिला मुद्दा", "दुसरा मुद्दा", "तिसरा मुद्दा"]
    assert [paragraph.text for paragraph in bullets] == ["अतिरिक्त मुद्दा"]


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


def test_formatting_requires_server_api_key(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "")
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService.format_transcript("Meeting notes")
    assert error.value.status_code == 503


def test_formatting_maps_gemini_rate_limit_to_retryable_error(monkeypatch):
    import httpx
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    class RateLimitedResponse:
        status_code = 429

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: RateLimitedResponse())
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService.format_transcript("Meeting notes")
    assert error.value.status_code == 429




def test_formatting_retries_one_read_timeout_then_succeeds(monkeypatch):
    import json
    import httpx
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.document_formatting_service.time.sleep", lambda _delay: None)
    calls = {"count": 0}

    class SuccessResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "blocks": [{"type": "paragraph", "text": "Timeout retry worked"}]
            })}]}}]}

    def fake_post(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ReadTimeout("provider read timeout")
        return SuccessResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    result, html = DocumentFormattingService.format_transcript("Meeting notes")

    assert calls["count"] == 2
    assert result["blocks"][0]["text"] == "Timeout retry worked"
    assert "Timeout retry worked" in html



def test_formatting_uses_stable_flash_fallback_after_primary_503(monkeypatch):
    import json
    import httpx
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.document_formatting_service.time.sleep", lambda _delay: None)
    calls = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {}

        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request("POST", "https://example.test")
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError("provider error", request=request, response=response)

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "blocks": [{"type": "paragraph", "text": "Fallback formatting worked"}]
            })}]}}]}

    def fake_post(url, **_kwargs):
        calls.append(url)
        if "gemini-3.8-flash" in url:
            return Response(503)
        return Response(200)

    monkeypatch.setattr(httpx, "post", fake_post)
    result, html = DocumentFormattingService.format_transcript("Meeting notes")

    assert len(calls) == 3
    assert all("gemini-3.8-flash" in url for url in calls[:2])
    assert "gemini-3.6-flash" in calls[2]
    assert result["blocks"][0]["text"] == "Fallback formatting worked"
    assert "Fallback formatting worked" in html


def test_formatting_retries_transient_gemini_503_then_succeeds(monkeypatch):
    import json
    import httpx
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.document_formatting_service.time.sleep", lambda _delay: None)
    calls = {"count": 0}

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {}

        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request("POST", "https://example.test")
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError("provider error", request=request, response=response)

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "blocks": [{"type": "paragraph", "text": "Formatted successfully"}]
            })}]}}]}

    def fake_post(*_args, **_kwargs):
        calls["count"] += 1
        return Response(503 if calls["count"] < 3 else 200)

    monkeypatch.setattr(httpx, "post", fake_post)
    result, html = DocumentFormattingService.format_transcript("Meeting notes")

    assert calls["count"] == 3
    assert result["blocks"][0]["text"] == "Formatted successfully"
    assert "Formatted successfully" in html


def test_formatting_returns_retryable_503_after_transient_retries(monkeypatch):
    import httpx
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.document_formatting_service.time.sleep", lambda _delay: None)
    calls = {"count": 0}

    def unavailable(*_args, **_kwargs):
        calls["count"] += 1
        request = httpx.Request("POST", "https://example.test")
        response = httpx.Response(503, request=request)
        return response

    monkeypatch.setattr(httpx, "post", unavailable)
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService.format_transcript("Meeting notes")

    # Two primary-model attempts plus one fallback-model attempt.
    assert calls["count"] == 3
    assert error.value.status_code == 503
    assert "temporarily overloaded" in error.value.detail

def test_formatting_handles_provider_timeout_without_exposing_source(monkeypatch):
    import httpx
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    def timeout(*args, **kwargs):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(httpx, "post", timeout)
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService.format_transcript("private transcript text")
    assert error.value.status_code == 502
    assert "private transcript text" not in error.value.detail


def test_formatting_rejects_malformed_provider_response(monkeypatch):
    import httpx
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    class InvalidResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": []}

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: InvalidResponse())
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService.format_transcript("Meeting notes")
    assert error.value.status_code == 502


def test_formatted_version_upload_creates_a_separate_docx(monkeypatch):
    from app.services.google_drive_service import GoogleDriveService

    captured = {}

    class FakeResponse:
        def json(self):
            return {
                "id": "drive-formatted-file-id",
                "name": "Minutes - Formatted v2.docx",
                "webViewLink": "https://drive.google.com/file/d/drive-formatted-file-id/view",
            }

    monkeypatch.setattr(
        GoogleDriveService,
        "connection",
        lambda _db, _user_id: type("Connection", (), {"documents_folder_id": "folder-123"})(),
    )
    monkeypatch.setattr(GoogleDriveService, "_access_token", lambda *_args: "access-token")
    monkeypatch.setattr(GoogleDriveService, "_documents_folder", lambda *_args: "folder-123")

    def fake_drive_request(method, url, token, **kwargs):
        captured.update(method=method, url=url, token=token, **kwargs)
        return FakeResponse()

    monkeypatch.setattr(GoogleDriveService, "_drive_request", fake_drive_request)
    result = GoogleDriveService.upload_formatted_version(
        object(), "owner-id", "document-id", 2, "Minutes", "<h1>बैठक</h1>"
    )

    assert result["id"] == "drive-formatted-file-id"
    assert captured["method"] == "POST"
    assert captured["token"] == "access-token"
    assert captured["params"]["uploadType"] == "multipart"
    assert b"Minutes - Formatted v2.docx" in captured["content"]
    assert b"PK" in captured["content"]


def test_drive_request_maps_google_api_failure_to_safe_http_error(monkeypatch):
    import httpx
    from app.services.google_drive_service import GoogleDriveService

    def fail_request(*_args, **_kwargs):
        request = httpx.Request("GET", "https://www.googleapis.com/drive/v3/files")
        response = httpx.Response(503, request=request)
        raise httpx.HTTPStatusError("provider details", request=request, response=response)

    monkeypatch.setattr(httpx, "request", fail_request)
    with pytest.raises(HTTPException) as error:
        GoogleDriveService._drive_request(
            "GET", "https://www.googleapis.com/drive/v3/files", "token"
        )
    assert error.value.status_code == 502
    assert "provider details" not in error.value.detail


def test_replacing_formatted_drive_version_updates_existing_docx(monkeypatch):
    from io import BytesIO
    from zipfile import ZipFile

    from app.services.google_drive_service import GoogleDriveService

    captured = {}

    class FakeResponse:
        def json(self):
            return {
                "id": "existing-drive-file-id",
                "name": "Minutes - Formatted v2.docx",
                "webViewLink": "https://drive.google.com/file/d/existing-drive-file-id/view",
            }

    monkeypatch.setattr(
        GoogleDriveService,
        "connection",
        lambda *_args: type("Connection", (), {"documents_folder_id": "folder-123"})(),
    )
    monkeypatch.setattr(GoogleDriveService, "_access_token", lambda *_args: "access-token")

    def fake_drive_request(method, url, token, **kwargs):
        captured.update(method=method, url=url, token=token, **kwargs)
        return FakeResponse()

    monkeypatch.setattr(GoogleDriveService, "_drive_request", fake_drive_request)
    result = GoogleDriveService.update_drive_document(
        object(), "owner-id", "existing-drive-file-id", "Minutes - Formatted v2",
        "<h1>बैठक</h1><p>Updated notes</p>",
    )

    assert result["id"] == "existing-drive-file-id"
    assert captured["method"] == "PATCH"
    assert captured["url"].endswith("/files/existing-drive-file-id")
    assert captured["params"]["uploadType"] == "multipart"
    assert b"Updated notes" not in captured["content"]  # Content is inside the DOCX ZIP.
    with ZipFile(BytesIO(captured["content"].split(b"PK", 1)[0] + b"PK" + captured["content"].split(b"PK", 1)[1])) as archive:
        assert "word/document.xml" in archive.namelist()
        assert b"Updated notes" in archive.read("word/document.xml")


def test_gemini_primary_timeouts_attempt_fallback_model(monkeypatch):
    import json
    import httpx
    from app.core.config import settings
    import app.services.document_formatting_service as formatting_module

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(formatting_module.time, "sleep", lambda *_args: None)

    class FormattedResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "blocks": [{"type": "paragraph", "text": "Formatted safely"}]
            })}]}}]}

    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) <= 2:
            raise httpx.ReadTimeout("temporary primary timeout")
        return FormattedResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    structured, html = DocumentFormattingService.format_transcript("Original text")

    assert len(calls) == 3
    assert "gemini-3.8-flash:generateContent" in calls[0]
    assert "gemini-3.8-flash:generateContent" in calls[1]
    assert "gemini-3.6-flash:generateContent" in calls[2]
    assert structured["blocks"][0]["text"] == "Formatted safely"
    assert "Formatted safely" in html


def test_gemini_primary_service_unavailable_retries_then_uses_fallback(monkeypatch):
    import json
    import httpx
    from app.core.config import settings
    import app.services.document_formatting_service as formatting_module

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(formatting_module.time, "sleep", lambda *_args: None)

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "temporary service error",
                    request=httpx.Request("POST", "https://example.test"),
                    response=httpx.Response(self.status_code),
                )

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "blocks": [{"type": "paragraph", "text": "Fallback worked"}]
            })}]}}]}

    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return Response(503 if len(calls) <= 2 else 200)

    monkeypatch.setattr(httpx, "post", fake_post)
    structured, _ = DocumentFormattingService.format_transcript("Original text")

    assert len(calls) == 3
    assert "gemini-3.6-flash:generateContent" in calls[-1]
    assert structured["blocks"][0]["text"] == "Fallback worked"


def test_legal_formatting_prompt_requires_selected_document_type_outline(monkeypatch):
    import json
    import httpx
    from app.core.config import settings
    from app.services.legal_document_catalog import get_legal_context

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    captured = {}

    class SuccessResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "blocks": [
                    {"type": "title", "text": "विवाह विच्छेद याचिका"},
                    {"type": "heading", "text": "याचिकाकर्त्याचा तपशील"},
                    {"type": "paragraph", "text": "[याचिकाकर्त्याचे नाव]"},
                    {"type": "heading", "text": "प्रार्थना"},
                    {"type": "paragraph", "text": "लग्नाची माहिती आणि घटस्फोटाची मागणी", "source_segment_ids": ["SOURCE_SEGMENT_0001"]},
                ]
            })}]}}]}

    def fake_post(_url, **kwargs):
        captured.update(kwargs["json"])
        return SuccessResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    context = get_legal_context("IN", "family-matrimonial-law", "divorce-petition-draft")
    DocumentFormattingService.format_transcript("लग्नाची माहिती आणि घटस्फोटाची मागणी", legal_context=context)

    prompt = captured["systemInstruction"]["parts"][0]["text"]
    assert "Divorce Petition Draft" in prompt
    assert "Petitioner particulars" in prompt
    assert "Respondent particulars" in prompt
    assert "Chronological statement of all matrimonial facts" in prompt
    assert "Each prayer or relief requested" in prompt
    assert "MUST transform the source into that document type" in prompt
    assert "Never invent facts" in prompt


def test_legal_formatting_prompt_preserves_all_source_details_and_separate_reliefs(monkeypatch):
    import json
    import httpx
    from app.core.config import settings
    from app.services.legal_document_catalog import get_legal_context

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    captured = {}

    source = (
        "याचिकाकर्ता व्यवसायाने शिक्षक आहे आणि पुणे येथे राहतो. "
        "पहिली घटना १२ जानेवारी रोजी घडली. दुसरी घटना १८ जानेवारी रोजी घडली. "
        "प्रार्थना १: घटस्फोटाचा हुकूम द्यावा. "
        "प्रार्थना २: खर्च मंजूर करावा. "
        "प्रार्थना ३: योग्य इतर दिलासा द्यावा."
    )
    class SuccessResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "blocks": [{
                    "type": "paragraph",
                    "text": source,
                    "source_segment_ids": [f"SOURCE_SEGMENT_{index:04d}" for index in range(1, 7)],
                }]
            })}]}}]}

    def fake_post(_url, **kwargs):
        captured["payload"] = kwargs["json"]
        return SuccessResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    context = get_legal_context("IN", "family-matrimonial-law", "divorce-petition-draft")
    DocumentFormattingService.format_transcript(source, legal_context=context)

    instruction = captured["payload"]["systemInstruction"]["parts"][0]["text"]
    assert "NOT summarization" in instruction
    assert "Do not shorten the source" in instruction
    assert "occupation, address" in instruction
    assert "each separate prayer" in instruction
    assert "never collapse multiple reliefs" in instruction
    assert "silently cross-check it against the source" in instruction
    assert "Chronological statement of all matrimonial facts" in instruction
    assert "Each prayer or relief requested" in instruction
    assert source in captured["payload"]["contents"][0]["parts"][0]["text"]
    assert "[SOURCE_SEGMENT_0001]" in captured["payload"]["contents"][0]["parts"][0]["text"]



def test_legal_structured_output_rejects_missing_source_segments():
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService._validate_result(
            {"blocks": [{"type": "paragraph", "text": "Only part of the draft", "source_segment_ids": ["SOURCE_SEGMENT_0001"]}]},
            required_source_ids={"SOURCE_SEGMENT_0001", "SOURCE_SEGMENT_0002"},
        )

    assert error.value.status_code == 502
    assert "omitted part" in error.value.detail


def test_legal_structured_output_rejects_unknown_source_segment():
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService._validate_result(
            {"blocks": [{"type": "paragraph", "text": "Draft", "source_segment_ids": ["SOURCE_SEGMENT_9999"]}]},
            required_source_ids={"SOURCE_SEGMENT_0001"},
        )

    assert error.value.status_code == 502
    assert "invalid source references" in error.value.detail


def test_legal_structured_output_accepts_complete_source_coverage():
    result = DocumentFormattingService._validate_result(
        {"blocks": [
            {"type": "paragraph", "text": "पहिला मुद्दा", "source_segment_ids": ["SOURCE_SEGMENT_0001"]},
            {"type": "paragraph", "text": "दुसरा मुद्दा", "source_segment_ids": ["SOURCE_SEGMENT_0002"]},
        ]},
        required_source_ids={"SOURCE_SEGMENT_0001", "SOURCE_SEGMENT_0002"},
    )

    assert len(result["blocks"]) == 2



def test_legal_docx_export_uses_formal_page_layout_and_typography():
    from io import BytesIO

    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from app.services.docx_converter import html_to_docx

    output = html_to_docx(
        "<h1>विवाह विच्छेद याचिका</h1>"
        "<h2>याचिकाकर्त्याचा तपशील</h2>"
        "<p>याचिकाकर्ता पुणे येथे राहतो.</p>",
        legal_mode=True,
    )
    document = Document(BytesIO(output))
    section = document.sections[0]

    assert round(section.top_margin.inches, 2) == 1.0
    assert round(section.bottom_margin.inches, 2) == 1.0
    assert round(section.left_margin.inches, 2) == 1.25
    assert round(section.right_margin.inches, 2) == 1.0
    assert document.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert document.paragraphs[1].alignment == WD_ALIGN_PARAGRAPH.LEFT
    assert document.paragraphs[2].alignment == WD_ALIGN_PARAGRAPH.JUSTIFY
    assert document.paragraphs[2].runs[0].font.name == "Times New Roman"
    assert document.paragraphs[2].runs[0].font.size.pt == 12
    assert document.paragraphs[2].paragraph_format.line_spacing == 1.5


def test_general_docx_export_keeps_default_layout():
    from io import BytesIO

    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from app.services.docx_converter import html_to_docx

    output = html_to_docx("<p>General document paragraph.</p>")
    document = Document(BytesIO(output))

    default_document = Document()
    assert document.paragraphs[0].alignment != WD_ALIGN_PARAGRAPH.JUSTIFY
    assert document.sections[0].left_margin == default_document.sections[0].left_margin
    assert document.paragraphs[0].paragraph_format.line_spacing is None



def test_legal_source_is_split_into_sentence_level_traceable_segments():
    from app.services.document_formatting_service import _split_legal_source_segments

    source = "विवाह 15.02.2018 रोजी झाला. पहिली घटना १२ जानेवारीला घडली.\nदुसरी घटना नंतर घडली."
    assert _split_legal_source_segments(source) == [
        "विवाह 15.02.2018 रोजी झाला.",
        "पहिली घटना १२ जानेवारीला घडली.",
        "दुसरी घटना नंतर घडली.",
    ]


def test_legal_output_rejects_reworded_or_omitted_source_even_when_ids_are_claimed():
    source = "राहुल शर्मा पुणे येथे राहतो. विवाह १५ फेब्रुवारी २०१८ रोजी झाला."
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService._validate_result(
            {"blocks": [{
                "type": "paragraph",
                "text": "राहुल शर्मा पुण्यात राहतो. विवाह १५ फेब्रुवारी २०१८ रोजी झाला.",
                "source_segment_ids": ["SOURCE_SEGMENT_0001"],
            }]},
            required_source_ids={"SOURCE_SEGMENT_0001"},
            required_source_text=source,
        )
    assert error.value.status_code == 502
    assert "changed, added, or omitted" in error.value.detail


def test_legal_output_rejects_omitted_date_even_when_other_wording_is_preserved():
    source = "विवाह १५ फेब्रुवारी २०१८ रोजी पुणे येथे झाला."
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService._validate_result(
            {"blocks": [{"type": "paragraph", "text": "विवाह २०१८ रोजी पुणे येथे झाला."}]},
            required_source_text=source,
        )
    assert error.value.status_code == 502
    assert "date, number, or amount" in error.value.detail


def test_legal_output_rejects_invented_dates_numbers_or_amounts():
    source = "विवाह १५ फेब्रुवारी २०१८ रोजी पुणे येथे झाला."
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService._validate_result(
            {"blocks": [
                {"type": "heading", "text": "विवाहाचा तपशील"},
                {"type": "paragraph", "text": "विवाह १५ फेब्रुवारी २०१८ रोजी पुणे येथे झाला. अर्ज क्रमांक १२/२०२६."},
            ]},
            required_source_text=source,
        )
    assert error.value.status_code == 502
    assert "date, number, or amount" in error.value.detail


def test_legal_output_rejects_invented_case_number_in_heading():
    source = "विवाह १५ फेब्रुवारी २०१८ रोजी पुणे येथे झाला."
    with pytest.raises(HTTPException) as error:
        DocumentFormattingService._validate_result(
            {"blocks": [
                {"type": "heading", "text": "केस क्रमांक १२/२०२६"},
                {"type": "paragraph", "text": source},
            ]},
            required_source_text=source,
        )
    assert error.value.status_code == 502
    assert "date, number, or amount" in error.value.detail


def test_legal_output_accepts_source_text_with_added_structural_headings_and_placeholders():
    source = "राहुल शर्मा पुणे येथे राहतो. विवाह १५ फेब्रुवारी २०१८ रोजी झाला."
    result = DocumentFormattingService._validate_result(
        {"blocks": [
            {"type": "heading", "text": "याचिकाकर्त्याचा तपशील"},
            {"type": "paragraph", "text": "राहुल शर्मा पुणे येथे राहतो."},
            {"type": "heading", "text": "विवाहाचा तपशील"},
            {"type": "paragraph", "text": "विवाह १५ फेब्रुवारी २०१८ रोजी झाला. [Marriage Registration Number]"},
        ]},
        required_source_text=source,
    )
    assert len(result["blocks"]) == 4



def test_divorce_petition_prompt_targets_gemini_style_structure_without_legal_assumptions(monkeypatch):
    import json
    import httpx
    from app.core.config import settings
    from app.services.legal_document_catalog import get_legal_context

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    captured = {}

    class SuccessResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "blocks": [
                    {"type": "title", "text": "विवाह विच्छेदासाठी अर्ज"},
                    {"type": "heading", "text": "अर्जदार"},
                    {"type": "paragraph", "text": "राहुल शर्मा पुणे येथे राहतो.", "source_segment_ids": ["SOURCE_SEGMENT_0001"]},
                ]
            })}]}}]}

    def fake_post(_url, **kwargs):
        captured["payload"] = kwargs["json"]
        return SuccessResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    context = get_legal_context("IN", "family-matrimonial-law", "divorce-petition-draft")
    DocumentFormattingService.format_transcript(
        "राहुल शर्मा पुणे येथे राहतो.", legal_context=context
    )

    instruction = captured["payload"]["systemInstruction"]["parts"][0]["text"]
    required_phrases = [
        "centered court caption",
        "petitioner and respondent particulars in separate blocks",
        "distinct विनंती (Prayer) section",
        "सत्यापन (Verification)",
        "[विवाह याचिका क्रमांक]",
        "uncompleted template only",
        "never assert that the applicant swears",
        "do not assert territorial jurisdiction",
        "preserve every source factual sentence verbatim",
        "Never add a prayer for costs",
        "Never assume the applicable personal law",
    ]
    for phrase in required_phrases:
        assert phrase in instruction
    assert "Hindu Marriage Act" not in instruction


def test_divorce_petition_catalog_requests_full_formal_structure():
    from app.services.legal_document_catalog import get_legal_context

    context = get_legal_context("IN", "family-matrimonial-law", "divorce-petition-draft")
    outline = " ".join(context["format_sections"])
    for phrase in [
        "Centered court caption",
        "separate blocks",
        "Subject line",
        "Numbered sections",
        "distinct prayer section",
        "Verification section",
    ]:
        assert phrase.lower() in outline.lower()



def test_legal_formatting_retries_once_when_model_changes_source_wording(monkeypatch):
    import json
    import httpx
    from app.core.config import settings
    from app.services.legal_document_catalog import get_legal_context

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    source = "राहुल शर्मा पुणे येथे राहतो. विवाह १५ फेब्रुवारी २०१८ रोजी झाला."
    outputs = [
        {"blocks": [{
            "type": "paragraph",
            "text": "राहुल शर्मा पुण्यात राहतो. विवाह १५ फेब्रुवारी २०१८ रोजी झाला.",
            "source_segment_ids": ["SOURCE_SEGMENT_0001", "SOURCE_SEGMENT_0002"],
        }]},
        {"blocks": [
            {"type": "title", "text": "विवाह विच्छेदासाठी अर्ज"},
            {"type": "heading", "text": "अर्जदाराचा तपशील"},
            {"type": "paragraph", "text": "राहुल शर्मा पुणे येथे राहतो.", "source_segment_ids": ["SOURCE_SEGMENT_0001"]},
            {"type": "heading", "text": "विवाहाचा तपशील"},
            {"type": "paragraph", "text": "विवाह १५ फेब्रुवारी २०१८ रोजी झाला.", "source_segment_ids": ["SOURCE_SEGMENT_0002"]},
        ]},
    ]
    calls = []

    class Response:
        status_code = 200
        headers = {}

        def __init__(self, output):
            self.output = output

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(self.output, ensure_ascii=False)}]}}]}

    def fake_post(_url, **kwargs):
        calls.append(kwargs["json"])
        return Response(outputs[len(calls) - 1])

    monkeypatch.setattr(httpx, "post", fake_post)
    context = get_legal_context("IN", "family-matrimonial-law", "divorce-petition-draft")
    structured, html = DocumentFormattingService.format_transcript(source, legal_context=context)

    assert len(calls) == 2
    assert "STRICT CORRECTION" in calls[1]["systemInstruction"]["parts"][0]["text"]
    assert "राहुल शर्मा पुणे येथे राहतो." in html
    assert "विवाह १५ फेब्रुवारी २०१८ रोजी झाला." in html
    assert structured["blocks"][-1]["text"] == "विवाह १५ फेब्रुवारी २०१८ रोजी झाला."


def test_legal_formatting_uses_verbatim_fallback_when_corrective_retry_fails(monkeypatch):
    import json
    import httpx
    from app.core.config import settings
    from app.services.legal_document_catalog import get_legal_context

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    source = "राहुल शर्मा पुणे येथे राहतो. विवाह १५ फेब्रुवारी २०१८ रोजी झाला."
    invalid = {"blocks": [{
        "type": "paragraph",
        "text": "राहुल शर्मा पुण्यात राहतो. विवाह १५ फेब्रुवारी २०१८ रोजी झाला.",
        "source_segment_ids": ["SOURCE_SEGMENT_0001", "SOURCE_SEGMENT_0002"],
    }]}
    calls = []

    class Response:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(invalid, ensure_ascii=False)}]}}]}

    def fake_post(_url, **_kwargs):
        calls.append(True)
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    context = get_legal_context("IN", "family-matrimonial-law", "divorce-petition-draft")
    structured, html = DocumentFormattingService.format_transcript(source, legal_context=context)

    factual_blocks = [
        block["text"] for block in structured["blocks"]
        if block["type"] == "paragraph"
    ]
    assert len(calls) == 2
    assert factual_blocks == [
        "राहुल शर्मा पुणे येथे राहतो.",
        "विवाह १५ फेब्रुवारी २०१८ रोजी झाला.",
    ]
    assert "".join("".join(block.split()) for block in factual_blocks) == "".join(source.split())
    assert "विवाह विच्छेदासाठी अर्ज" in html


@pytest.mark.parametrize(
    ("primary_failure", "expected_status"),
    [
        ("service_unavailable", 503),
        ("timeout", 502),
    ],
)
def test_gemini_fallback_timeout_preserves_primary_failure_classification(
    monkeypatch, primary_failure, expected_status
):
    import httpx
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr("app.services.document_formatting_service.time.sleep", lambda _seconds: None)
    calls = []

    class ServiceUnavailableResponse:
        status_code = 503
        headers = {}

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "service unavailable",
                request=httpx.Request("POST", "https://example.test"),
                response=httpx.Response(503),
            )

    def fake_post(url, **_kwargs):
        calls.append(url)
        if primary_failure == "service_unavailable" and len(calls) <= 2:
            return ServiceUnavailableResponse()
        raise httpx.ReadTimeout("provider timed out")

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(HTTPException) as error:
        DocumentFormattingService.format_transcript("A short source document.")

    assert error.value.status_code == expected_status
    assert len(calls) == 3
    if expected_status == 503:
        assert "temporarily overloaded" in error.value.detail
    else:
        assert "temporarily unavailable" in error.value.detail
