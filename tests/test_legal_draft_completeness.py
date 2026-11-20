from app.services.legal_document_catalog import get_legal_context
from app.services.legal_draft_completeness import assess_legal_draft_completeness


def test_cheque_notice_preflight_flags_missing_notice_date_address_and_memo_receipt_date():
    context = get_legal_context("IN", "banking-finance", "cheque-dishonour-notice")
    source = (
        "माझे नाव अमोल सुरेश पाटील आहे. मी बार्शी येथे राहतो. "
        "श्री. राहुल विजय देशमुख पुणे येथे राहतात. "
        "त्यांनी १,५०,००० रुपये घेतले. चेक दिनांक ०५/११/२०२६. "
        "१०/११/२०२६ रोजी चेक जमा केला. १२/११/२०२६ रोजी चेक अपुऱ्या निधीमुळे परत आला."
    )
    result = assess_legal_draft_completeness(source, context)

    fields = {item["field"] for item in result["missing_information"]}
    assert result["status"] == "needs_information"
    assert result["can_generate"] is False
    assert {"notice_date", "recipient_full_address", "dishonour_information_received_date"} <= fields
    assert "कायदेशीर वैधता" in result["notice"]


def test_cheque_notice_preflight_does_not_claim_to_certify_legal_compliance():
    context = get_legal_context("IN", "banking-finance", "cheque-dishonour-notice")
    result = assess_legal_draft_completeness("Cheque notice date 19/11/2026", context)
    assert "does not determine legal validity" in result["notice"]


def test_non_cheque_legal_document_does_not_receive_cheque_specific_questions():
    context = get_legal_context("IN", "criminal-law", "criminal-complaint")
    result = assess_legal_draft_completeness("घटना १९/११/२०२६ रोजी घडली.", context)
    assert result["missing_information"] == []
    assert result["can_generate"] is True
