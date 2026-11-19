"""Document-type-specific safeguards for Indian legal document formatting.

These are formatting instructions, not legal advice or prescribed court forms.
"""

_DOCUMENT_TYPE_RULES = {
    "notice": {
        "legal-notice", "cheque-dishonour-notice", "loan-recovery-notice",
        "refund-demand-notice", "salary-recovery-notice",
        "copyright-infringement-notice",
    },
    "complaint": {
        "police-complaint", "criminal-complaint", "consumer-complaint",
        "cybercrime-complaint", "online-fraud-complaint", "education-complaint",
        "environmental-complaint",
    },
    "representation": {
        "police-representation", "banking-grievance",
        "deficiency-service-representation", "termination-dispute-representation",
        "employment-grievance", "business-representation",
        "cyber-incident-representation",
        "tax-representation", "constitutional-representation",
        "admission-dispute-representation", "academic-grievance",
        "environmental-representation", "ip-infringement-representation",
        "visa-representation", "immigration-explanation",
        "property-dispute-application",
    },
    "petition_or_application": {
        "divorce-petition-draft", "maintenance-application",
        "child-custody-petition", "partition-suit-draft",
        "bail-application-draft", "compensation-claim-draft",
        "accident-related-petition", "writ-petition-draft",
        "prize-claim-application", "immigration-appeal-draft",
        "tax-objection-draft",
    },
    "affidavit": {"affidavit"},
    "agreement": {"partnership-agreement-draft"},
    "reply": {"tax-reply-draft", "trademark-objection-reply"},
    "claim": {"insurance-claim-representation"},
}

_FAMILY_GUIDANCE = {
    "notice": (
        "NOTICE FORMAT: Present the sender and recipient separately, then the subject, "
        "relevant transaction/background, specific grievance, each distinct demand, "
        "response period only when supplied (otherwise a clearly marked placeholder), "
        "and closing/signature. Do not turn a notice into a court petition or invent "
        "statutory deadlines, consequences, or legal provisions."
    ),
    "complaint": (
        "COMPLAINT FORMAT: Identify the receiving authority and complainant, then set "
        "out the incident and its date/place, a chronological account, each distinct "
        "act or grievance, loss/impact, witnesses/evidence actually mentioned, and "
        "the action requested. Do not assert that an offence or legal violation is "
        "proved; retain allegations as allegations."
    ),
    "representation": (
        "REPRESENTATION FORMAT: Address the relevant recipient, identify the applicant "
        "and reference, explain the background and chronology, state each issue or "
        "grievance separately, include prior communications/responses when supplied, "
        "and list the specific corrective action requested. Do not add court pleadings "
        "or convert requests into legal findings."
    ),
    "petition_or_application": (
        "PETITION/APPLICATION FORMAT: Use a forum/caption and separate party particulars "
        "where supported, followed by concise case background, complete numbered facts "
        "in source order, distinct grounds only where supplied, each separate relief "
        "as its own prayer clause, and appropriate uncompleted verification/signature "
        "placeholders. Never invent jurisdiction, statutory grounds, case numbers, "
        "procedural history, or relief."
    ),
    "affidavit": (
        "AFFIDAVIT FORMAT: Use an affidavit title and deponent particulars, followed by "
        "separately numbered factual statements. Do not convert allegations into sworn "
        "facts, add an oath/declaration, or claim personal knowledge. Keep verification, "
        "place/date, oath and attestation wording as clearly uncompleted placeholders "
        "unless the exact authorized wording is present in the source."
    ),
    "agreement": (
        "AGREEMENT FORMAT: Use a clear agreement title, date/place and party particulars, "
        "then organize only the terms actually supplied into distinct clauses. Preserve "
        "all obligations, amounts, dates, conditions, exceptions and defined terms. "
        "Do not invent commercial terms, warranties, penalties, governing law, dispute "
        "resolution, termination rights, or signatures; mark genuinely missing terms "
        "as placeholders for professional completion."
    ),
    "reply": (
        "REPLY FORMAT: Identify the authority/recipient and the notice, application or "
        "objection being answered. Preserve each issue in its original order and present "
        "the supplied response point-by-point. Do not concede, deny, admit, calculate, "
        "or introduce arguments or documents that are not in the source."
    ),
    "claim": (
        "CLAIM FORMAT: Identify the claimant, respondent/insurer and claim reference, "
        "then organize the event, policy/transaction details, chronology, loss or injury, "
        "supporting records and requested settlement/action. Preserve supplied figures "
        "without recalculation and never estimate or add compensation amounts."
    ),
}

_GENERIC_GUIDANCE = (
    "DOCUMENT FORMAT: Follow the selected document type's section outline. Use a "
    "professional title, relevant recipient/party details, chronological source facts, "
    "distinct issues and requested action, and appropriate closing fields. Do not "
    "force court-petition sections onto a non-petition document."
)


def get_document_type_guidance(legal_context: dict) -> str:
    """Return safe structural guidance for the selected document type."""
    document_type_id = legal_context.get("document_type_id", "")
    for family, document_types in _DOCUMENT_TYPE_RULES.items():
        if document_type_id in document_types:
            return _FAMILY_GUIDANCE[family]
    return _GENERIC_GUIDANCE


def get_supported_document_type_ids() -> set[str]:
    """Expose configured IDs for catalogue-coverage tests."""
    return set().union(*_DOCUMENT_TYPE_RULES.values())
