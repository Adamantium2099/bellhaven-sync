from executor import build_new_account_payload
from matcher import BELLHAVEN_PARENT_ID


def test_build_new_account_payload():
    facility = {
        "name": "Bellhaven of Testville",
        "address": "100 Main St",
        "city": "Testville",
        "state": "OH",
        "zip": "44000",
    }

    payload = build_new_account_payload(
        facility
    )

    assert payload == {
        "name": "Bellhaven of Testville",
        "parent_id": BELLHAVEN_PARENT_ID,
        "status": "Active",
        "billing_street": "100 Main St",
        "billing_city": "Testville",
        "billing_state": "OH",
        "billing_zip": "44000",
    }