"""Coverage tests for document-type-specific legal formatting guidance."""

import pytest

from app.services.legal_document_catalog import LEGAL_CATEGORIES, get_legal_context
from app.services.legal_formatting_guidance import (
    get_document_type_guidance,
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
    assert get_supported_document_type_ids() <= CATALOGUE_DOCUMENT_TYPE_IDS


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
