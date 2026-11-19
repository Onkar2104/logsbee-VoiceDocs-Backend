"""Regression coverage for every selectable Indian legal document format.

These tests mock Gemini deliberately: they validate catalogue-to-prompt integration,
language/source preservation, and document-type selection without requiring API access.
"""
import json
import os

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
    "GOOGLE_TOKEN_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    "FRONTEND_APP_URL": "http://localhost:5173",
    "TRANSCRIPTION_PROVIDER": "browser",
    "WHISPER_MODEL_SIZE": "small",
    "WHISPER_DEVICE": "cpu",
    "WHISPER_COMPUTE_TYPE": "int8",
    "WHISPER_CPU_THREADS": "1",
    "WHISPER_BATCH_SIZE": "1",
    "INDICCONFORMER_DEVICE": "cpu",
    "GEMINI_API_KEY": "test-key",
}
for _key, _value in _TEST_SETTINGS.items():
    os.environ.setdefault(_key, _value)

import pytest
import httpx

from app.core.config import settings
from app.services.document_formatting_service import DocumentFormattingService, _split_legal_source_segments
from app.services.legal_document_catalog import LEGAL_CATEGORIES, get_legal_context


LEGAL_FORMAT_CASES = [
    (category["id"], document_type["id"], language)
    for category in LEGAL_CATEGORIES
    for document_type in category["document_types"]
    for language in ("en", "mr")
]


@pytest.mark.parametrize(
    ("category_id", "document_type_id", "language"),
    LEGAL_FORMAT_CASES,
    ids=[
        f"{category}-{document_type}-{language}"
        for category, document_type, language in LEGAL_FORMAT_CASES
    ],
)
def test_every_legal_document_type_passes_selected_outline_and_preserves_source(
    monkeypatch, category_id, document_type_id, language
):
    """Every selectable legal type must reach Gemini with its own outline.

    The mocked provider returns the original source verbatim. This checks the
    integration and strict validator for both supported scripts without making
    network calls or depending on a live Gemini API key.
    """
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    if language == "mr":
        source = "अर्जदार राहुल पाटील पुणे येथे राहतो. दिनांक १२ जानेवारी २०२५ रोजी रुपये १२,५०० भरले."
    else:
        source = "Applicant Rahul Patil lives in Pune. INR 12,500 was paid on 12 January 2025."

    source_ids = [
        f"SOURCE_SEGMENT_{index:04d}"
        for index, _segment in enumerate(_split_legal_source_segments(source), start=1)
    ]
    provider_output = {
        "blocks": [{
            "type": "paragraph",
            "text": source,
            "source_segment_ids": source_ids,
        }]
    }
    captured = {}

    class SuccessResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [{
                    "content": {
                        "parts": [{"text": json.dumps(provider_output, ensure_ascii=False)}]
                    }
                }]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["payload"] = kwargs["json"]
        return SuccessResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    context = get_legal_context("IN", category_id, document_type_id)
    structured, formatted_html = DocumentFormattingService.format_transcript(
        source, legal_context=context
    )

    prompt = captured["payload"]["systemInstruction"]["parts"][0]["text"]
    assert context["document_type_label"] in prompt
    assert context["category_label"] in prompt
    assert "You MUST transform the source into that document type" in prompt
    for section in context["format_sections"]:
        assert section in prompt

    assert len(captured["payload"]["contents"]) == 1
    assert source in captured["payload"]["contents"][0]["parts"][0]["text"]
    assert structured["blocks"][0]["text"] == source
    assert source in formatted_html
    assert structured["blocks"][0]["source_segment_ids"] == source_ids


def test_legal_catalogue_has_no_duplicate_document_type_within_a_category():
    """Repeated types across categories are valid; duplicates within one are not."""
    for category in LEGAL_CATEGORIES:
        document_type_ids = [
            item["id"] for item in category["document_types"]
        ]
        assert len(document_type_ids) == len(set(document_type_ids)), category["id"]
