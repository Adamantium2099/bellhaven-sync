from decision_store import proposal_fingerprint


def test_same_proposal_has_same_fingerprint():
    proposal = {
        "type": "UPDATE_NAME",
        "website": {
            "name": "Bellhaven of Testville",
            "address": "100 Main St",
            "city": "Testville",
            "state": "OH",
            "zip": "44000",
        },
        "target_account": {
            "account_id": "account-1",
        },
        "changes": {
            "name": "Bellhaven of Testville",
        },
    }

    assert (
        proposal_fingerprint(proposal)
        == proposal_fingerprint(proposal)
    )


def test_changed_proposal_gets_new_fingerprint():
    first = {
        "type": "UPDATE_ZIP",
        "website": {
            "name": "Bellhaven of Testville",
            "address": "100 Main St",
            "city": "Testville",
            "state": "OH",
            "zip": "44000",
        },
        "target_account": {
            "account_id": "account-1",
        },
        "changes": {
            "billing_zip": "44000",
        },
    }

    second = {
        "type": "UPDATE_ZIP",
        "website": {
            "name": "Bellhaven of Testville",
            "address": "100 Main St",
            "city": "Testville",
            "state": "OH",
            "zip": "44001",
        },
        "target_account": {
            "account_id": "account-1",
        },
        "changes": {
            "billing_zip": "44001",
        },
    }

    assert (
        proposal_fingerprint(first)
        != proposal_fingerprint(second)
    )