"""Pre-drafting completeness checks for Indian legal document drafts.

This is a conservative intake aid, not a legal opinion or a statutory-compliance validator.
It flags information that appears absent; it never infers missing facts.
"""
import re


def _has_any(source: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, source, re.IGNORECASE) for pattern in patterns)


def assess_legal_draft_completeness(source: str, legal_context: dict) -> dict:
    """Return focused missing-information questions before legal drafting."""
    source = source or ""
    document_type = legal_context.get("document_type_id", "")
    is_marathi = bool(re.search(r"[\u0900-\u097F]", source))
    missing = []
    checks = []

    def add(field, importance, question_en, question_mr, reason_en, reason_mr):
        item = {
            "field": field,
            "importance": importance,
            "question": question_mr if is_marathi else question_en,
            "reason": reason_mr if is_marathi else reason_en,
        }
        missing.append(item)

    if document_type == "cheque-dishonour-notice":
        if not _has_any(source, (r"नोटीस.{0,12}दिनांक", r"दिनांक.{0,12}नोटीस", r"notice\s*date", r"date\s*of\s*notice")):
            add("notice_date", "required_for_final_notice",
                "What date should appear on the legal notice?",
                "कायदेशीर नोटीसवर कोणती तारीख नमूद करायची आहे?",
                "The notice date was not supplied. A placeholder can be used until confirmed.",
                "नोटीसची तारीख दिलेली नाही. खात्री होईपर्यंत जागी placeholder ठेवता येईल.")
        if not _has_any(source, (r"पत्ता.{0,35}(?:पुणे|मुंबई|बार्शी|नाशिक|औरंगाबाद|नागपूर)", r"address\s*:", r"full\s+address")):
            add("recipient_full_address", "required_for_service",
                "What is the recipient's complete postal address, including PIN code?",
                "नोटीस प्राप्त करणाऱ्याचा संपूर्ण टपाल पत्ता आणि पिनकोड काय आहे?",
                "A city alone may be insufficient for reliable notice delivery.",
                "फक्त शहराचे नाव नोटीस पाठविण्यासाठी पुरेसे नसू शकते.")
        if not _has_any(source, (r"पत्ता.{0,35}(?:पुणे|मुंबई|बार्शी|नाशिक|औरंगाबाद|नागपूर)", r"sender\s+address", r"from\s+address")):
            add("sender_full_address", "recommended",
                "What is the sender's complete postal address?",
                "नोटीस पाठविणाऱ्याचा संपूर्ण टपाल पत्ता काय आहे?",
                "The sender's complete address was not clearly supplied.",
                "नोटीस पाठविणाऱ्याचा संपूर्ण पत्ता स्पष्टपणे दिलेला नाही.")
        if not _has_any(source, (r"मेमो.{0,25}मिळ", r"परत.{0,25}मिळ", r"received.{0,20}(?:memo|dishonour|return)", r"receipt\s+of\s+(?:the\s+)?(?:bank\s+)?memo")):
            add("dishonour_information_received_date", "required_to_check_timeline",
                "On what date did you receive the bank's cheque-return memo or learn of dishonour?",
                "बँकेचा चेक परत आल्याचा मेमो किंवा अनादराची माहिती तुम्हाला कोणत्या दिवशी मिळाली?",
                "The date of receiving dishonour information is needed to assess the notice-issuance timeline; the dishonour date alone may not establish it.",
                "नोटीस पाठविण्याची मुदत तपासण्यासाठी अनादराची माहिती मिळाल्याची तारीख आवश्यक आहे; फक्त चेक परत आल्याची तारीख पुरेशी नसेल.")
        if not _has_any(source, (r"तीन\s*महिने|3\s*महिने|validity|वैधता",)):
            add("cheque_validity_confirmation", "recommended_confirmation",
                "Please confirm that the cheque was presented within its validity period.",
                "धनादेश त्याच्या वैधता कालावधीत बँकेत सादर केला होता, याची कृपया पुष्टी करा.",
                "The source does not establish whether presentation was within the cheque's validity period.",
                "धनादेश वैधता कालावधीत सादर झाला होता का, हे दिलेल्या मजकुरातून स्पष्ट होत नाही.")

    if not missing:
        status = "ready_with_review"
    elif any(item["importance"].startswith("required") for item in missing):
        status = "needs_information"
    else:
        status = "ready_with_questions"

    return {
        "document_type": document_type,
        "status": status,
        "can_generate": status != "needs_information",
        "missing_information": missing,
        "notice": (
            "This check identifies potentially missing intake details only. It does not determine legal validity or certify compliance. A qualified Indian lawyer should review the final draft."
            if not is_marathi else
            "ही तपासणी केवळ संभाव्य अपूर्ण माहिती दर्शवते. ती कायदेशीर वैधता किंवा कायद्याचे पालन प्रमाणित करत नाही. अंतिम मसुद्याची पात्र भारतीय वकिलांकडून तपासणी करून घ्यावी."
        ),
    }
