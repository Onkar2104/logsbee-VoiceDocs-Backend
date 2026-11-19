"""Coverage tests for document-type-specific legal formatting guidance."""

import json

import httpx
import pytest

from app.core.config import settings

from app.services.legal_document_catalog import LEGAL_CATEGORIES, get_legal_context
from app.services.document_formatting_service import (
    DocumentFormattingService,
    _split_legal_source_segments,
)
from app.services.legal_formatting_guidance import (
    get_document_type_guidance,
    get_fallback_section_heading,
    get_supported_document_type_ids,
)


CATALOGUE_DOCUMENT_TYPE_IDS = {
    document_type["id"]
    for category in LEGAL_CATEGORIES
    for document_type in category["document_types"]
}


@pytest.mark.parametrize("document_type_id", sorted(CATALOGUE_DOCUMENT_TYPE_IDS))
def test_every_catalogue_document_type_has_specific_formatting_guidance(document_type_id):
    category = next(
        category
        for category in LEGAL_CATEGORIES
        if any(item["id"] == document_type_id for item in category["document_types"])
    )
    context = get_legal_context("IN", category["id"], document_type_id)

    guidance = get_document_type_guidance(context)

    assert guidance
    assert "Do not" in guidance or "never" in guidance.lower()


def test_guidance_configuration_contains_only_catalogue_document_types():
    assert get_supported_document_type_ids() == CATALOGUE_DOCUMENT_TYPE_IDS


@pytest.mark.parametrize(
    ("category_id", "document_type_id", "expected_phrase"),
    [
        ("criminal-law", "criminal-complaint", "allegations as allegations"),
        ("family-matrimonial-law", "maintenance-application", "each separate relief"),
        ("lottery-prize-disputes", "affidavit", "uncompleted placeholders"),
        ("business-corporate-law", "partnership-agreement-draft", "Do not invent commercial terms"),
        ("taxation", "tax-reply-draft", "point-by-point"),
        ("banking-finance", "cheque-dishonour-notice", "statutory deadlines"),
        ("motor-accident-claims", "insurance-claim-representation", "never estimate or add compensation amounts"),
    ],
)
def test_document_family_guidance_uses_appropriate_structure(
    category_id, document_type_id, expected_phrase
):
    context = get_legal_context("IN", category_id, document_type_id)

    assert expected_phrase in get_document_type_guidance(context)



@pytest.mark.parametrize(
    ("category_id", "document_type_id", "source", "expected_heading"),
    [
        ("banking-finance", "cheque-dishonour-notice", "A cheque was issued on 12 March 2025. Payment was not received.", "Notice content supplied"),
        ("criminal-law", "criminal-complaint", "घटना १२ मार्च २०२५ रोजी घडली. तक्रार नोंदवली.", "दिलेल्या तक्रारीचा तपशील"),
        ("family-matrimonial-law", "maintenance-application", "Applicant earns INR 12,000 monthly. Two dependants are identified.", "Petition / application facts supplied"),
        ("lottery-prize-disputes", "affidavit", "मी दिलेल्या माहितीनुसार हा मजकूर सादर करीत आहे.", "दिलेली निवेदने (शपथपूर्वक घोषित नाहीत)"),
        ("business-corporate-law", "partnership-agreement-draft", "Partner A contributes INR 50,000. Partner B contributes INR 25,000.", "Agreement terms supplied"),
        ("taxation", "tax-reply-draft", "The notice is dated 4 April 2025. I submitted the records.", "Reply content supplied"),
        ("motor-accident-claims", "insurance-claim-representation", "The accident occurred on 1 May 2025. The claim amount is INR 80,000.", "Claim details supplied"),
    ],
)
def test_legal_fallback_has_family_heading_and_preserves_all_source_segments(
    category_id, document_type_id, source, expected_heading
):
    category = next(
        category for category in LEGAL_CATEGORIES if category["id"] == category_id
    )
    context = get_legal_context("IN", category_id, document_type_id)

    fallback = DocumentFormattingService._build_legal_document_fallback(
        source, context
    )
    segments = _split_legal_source_segments(source)

    assert fallback["blocks"][0] == {
        "type": "title",
        "text": context["document_type_label"],
    }
    assert fallback["blocks"][1]["type"] == "heading"
    assert fallback["blocks"][1]["text"] == expected_heading
    factual_blocks = fallback["blocks"][2:]
    assert [block["text"] for block in factual_blocks] == segments
    assert [
        block["source_segment_ids"][0] for block in factual_blocks
    ] == [
        f"SOURCE_SEGMENT_{index:04d}"
        for index in range(1, len(segments) + 1)
    ]

    validated = DocumentFormattingService._validate_result(
        fallback,
        required_source_ids={
            f"SOURCE_SEGMENT_{index:04d}"
            for index in range(1, len(segments) + 1)
        },
        required_source_text=source,
    )
    assert [block["text"] for block in validated["blocks"][2:]] == segments



@pytest.mark.parametrize(
    ("category_id", "document_type_id", "source", "expected_heading"),
    [
        ("banking-finance", "cheque-dishonour-notice", "A cheque was issued on 12 March 2025. Payment was not received.", "Notice content supplied"),
        ("criminal-law", "criminal-complaint", "घटना १२ मार्च २०२५ रोजी घडली. तक्रार नोंदवली.", "दिलेल्या तक्रारीचा तपशील"),
        ("business-corporate-law", "partnership-agreement-draft", "Partner A contributes INR 50,000. Partner B contributes INR 25,000.", "Agreement terms supplied"),
    ],
)
def test_format_transcript_uses_structured_family_fallback_after_retry_fails(
    monkeypatch, category_id, document_type_id, source, expected_heading
):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls = []

    class InvalidResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            invalid_output = {
                "blocks": [{
                    "type": "paragraph",
                    "text": "This deliberately altered response fails source validation.",
                    "source_segment_ids": [
                        f"SOURCE_SEGMENT_{index:04d}"
                        for index, _ in enumerate(
                            _split_legal_source_segments(source), start=1
                        )
                    ],
                }]
            }
            return {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps(invalid_output, ensure_ascii=False)
                        }]
                    }
                }]
            }

    def fake_post(_url, **_kwargs):
        calls.append(True)
        return InvalidResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    context = get_legal_context("IN", category_id, document_type_id)

    structured, html = DocumentFormattingService.format_transcript(
        source, legal_context=context
    )

    assert len(calls) == 2
    assert structured["blocks"][0]["type"] == "title"
    assert structured["blocks"][0]["text"] == context["document_type_label"]
    assert structured["blocks"][1]["type"] == "heading"
    assert structured["blocks"][1]["text"] == expected_heading
    factual_blocks = [
        block for block in structured["blocks"]
        if block["type"] in {"paragraph", "number", "bullet", "quote"}
    ]
    assert [block["text"] for block in factual_blocks] == (
        _split_legal_source_segments(source)
    )
    # HTML renders each preserved source segment in its own paragraph.
    assert all(segment in html for segment in _split_legal_source_segments(source))
