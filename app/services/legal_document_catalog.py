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


# Document-type outlines are drafting structures, not prescribed or universally valid court forms.
DOCUMENT_TYPE_SECTIONS = {
    "divorce-petition-draft": [
        "Court heading and case particulars",
        "Petitioner particulars",
        "Respondent particulars",
        "Marriage particulars",
        "Chronology of matrimonial facts",
        "Grounds relied upon, only as alleged and supplied by the user",
        "Children, maintenance or custody details, if supplied",
        "Prior proceedings or reconciliation details, if supplied",
        "Reliefs or prayers sought",
        "Documents or annexures actually mentioned",
        "Verification and signature placeholders"
    ],
    "maintenance-application": [
        "Forum and case heading",
        "Applicant and respondent particulars",
        "Relationship and dependants",
        "Income and financial circumstances supplied",
        "Needs, expenses and dependency details",
        "Previous support or proceedings, if supplied",
        "Maintenance or interim relief requested",
        "Documents, verification and signature"
    ],
    "child-custody-petition": [
        "Court heading",
        "Applicant and respondent particulars",
        "Child particulars",
        "Caregiving and relationship background",
        "Chronology of relevant events",
        "Existing custody arrangements, if supplied",
        "Child welfare concerns supported by supplied facts",
        "Custody or visitation relief requested",
        "Documents and verification"
    ],
    "bail-application-draft": [
        "Court heading",
        "Applicant or accused particulars",
        "Case, FIR and police station references as supplied or placeholders",
        "Custody and procedural status, if supplied",
        "Brief facts of the case",
        "Grounds for seeking bail, limited to supplied submissions",
        "Undertakings or conditions only if supplied",
        "Prayer for bail",
        "Counsel and applicant signature placeholders"
    ],
    "criminal-complaint": [
        "Addressee and complainant particulars",
        "Persons complained against, if identified",
        "Incident date, time and location",
        "Chronological facts and specific conduct alleged",
        "Loss, injury or impact stated",
        "Witnesses and evidence actually mentioned",
        "Action requested",
        "Date, place and signature"
    ],
    "police-complaint": [
        "Police station addressee",
        "Complainant particulars",
        "Persons complained against, if identified",
        "Incident date, time and location",
        "Chronological facts",
        "Specific acts or losses reported",
        "Evidence or witnesses mentioned",
        "Action requested",
        "Date, place and signature"
    ],
    "affidavit": [
        "Title: Affidavit",
        "Deponent particulars",
        "Introductory identity statement",
        "Numbered factual statements limited to supplied information",
        "Verification with [Place] and [Date] placeholders if absent",
        "Deponent signature",
        "Attestation or oath section as an uncompleted placeholder"
    ],
    "partition-suit-draft": [
        "Court heading",
        "Plaintiff and defendant particulars",
        "Property description and schedule",
        "Relationship and succession facts supplied",
        "Ownership and share claims as stated",
        "Chronology of dispute and prior demands",
        "Cause-of-action facts supplied",
        "Partition and possession relief requested",
        "Valuation and jurisdiction placeholders if absent",
        "Documents and verification"
    ],
    "property-dispute-application": [
        "Addressee or forum",
        "Applicant and opposite-party particulars",
        "Property identification",
        "Ownership, possession or transaction background",
        "Chronology of dispute",
        "Specific interference or grievance",
        "Evidence and documents mentioned",
        "Relief requested",
        "Date, place and signature"
    ],
    "cheque-dishonour-notice": [
        "Sender and recipient particulars",
        "Transaction and liability background",
        "Cheque number, date, amount and bank details as supplied",
        "Presentation and dishonour particulars",
        "Demand and response period only as supplied or placeholders",
        "Payment instructions or remedy requested",
        "Signature and delivery details"
    ],
    "loan-recovery-notice": [
        "Lender and borrower particulars",
        "Loan or facility details",
        "Repayment and outstanding amount details supplied",
        "Chronology of default and communications",
        "Demand or proposed resolution",
        "Payment deadline placeholder if absent",
        "Signature and enclosures"
    ],
    "consumer-complaint": [
        "Forum heading",
        "Complainant and opposite-party particulars",
        "Product or service details",
        "Purchase or service transaction",
        "Chronology of deficiency or unfair conduct alleged",
        "Loss or impact stated",
        "Prior attempts to resolve",
        "Reliefs or compensation requested",
        "Documents and verification"
    ],
    "refund-demand-notice": [
        "Sender and recipient particulars",
        "Order or service details",
        "Payment amount and date supplied",
        "Reason for refund request",
        "Prior communications",
        "Refund demand and deadline placeholder if absent",
        "Requested resolution",
        "Date and signature"
    ],
    "salary-recovery-notice": [
        "Employee and employer particulars",
        "Employment details",
        "Unpaid salary period",
        "Amount breakdown as supplied",
        "Chronology of non-payment and follow-ups",
        "Demand for payment",
        "Response deadline placeholder if absent",
        "Date and signature"
    ],
    "termination-dispute-representation": [
        "Employee and employer particulars",
        "Employment details",
        "Termination decision and date",
        "Chronology and circumstances supplied",
        "Grounds of dispute as stated by employee",
        "Impact and outstanding dues, if supplied",
        "Relief requested",
        "Supporting documents and signature"
    ],
    "partnership-agreement-draft": [
        "Agreement title, date and place placeholders",
        "Partner particulars",
        "Business name, purpose and place",
        "Capital contributions and ownership shares as supplied",
        "Roles and responsibilities",
        "Profit and loss sharing as supplied or placeholders",
        "Accounts and decision-making",
        "Duration, exit, dissolution and dispute terms only as instructed",
        "Partner and witness signature placeholders"
    ],
    "cybercrime-complaint": [
        "Cybercrime authority addressee",
        "Complainant particulars",
        "Incident type and platform",
        "Date and time chronology",
        "Accounts, phone numbers, URLs or identifiers supplied",
        "Financial loss and transaction references, if any",
        "Reports already filed and acknowledgement numbers",
        "Digital evidence actually available",
        "Action requested",
        "Date and signature"
    ],
    "online-fraud-complaint": [
        "Authority addressee",
        "Complainant particulars",
        "Fraud platform or communication channel",
        "Chronology of events",
        "Payment and transaction details supplied",
        "Amount lost and date",
        "Bank or platform reporting already completed",
        "Evidence and reference numbers",
        "Assistance requested",
        "Date and signature"
    ],
    "compensation-claim-draft": [
        "Tribunal or forum heading",
        "Claimant and respondent particulars",
        "Accident date, time and location",
        "Vehicle and insurance details supplied",
        "Chronology and circumstances",
        "Injuries and treatment details supplied",
        "Employment, income and expenses supplied",
        "Losses claimed without unsupported calculations",
        "Relief sought",
        "Documents and verification"
    ],
    "writ-petition-draft": [
        "Court heading",
        "Petitioner and respondent particulars",
        "Challenged action or omission as supplied",
        "Synopsis and list of dates from source chronology",
        "Facts of the case",
        "Grounds urged, limited to supplied material",
        "Reliefs expressly sought",
        "Interim relief only if requested",
        "Annexures actually mentioned",
        "Verification and signature"
    ],
    "tax-reply-draft": [
        "Tax authority addressee",
        "Taxpayer particulars and identifier placeholders",
        "Notice or proceeding reference",
        "Issue-wise response to points raised in source",
        "Facts and explanations supplied",
        "Supporting records actually mentioned",
        "Clarification or relief requested",
        "Verification and authorized signature"
    ],
    "education-complaint": [
        "Institution or authority addressee",
        "Student particulars",
        "Institution and course details",
        "Admission, examination or academic reference",
        "Chronology of events",
        "Specific grievance and impact",
        "Previous representations and responses",
        "Resolution requested",
        "Documents, date and signature"
    ],
    "environmental-complaint": [
        "Environmental authority addressee",
        "Complainant particulars",
        "Location and site details",
        "Nature of environmental concern",
        "Chronology and observed effects",
        "Persons or entities involved, if identified",
        "Evidence actually mentioned",
        "Inspection or corrective action requested",
        "Date and signature"
    ],
    "copyright-infringement-notice": [
        "Rights-holder and recipient particulars",
        "Work or material identification",
        "Ownership or authorization facts supplied",
        "Description and location of alleged use",
        "Evidence and dates supplied",
        "Specific demands only as instructed",
        "Response deadline placeholder if absent",
        "Reservation of rights and signature"
    ],
    "trademark-objection-reply": [
        "Registry or authority addressee",
        "Applicant and trademark particulars",
        "Application and examination reference",
        "Objection points stated in source",
        "Point-wise response based only on supplied facts and arguments",
        "Supporting documents mentioned",
        "Clarification or relief requested",
        "Authorized signature and date"
    ],
    "visa-representation": [
        "Immigration authority addressee",
        "Applicant particulars",
        "Passport and application reference placeholders",
        "Visa category and travel purpose as supplied",
        "Relevant personal and travel facts",
        "Application or refusal chronology",
        "Supporting documents mentioned",
        "Reconsideration or relief requested",
        "Date and signature"
    ],
    "immigration-appeal-draft": [
        "Appellate authority heading",
        "Appellant particulars",
        "Decision and reference details",
        "Timeline of application and decision",
        "Grounds of appeal based only on supplied material",
        "Supporting facts and documents",
        "Relief sought",
        "Verification and signature"
    ]
}


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
        "format_sections": DOCUMENT_TYPE_SECTIONS.get(document_type["id"], [
            "Title and addressee", "Relevant parties and reference details",
            "Chronological facts supplied by the user", "Specific issue or request",
            "Supporting documents actually mentioned", "Relief or action requested",
            "Date, place and signature placeholders where appropriate",
        ]),
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
