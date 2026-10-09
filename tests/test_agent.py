from datetime import date

import pytest

from agent.graph import build_graph
from agent.llm import RuleBasedExtractor, find_first_date, normalise_plate
from agent.schema import Extraction, RequestType
from agent.store import RequestStore
from agent.validators import validate

TODAY = date(2026, 10, 10)


def make(**overrides) -> Extraction:
    base = dict(
        request_type=RequestType.ENDORSEMENT,
        confidence=0.9,
        policy_number="MTR-2026-004512",
        key_date="2026-10-15",
        contact_phone="0812345678",
    )
    base.update(overrides)
    return Extraction(**base)


# --- parsing helpers -------------------------------------------------------

def test_buddhist_era_date_is_converted():
    assert find_first_date("มีผลตั้งแต่วันที่ 15/10/2569") == "2026-10-15"


def test_iso_date_is_kept():
    assert find_first_date("effective 2026-10-20.") == "2026-10-20"


def test_plate_is_normalised():
    assert normalise_plate("1กข1234") == "1กข 1234"


def test_rule_based_extraction_reads_thai_claim():
    text = "แจ้งเคลม กรมธรรม์ MTR-2026-002210 รถทะเบียน 1กข 1234 ถูกชน เมื่อวันที่ 08/10/2569 โทร 062-345-6789"
    result = RuleBasedExtractor().extract(text)
    assert result.request_type == RequestType.CLAIM
    assert result.policy_number == "MTR-2026-002210"
    assert result.plate_number == "1กข 1234"
    assert result.key_date == "2026-10-08"
    assert result.contact_phone == "0623456789"


# --- business rules --------------------------------------------------------

def test_clean_endorsement_has_no_issues():
    assert validate(make(), "please endorse", TODAY) == []


def test_malformed_policy_number_is_flagged():
    issues = validate(make(policy_number="MTR-2026-07731"), "", TODAY)
    assert any("does not match the format" in issue for issue in issues)


def test_backdated_endorsement_is_flagged():
    issues = validate(make(key_date="2026-09-01"), "", TODAY)
    assert any("Backdated" in issue for issue in issues)


def test_future_claim_is_flagged():
    claim = make(request_type=RequestType.CLAIM, plate_number="1กข 1234", key_date="2026-11-02")
    assert any("in the future" in issue for issue in validate(claim, "", TODAY))


def test_change_of_insured_always_needs_a_person():
    issues = validate(make(), "ขอโอนกรรมสิทธิ์ เปลี่ยนชื่อผู้เอาประกัน", TODAY)
    assert any("compliance" in issue for issue in issues)


def test_low_confidence_is_flagged():
    assert any("Low confidence" in issue for issue in validate(make(confidence=0.5), "", TODAY))


# --- end-to-end workflow ---------------------------------------------------

@pytest.fixture
def workflow(tmp_path):
    store = RequestStore(str(tmp_path / "test.db"))
    return build_graph(RuleBasedExtractor(), store), store


def test_clear_request_is_routed_automatically(workflow):
    graph, store = workflow
    text = "Please endorse policy MTR-2026-004512 to change the address, effective 2026-10-15. Call 081 234 5678."
    result = graph.invoke({"text": text, "today": "2026-10-10"})
    assert result["route"] == "auto"
    assert result["team"] == "Underwriting"
    assert store.get(result["record_id"])["status"] == "queued_for_team"


def test_unclear_request_waits_for_review_and_is_audited(workflow):
    graph, store = workflow
    result = graph.invoke({"text": "สวัสดีครับ สาขาเปิดวันเสาร์ไหม", "today": "2026-10-10"})
    assert result["route"] == "human_review"
    assert [r["id"] for r in store.review_queue()] == [result["record_id"]]

    store.decide(result["record_id"], reviewer="Tent", approve=True, note="Forwarded to customer service")
    assert store.review_queue() == []
    actions = [entry["action"] for entry in store.history(result["record_id"])]
    assert actions == ["triaged", "approved"]
