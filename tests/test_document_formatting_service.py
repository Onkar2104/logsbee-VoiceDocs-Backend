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
