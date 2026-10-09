"""Extractors that turn a broker email into an Extraction.

Two interchangeable implementations:
  * GeminiExtractor: an LLM with structured JSON output (used when GEMINI_API_KEY is set).
  * RuleBasedExtractor: keywords and regular expressions, so the project runs offline
    and gives a baseline to compare the LLM against.

Both outputs pass through clean_extraction(), so phone numbers, Thai digits and plates
are formatted the same way before the business rules see them.
"""

from __future__ import annotations

import os
import re
import time
from datetime import date
from typing import Optional, Protocol

from .schema import Extraction, RequestType

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"

SYSTEM_PROMPT = """You triage emails sent by insurance brokers to a Thai motor insurer.
Emails may be in Thai, English or both. Today's date is given before the email.

Fill in the JSON schema:
- request_type:
  * endorsement: a change to an existing policy (address, driver, vehicle, cover, insured
    name or ownership).
  * claim: a new report of an accident, damage or theft.
  * pre_inspection: a request to inspect a vehicle before cover starts or renews.
  * quote: a request for a price, premium or quotation, including renewal quotes.
  * other: everything else, such as status enquiries about existing claims, payment
    confirmations, document requests, coverage questions, complaints and marketing.
- confidence: your confidence in request_type, from 0 to 1. Use a value below 0.75 when
  the email is ambiguous.
- policy_number: copy it exactly as written, for example MTR-2026-004512. Never correct it.
  A claim reference (such as CLM-...) is not a policy number.
- insured_name: the insured person, only if the email names them, without honorifics such
  as คุณ, Mr or Ms.
- plate_number: the Thai licence plate, for example 1กข 1234, without the province.
- key_date: as YYYY-MM-DD in the Gregorian calendar. Use the effective date for an
  endorsement, the incident date for a claim and the appointment date for a
  pre_inspection; otherwise null. Thai dates often use the Buddhist Era: subtract 543
  from the year (2569 is 2026, and a short year such as 69 means 2569). Thai month
  abbreviations: ม.ค. Jan, ก.พ. Feb, มี.ค. Mar, เม.ย. Apr, พ.ค. May, มิ.ย. Jun, ก.ค. Jul,
  ส.ค. Aug, ก.ย. Sep, ต.ค. Oct, พ.ย. Nov, ธ.ค. Dec. If the year is missing, use today's
  date to work it out.
- contact_phone: digits only, for example 0812345678.
- summary: one short English sentence describing what the sender wants.

Use null for anything the email does not state. Never invent values."""

RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL")


class Extractor(Protocol):
    name: str

    def extract(self, text: str, today: Optional[date] = None) -> Extraction: ...


class GeminiExtractor:
    """Calls Gemini with a JSON schema so the reply is always valid, typed data."""

    def __init__(self, api_key: str, model: Optional[str] = None, max_retries: int = 5):
        from google import genai  # imported here so offline use needs no network setup

        self.client = genai.Client(api_key=api_key)
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.name = self.model
        self.max_retries = max_retries

    def extract(self, text: str, today: Optional[date] = None) -> Extraction:
        from google.genai import types

        today = today or date.today()
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=Extraction,
        )
        contents = f"Today's date: {today.isoformat()}\n\nBroker email:\n{text}"

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
                break
            except Exception as error:  # rate limits and brief outages: wait and retry
                if attempt == self.max_retries or not any(code in str(error) for code in RETRYABLE):
                    raise
                time.sleep(min(5 * 2**attempt, 60))

        parsed = response.parsed
        result = parsed if isinstance(parsed, Extraction) else Extraction.model_validate_json(response.text)
        result.confidence = min(max(result.confidence, 0.0), 1.0)
        return result


# ---------------------------------------------------------------------------
# Shared clean-up
# ---------------------------------------------------------------------------

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def normalise_plate(plate: str) -> str:
    plate = re.sub(r"\s+", "", plate)
    return re.sub(r"([ก-ฮ])(\d)", r"\1 \2", plate)


def normalise_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone.translate(THAI_DIGITS))
    if digits.startswith("66") and len(digits) in (10, 11):  # +66 81 234 5678 -> 0812345678
        digits = "0" + digits[2:]
    return digits


def clean_extraction(extraction: Extraction) -> Extraction:
    """Format fields consistently, whichever extractor produced them."""
    data = extraction.model_dump()
    for field in ("policy_number", "insured_name", "plate_number", "key_date", "contact_phone"):
        value = data[field]
        if isinstance(value, str):
            value = value.strip().translate(THAI_DIGITS)
        data[field] = value or None
    if data["plate_number"]:
        data["plate_number"] = normalise_plate(data["plate_number"])
    if data["contact_phone"]:
        data["contact_phone"] = normalise_phone(data["contact_phone"]) or None
    return Extraction(**data)


