"""India-only legal document catalogue used by the optional formatting mode.

The catalogue contains selectable document types, not authoritative court templates.
Add future jurisdictions as separate catalogue entries rather than reusing Indian options.
"""

INDIA_JURISDICTION = "IN"

LEGAL_CATEGORIES = [
    {"id": "lottery-prize-disputes", "label": "Lottery and Prize Disputes", "document_types": [
        {"id": "legal-notice", "label": "Legal Notice"},
        {"id": "prize-claim-application", "label": "Prize Claim Application"},
        {"id": "police-complaint", "label": "Police Complaint"},
        {"id": "affidavit", "label": "Affidavit"},
    ]},
    {"id": "family-matrimonial-law", "label": "Family and Matrimonial Law", "document_types": [
        {"id": "divorce-petition-draft", "label": "Divorce Petition Draft"},
        {"id": "maintenance-application", "label": "Maintenance Application"},
        {"id": "child-custody-petition", "label": "Child Custody Petition"},
        {"id": "affidavit", "label": "Affidavit"},
    ]},
    {"id": "property-land-disputes", "label": "Property and Land Disputes", "document_types": [
        {"id": "legal-notice", "label": "Legal Notice"},
        {"id": "partition-suit-draft", "label": "Partition Suit Draft"},
        {"id": "property-dispute-application", "label": "Property Dispute Application"},
        {"id": "affidavit", "label": "Affidavit"},
    ]},
    {"id": "criminal-law", "label": "Criminal Law", "document_types": [
        {"id": "criminal-complaint", "label": "Criminal Complaint"},
        {"id": "bail-application-draft", "label": "Bail Application Draft"},
        {"id": "police-representation", "label": "Police Representation"},
        {"id": "affidavit", "label": "Affidavit"},
    ]},
    {"id": "banking-finance", "label": "Banking and Finance", "document_types": [
        {"id": "cheque-dishonour-notice", "label": "Cheque Dishonour Notice"},
        {"id": "loan-recovery-notice", "label": "Loan Recovery Notice"},
        {"id": "banking-grievance", "label": "Banking Grievance Representation"},
    ]},
    {"id": "consumer-protection", "label": "Consumer Protection", "document_types": [
        {"id": "consumer-complaint", "label": "Consumer Complaint"},
        {"id": "refund-demand-notice", "label": "Refund Demand Notice"},
        {"id": "deficiency-service-representation", "label": "Deficiency in Service Representation"},
    ]},
    {"id": "employment-labour-law", "label": "Employment and Labour Law", "document_types": [
        {"id": "salary-recovery-notice", "label": "Salary Recovery Notice"},
        {"id": "termination-dispute-representation", "label": "Termination Dispute Representation"},
        {"id": "employment-grievance", "label": "Employment Grievance"},
    ]},
    {"id": "business-corporate-law", "label": "Business and Corporate Law", "document_types": [
        {"id": "legal-notice", "label": "Legal Notice"},
        {"id": "partnership-agreement-draft", "label": "Partnership Agreement Draft"},
        {"id": "business-representation", "label": "Business Representation"},
    ]},
    {"id": "cybercrime", "label": "Cybercrime", "document_types": [
        {"id": "cybercrime-complaint", "label": "Cybercrime Complaint"},
        {"id": "online-fraud-complaint", "label": "Online Fraud Complaint"},
        {"id": "cyber-incident-representation", "label": "Cyber Incident Representation"},
    ]},
    {"id": "motor-accident-claims", "label": "Motor Accident Claims", "document_types": [
        {"id": "compensation-claim-draft", "label": "Compensation Claim Draft"},
        {"id": "accident-related-petition", "label": "Accident-Related Petition"},
        {"id": "insurance-claim-representation", "label": "Insurance Claim Representation"},
    ]},
    {"id": "taxation", "label": "Taxation", "document_types": [
        {"id": "tax-reply-draft", "label": "Tax Reply Draft"},
        {"id": "tax-representation", "label": "Tax Representation"},
        {"id": "tax-objection-draft", "label": "Tax Objection Draft"},
    ]},
    {"id": "constitutional-law", "label": "Constitutional Law", "document_types": [
        {"id": "writ-petition-draft", "label": "Writ Petition Draft"},
        {"id": "constitutional-representation", "label": "Constitutional Representation"},
    ]},
    {"id": "education-law", "label": "Education Law", "document_types": [
        {"id": "education-complaint", "label": "Education Complaint"},
        {"id": "admission-dispute-representation", "label": "Admission Dispute Representation"},
        {"id": "academic-grievance", "label": "Academic Grievance"},
    ]},
    {"id": "environmental-law", "label": "Environmental Law", "document_types": [
        {"id": "environmental-complaint", "label": "Environmental Complaint"},
        {"id": "legal-notice", "label": "Legal Notice"},
        {"id": "environmental-representation", "label": "Environmental Representation"},
    ]},
    {"id": "intellectual-property", "label": "Intellectual Property", "document_types": [
        {"id": "copyright-infringement-notice", "label": "Copyright Infringement Notice"},
        {"id": "trademark-objection-reply", "label": "Trademark Objection Reply"},
        {"id": "ip-infringement-representation", "label": "IP Infringement Representation"},
    ]},
    {"id": "immigration", "label": "Immigration", "document_types": [
        {"id": "visa-representation", "label": "Visa Representation"},
        {"id": "immigration-appeal-draft", "label": "Immigration Appeal Draft"},
        {"id": "immigration-explanation", "label": "Immigration Explanation"},
    ]},
]


def get_legal_catalog() -> dict:
    return {
        "jurisdictions": [{"id": INDIA_JURISDICTION, "label": "India"}],
        "categories": LEGAL_CATEGORIES,
    }


def get_legal_context(jurisdiction: str, category_id: str, document_type_id: str) -> dict:
    if jurisdiction != INDIA_JURISDICTION:
        raise ValueError("The selected legal jurisdiction is not supported.")
    category = next((item for item in LEGAL_CATEGORIES if item["id"] == category_id), None)
    if category is None:
        raise ValueError("Select a valid legal category.")
    document_type = next((item for item in category["document_types"] if item["id"] == document_type_id), None)
    if document_type is None:
        raise ValueError("Select a document type available for the chosen legal category.")
    return {
        "jurisdiction": INDIA_JURISDICTION,
        "jurisdiction_label": "India",
        "category_id": category["id"],
        "category_label": category["label"],
        "document_type_id": document_type["id"],
        "document_type_label": document_type["label"],
    }


def validate_document_metadata(mode: str, jurisdiction: str | None, category_id: str | None, document_type_id: str | None) -> dict:
    if mode == "general":
        if any(value is not None for value in (jurisdiction, category_id, document_type_id)):
            raise ValueError("General documents cannot contain legal category selections.")
        return {"formatting_mode": "general", "jurisdiction": None, "legal_category": None, "document_type": None}
    if mode != "legal":
        raise ValueError("Select General Document or Legal Document.")
    if not all((jurisdiction, category_id, document_type_id)):
        raise ValueError("Select a jurisdiction, legal category, and document type.")
    get_legal_context(jurisdiction, category_id, document_type_id)
    return {
        "formatting_mode": "legal",
        "jurisdiction": jurisdiction,
        "legal_category": category_id,
        "document_type": document_type_id,
    }
