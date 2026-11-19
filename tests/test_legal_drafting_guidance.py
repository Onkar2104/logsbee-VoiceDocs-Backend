import json

import pytest

from app.services.legal_drafting_guidance import get_legal_drafting_guidance
from app.services.legal_document_catalog import get_legal_context
from app.services.document_formatting_service import DocumentFormattingService


def test_cheque_dishonour_notice_guidance_requires_formal_marathi_notice_structure():
    context = get_legal_context("IN", "banking-finance", "cheque-dishonour-notice")
    guidance = get_legal_drafting_guidance(context)

    for phrase in (
        "CHEQUE DISHONOUR LEGAL NOTICE",
        "recipient's full name/address",
        "cheque number",
        "exact bank return reason",
        "DD/MM/YYYY",
        "19/11/2026",
        "Do not add claims of mental harassment",
        "Do not invent an advocate's name",
    ):
        assert phrase in guidance


def test_drafting_guidance_does_not_turn_missing_facts_into_assumptions():
    context = get_legal_context("IN", "banking-finance", "cheque-dishonour-notice")
    guidance = get_legal_drafting_guidance(context)

    assert "Do not invent or assume names" in guidance
    assert "response period only when supplied" in guidance
    assert "Do not state that the notice was served if only dispatch is supplied" in guidance


def test_legal_drafting_mode_allows_formal_rewording_but_requires_source_segment_coverage():
    source = "अमोल देशमुख यांनी राजेश पाटील यांना कर्ज दिले. धनादेश अपुऱ्या शिल्लकीमुळे परत आला."
    context = get_legal_context("IN", "banking-finance", "cheque-dishonour-notice")
    output = {
        "blocks": [
            {"type": "title", "text": "धनादेश अनादरित झाल्याबाबत कायदेशीर नोटीस"},
            {
                "type": "paragraph",
                "text": "माझ्या पक्षकार श्री. अमोल देशमुख यांनी आपणास कर्जरक्कम दिली होती.",
                "source_segment_ids": ["SOURCE_SEGMENT_0001"],
            },
            {
                "type": "paragraph",
                "text": "आपण दिलेला धनादेश अपुऱ्या शिल्लकीमुळे अनादरित झाला.",
                "source_segment_ids": ["SOURCE_SEGMENT_0002"],
            },
        ]
    }

    validated = DocumentFormattingService._validate_result(
        output,
        required_source_ids={"SOURCE_SEGMENT_0001", "SOURCE_SEGMENT_0002"},
        required_source_text=None,
    )

    assert validated["blocks"][1]["text"] != "अमोल देशमुख यांनी राजेश पाटील यांना कर्ज दिले."
    assert {
        source_id
        for block in validated["blocks"]
        for source_id in block.get("source_segment_ids", [])
    } == {"SOURCE_SEGMENT_0001", "SOURCE_SEGMENT_0002"}


def test_cheque_notice_drafting_prompt_is_used_and_preserves_rewritten_segments(monkeypatch):
    import httpx
    from app.core.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    source = "अमोल देशमुख यांनी राजेश पाटील यांना कर्ज दिले. धनादेश अपुऱ्या शिल्लकीमुळे परत आला."
    captured = {}

    class Response:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "blocks": [
                    {"type": "title", "text": "धनादेश अनादरित झाल्याबाबत कायदेशीर नोटीस"},
                    {"type": "paragraph", "text": "माझ्या पक्षकार श्री. अमोल देशमुख यांनी आपणास कर्जरक्कम दिली होती.", "source_segment_ids": ["SOURCE_SEGMENT_0001"]},
                    {"type": "paragraph", "text": "आपण दिलेला धनादेश अपुऱ्या शिल्लकीमुळे अनादरित झाला.", "source_segment_ids": ["SOURCE_SEGMENT_0002"]},
                ]
            }, ensure_ascii=False)}]}}]}

    def fake_post(_url, **kwargs):
        captured["payload"] = kwargs["json"]
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    context = get_legal_context("IN", "banking-finance", "cheque-dishonour-notice")
    structured, html = DocumentFormattingService.format_transcript(
        source, legal_context=context, drafting_mode=True
    )

    prompt = captured["payload"]["systemInstruction"]["parts"][0]["text"]
    assert "DRAFTING MODE" in prompt
    assert "CHEQUE DISHONOUR LEGAL NOTICE" in prompt
    assert "VERBATIM FACTUAL CONTENT RULE" in prompt
    assert "माझ्या पक्षकार श्री. अमोल देशमुख" in html
    assert len(structured["blocks"]) == 3


def test_drafting_mode_requires_a_legal_context():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        DocumentFormattingService.format_transcript(
            "कर्ज दिले.", legal_context=None, drafting_mode=True
        )
    assert error.value.status_code == 422
