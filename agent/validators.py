"""Business rules that decide whether a request can go straight to a team
or must wait for a person (human in the loop)."""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from .schema import Extraction, RequestType

CONFIDENCE_THRESHOLD = 0.75
POLICY_FORMAT = re.compile(r"^[A-Z]{3}-\d{4}-\d{6}$")
PHONE_FORMAT = re.compile(r"^0\d{8,9}$")

REQUIRED_FIELDS: dict[RequestType, list[str]] = {
    RequestType.ENDORSEMENT: ["policy_number", "key_date"],
    RequestType.CLAIM: ["policy_number", "plate_number", "key_date"],
    RequestType.PRE_INSPECTION: ["plate_number", "contact_phone"],
    RequestType.QUOTE: ["contact_phone"],
    RequestType.OTHER: [],
}

FIELD_LABELS = {
    "policy_number": "policy number",
    "plate_number": "licence plate",
    "key_date": "date",
    "contact_phone": "contact phone",
}

# Changing who is insured is a compliance-sensitive endorsement: always a person's call.
NAME_CHANGE_TRIGGERS = [
    "เปลี่ยนชื่อผู้เอาประกัน", "โอนกรรมสิทธิ์",
    "change of insured", "change the insured", "transfer of ownership",
]

TEAMS: dict[RequestType, str] = {
    RequestType.ENDORSEMENT: "Underwriting",
    RequestType.CLAIM: "Claims",
    RequestType.PRE_INSPECTION: "Underwriting (survey)",
    RequestType.QUOTE: "Sales",
    RequestType.OTHER: "Customer service",
}


def validate(extraction: Extraction, text: str, today: Optional[date] = None) -> list[str]:
    """Return the reasons a person must check this request. An empty list means auto-route."""
    today = today or date.today()
    issues: list[str] = []
    request_type = extraction.request_type

    if request_type == RequestType.OTHER:
        issues.append("Request type unclear, so a person needs to read it")
    if extraction.confidence < CONFIDENCE_THRESHOLD:
        issues.append(f"Low confidence ({extraction.confidence:.2f}) in the request type")

    for field in REQUIRED_FIELDS[request_type]:
        if not getattr(extraction, field):
            issues.append(f"Missing {FIELD_LABELS[field]}")

    if extraction.policy_number and not POLICY_FORMAT.match(extraction.policy_number):
        issues.append(f"Policy number {extraction.policy_number} does not match the format AAA-YYYY-NNNNNN")

    if extraction.contact_phone and not PHONE_FORMAT.match(extraction.contact_phone):
        issues.append(f"Phone number {extraction.contact_phone} is not a valid Thai number")

    if extraction.key_date:
        try:
            key_date = date.fromisoformat(extraction.key_date)
        except ValueError:
            issues.append(f"Date {extraction.key_date} could not be read")
        else:
            if request_type == RequestType.ENDORSEMENT and key_date < today:
                issues.append(f"Backdated endorsement (effective {key_date}) needs underwriter approval")
            if request_type == RequestType.CLAIM and key_date > today:
                issues.append(f"Incident date {key_date} is in the future")

    lowered = text.lower()
    if request_type == RequestType.ENDORSEMENT and any(t in lowered for t in NAME_CHANGE_TRIGGERS):
        issues.append("Change of insured or ownership: compliance requires a person to approve")

    return issues
