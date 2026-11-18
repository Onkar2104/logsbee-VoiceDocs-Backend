import pytest

from app.services.legal_document_catalog import (
    DOCUMENT_TYPE_SECTIONS,
    LEGAL_CATEGORIES,
    get_legal_catalog,
    get_legal_context,
    validate_document_metadata,
)


def test_india_catalog_contains_all_sixteen_requested_categories():
    catalog = get_legal_catalog()
    assert catalog["jurisdictions"] == [{"id": "IN", "label": "India"}]
    assert len(catalog["categories"]) == 16
    assert {item["label"] for item in catalog["categories"]} == {
        "Lottery and Prize Disputes", "Family and Matrimonial Law",
        "Property and Land Disputes", "Criminal Law", "Banking and Finance",
        "Consumer Protection", "Employment and Labour Law", "Business and Corporate Law",
        "Cybercrime", "Motor Accident Claims", "Taxation", "Constitutional Law",
        "Education Law", "Environmental Law", "Intellectual Property", "Immigration",
    }


def test_document_types_are_scoped_to_the_selected_category():
    context = get_legal_context("IN", "lottery-prize-disputes", "prize-claim-application")
    assert context["category_label"] == "Lottery and Prize Disputes"
    assert context["document_type_label"] == "Prize Claim Application"
    with pytest.raises(ValueError):
        get_legal_context("IN", "criminal-law", "prize-claim-application")


def test_general_document_metadata_is_optional_and_empty():
    assert validate_document_metadata("general", None, None, None) == {
        "formatting_mode": "general",
        "jurisdiction": None,
        "legal_category": None,
        "document_type": None,
    }


def test_legal_document_requires_valid_complete_metadata():
    with pytest.raises(ValueError):
        validate_document_metadata("legal", "IN", "criminal-law", None)
    with pytest.raises(ValueError):
        validate_document_metadata("legal", "US", "criminal-law", "bail-application-draft")
    assert validate_document_metadata(
        "legal", "IN", "criminal-law", "bail-application-draft"
    )["formatting_mode"] == "legal"


def test_unknown_formatting_mode_is_rejected():
    with pytest.raises(ValueError):
        validate_document_metadata("automatic", None, None, None)


def test_each_selectable_document_type_has_a_specific_format_outline():
    catalog = get_legal_catalog()
    for category in catalog["categories"]:
        for document_type in category["document_types"]:
            context = get_legal_context("IN", category["id"], document_type["id"])
            assert document_type["id"] in DOCUMENT_TYPE_SECTIONS
            assert context["format_sections"], document_type["id"]
            assert context["document_type_label"] == document_type["label"]


def test_divorce_petition_outline_uses_petition_specific_sections():
    context = get_legal_context(
        "IN", "family-matrimonial-law", "divorce-petition-draft"
    )
    outline = context["format_sections"]

    assert any("Petitioner" in section for section in outline)
    assert any("Respondent" in section for section in outline)
    assert any("matrimonial facts" in section for section in outline)
    assert any("Grounds" in section for section in outline)
    assert any("Each prayer or relief requested" in section for section in outline)
    assert any("Verification" in section for section in outline)
