# Evaluation results

50 labelled emails, evaluation date 2026-10-10.

| Metric | rule-based baseline | gemini-3.5-flash-lite |
| --- | --- | --- |
| Request type | 39/50 (78%) | 50/50 (100%) |
| Routing decision | 40/50 (80%) | 50/50 (100%) |
| Policy number | 49/50 (98%) | 50/50 (100%) |
| Licence plate | 50/50 (100%) | 50/50 (100%) |
| Key date | 35/46 (76%) | 46/46 (100%) |
| Contact phone | 47/50 (94%) | 50/50 (100%) |
| Insured name | 19/20 (95%) | 20/20 (100%) |

## Mistakes: rule-based baseline (37, errors: 0)

- #13 route: expected 'auto', got 'human_review' ['Missing date']
- #13 key_date: expected '2026-10-15', got None
- #14 request_type: expected 'endorsement', got 'other'
- #14 route: expected 'auto', got 'human_review' ['Request type unclear, so a person needs to read it', 'Low confidence (0.30) in the request type']
- #14 key_date: expected '2026-10-12', got None
- #14 contact_phone: expected '0817654321', got None
- #16 request_type: expected 'endorsement', got 'other'
- #16 route: expected 'auto', got 'human_review' ['Request type unclear, so a person needs to read it', 'Low confidence (0.30) in the request type']
- #16 key_date: expected '2026-11-01', got None
- #16 contact_phone: expected '038123456', got None
- #18 request_type: expected 'endorsement', got 'other'
- #19 request_type: expected 'endorsement', got 'other'
- #19 route: expected 'auto', got 'human_review' ['Request type unclear, so a person needs to read it', 'Low confidence (0.30) in the request type']
- #19 key_date: expected '2026-10-20', got None
- #20 request_type: expected 'endorsement', got 'other'
- #20 route: expected 'auto', got 'human_review' ['Request type unclear, so a person needs to read it', 'Low confidence (0.30) in the request type']
- #21 key_date: expected '2026-09-01', got None
- #23 request_type: expected 'claim', got 'other'
- #23 route: expected 'auto', got 'human_review' ['Request type unclear, so a person needs to read it', 'Low confidence (0.30) in the request type']
- #23 key_date: expected '2026-10-09', got None
- #24 key_date: expected '2026-10-07', got '2026-10-10'
- #25 request_type: expected 'claim', got 'other'
- #26 route: expected 'auto', got 'human_review' ['Missing date']
- #26 key_date: expected '2026-10-09', got None
- #26 insured_name: expected 'Wichai Boonsong', got None
- #31 route: expected 'auto', got 'human_review' ['Missing date']
- #31 key_date: expected '2026-10-07', got None
- #32 key_date: expected '2026-10-13', got None
- #36 route: expected 'auto', got 'human_review' ['Missing contact phone']
- #36 key_date: expected '2026-10-12', got None
- #36 contact_phone: expected '0815550909', got None
- #38 request_type: expected 'quote', got 'other'
- #38 route: expected 'auto', got 'human_review' ['Request type unclear, so a person needs to read it', 'Low confidence (0.30) in the request type']
- #44 request_type: expected 'other', got 'claim'
- #44 policy_number: expected None, got 'CLM-2026-000981'
- #48 request_type: expected 'other', got 'quote'
- #50 request_type: expected 'other', got 'claim'

## Mistakes: gemini-3.5-flash-lite (0, errors: 0)

None.
