"""Data models shared by the extractors, the validators and the workflow."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RequestType(str, Enum):
    ENDORSEMENT = "endorsement"
    CLAIM = "claim"
    PRE_INSPECTION = "pre_inspection"
    QUOTE = "quote"
    OTHER = "other"


class Extraction(BaseModel):
    """What the agent reads out of one broker email."""

    request_type: RequestType = Field(
        description="endorsement, claim, pre_inspection, quote or other"
    )
    confidence: float = Field(
        description="Confidence in request_type, from 0 to 1"
    )
    policy_number: Optional[str] = Field(
        default=None, description="Policy number copied exactly as written"
    )
    insured_name: Optional[str] = Field(
        default=None, description="Current insured person, without honorifics"
    )
    plate_number: Optional[str] = Field(
        default=None, description="Thai licence plate such as 1กข 1234, without the province"
    )
    key_date: Optional[str] = Field(
        default=None,
        description="Main date (effective, incident or appointment) as YYYY-MM-DD, Gregorian calendar",
    )
    contact_phone: Optional[str] = Field(
        default=None, description="Contact phone number, digits only"
    )
    summary: str = Field(
        default="", description="One short English sentence describing what the sender wants"
    )