# ---------------------------------------------------------------------------
# Offline rule-based baseline
# ---------------------------------------------------------------------------

KEYWORDS: dict[RequestType, list[str]] = {
    RequestType.ENDORSEMENT: [
        "สลักหลัง", "เปลี่ยนที่อยู่", "เปลี่ยนชื่อ", "เพิ่มผู้ขับขี่", "โอนกรรมสิทธิ์",
        "endorse", "named driver", "change of address", "amend",
    ],
    RequestType.CLAIM: [
        "เคลม", "อุบัติเหตุ", "ชน", "เฉี่ยว",
        "claim", "accident", "collision", "scratch", "damage",
    ],
    RequestType.PRE_INSPECTION: ["ตรวจสภาพ", "pre-inspection", "inspection"],
    RequestType.QUOTE: ["เสนอราคา", "ขอราคา", "เบี้ย", "quotation", "quote", "premium"],
}

POLICY_RE = re.compile(r"(?<![A-Za-z])[A-Z]{3}-\d{4}-\d{3,8}(?!\d)")
PLATE_RE = re.compile(
    r"(?:ทะเบียน|plate(?:\s*(?:no\.?|number))?)\s*:?\s*(\d?[ก-ฮ]{1,2}\s?\d{1,4})(?!\d)",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?<!\d)0\d{1,2}[- ]?\d{3}[- ]?\d{4}(?!\d)")
ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
DMY_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")
INSURED_RE = re.compile(r"(?:ผู้เอาประกัน(?:ภัย)?|Insured(?:\s+name)?)\s*:\s*([^\n.,]+)", re.IGNORECASE)
HONORIFIC_RE = re.compile(r"^(?:คุณ|Khun|Mrs|Mr|Ms|Miss)\.?\s*", re.IGNORECASE)


def to_iso_date(year: int, month: int, day: int) -> Optional[str]:
    """Build an ISO date, converting Buddhist Era years (e.g. 2569) to Gregorian (2026)."""
    if year > 2400:
        year -= 543
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def find_first_date(text: str) -> Optional[str]:
    candidates = []
    for match in ISO_DATE_RE.finditer(text):
        y, m, d = (int(g) for g in match.groups())
        candidates.append((match.start(), to_iso_date(y, m, d)))
    for match in DMY_DATE_RE.finditer(text):
        d, m, y = (int(g) for g in match.groups())
        candidates.append((match.start(), to_iso_date(y, m, d)))
    for _, iso in sorted(candidates):
        if iso:
            return iso
    return None


class RuleBasedExtractor:
    """Keyword scoring plus regular expressions. Fast and free, but brittle."""

    name = "rule-based baseline"

    def classify(self, text: str) -> tuple[RequestType, float]:
        lowered = text.lower()
        scores = {
            request_type: sum(1 for keyword in keywords if keyword in lowered)
            for request_type, keywords in KEYWORDS.items()
        }
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        (best_type, best), (_, runner_up) = ranked[0], ranked[1]
        if best == 0:
            return RequestType.OTHER, 0.3
        if best == runner_up:
            return best_type, 0.5
        return best_type, min(0.75 + 0.05 * best, 0.95)

    def extract(self, text: str, today: Optional[date] = None) -> Extraction:
        text = text.translate(THAI_DIGITS)
        request_type, confidence = self.classify(text)

        policy = POLICY_RE.search(text)
        plate = PLATE_RE.search(text)
        phone = PHONE_RE.search(text)
        insured = INSURED_RE.search(text)

        insured_name = None
        if insured:
            name = re.split(r"\s+(?:โทร|ติดต่อ|tel\.?|call)|\d", insured.group(1), flags=re.IGNORECASE)[0]
            insured_name = HONORIFIC_RE.sub("", name.strip()).strip() or None

        first_line = text.strip().splitlines()[0] if text.strip() else ""
        return Extraction(
            request_type=request_type,
            confidence=confidence,
            policy_number=policy.group(0) if policy else None,
            insured_name=insured_name,
            plate_number=plate.group(1) if plate else None,
            key_date=find_first_date(text),
            contact_phone=phone.group(0) if phone else None,
            summary=f"{request_type.value} request: {first_line[:100]}",
        )


def get_extractor() -> Extractor:
    """Use Gemini when an API key is configured, otherwise the offline baseline."""
    try:
        from dotenv import load_dotenv  # reads GEMINI_API_KEY from a local .env file

        load_dotenv()
    except ImportError:
        pass
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return GeminiExtractor(api_key)
    return RuleBasedExtractor()
