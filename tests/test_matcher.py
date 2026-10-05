from matcher import (
    BELLHAVEN_PARENT_ID,
    candidate_evidence,
    chow_required,
    choose_survivor,
    find_stale_bellhaven_accounts,
    normalize_address,
    normalize_text,
    normalize_zip,
    reconcile_facility,
)


def test_normalize_address_abbreviations():
    assert (
        normalize_address("2301 Cleveland Road")
        == normalize_address("2301 Cleveland Rd")
    )

    assert (
        normalize_address("4850 Northwest Sylvania Avenue")
        == normalize_address("4850 NW Sylvania Ave")
    )


def test_normalize_text_handles_ampersand():
    assert (
        normalize_text("Rehabilitation & Nursing")
        == normalize_text("Rehabilitation and Nursing")
    )


def test_zip_normalization():
    assert normalize_zip("44236-1234") == "44236"
    assert normalize_zip("44236") == "44236"


def test_same_name_different_location_is_not_exact_location():
    facility = {
        "name": "Amberly Manor",
        "address": "4390 Darrow Rd",
        "city": "Hudson",
        "state": "OH",
        "zip": "44236",
    }

    account = {
        "account_id": "test-account",
        "name": "Amberly Manor",
        "parent_id": "other-parent",
        "parent_name": "Other Parent",
        "billing_street": "918 S Nevada Ave",
        "billing_city": "Colorado Springs",
        "billing_state": "CO",
        "billing_zip": "80903",
        "care_type": "Assisted Living",
        "status": "Active",
        "phone": "",
        "lifetime_revenue": 0,
        "outstanding_ar": 0,
        "duplicate_of_account": "",
        "chow_current_account": "",
        "note": "",
    }

    evidence = candidate_evidence(
        facility,
        account,
    )

    assert evidence["name_score"] == 100
    assert evidence["state_match"] is False
    assert evidence["zip_match"] is False
    assert evidence["exact_location"] is False


def test_chow_requires_revenue_and_ar():
    assert chow_required(
        {
            "lifetime_revenue": 50000,
            "outstanding_ar": 5000,
        }
    )

    assert not chow_required(
        {
            "lifetime_revenue": 50000,
            "outstanding_ar": 0,
        }
    )

    assert not chow_required(
        {
            "lifetime_revenue": 0,
            "outstanding_ar": 5000,
        }
    )


def test_survivor_prefers_bellhaven_account():
    candidates = [
        {
            "account_id": "other",
            "parent_id": "other-parent",
            "lifetime_revenue": 0,
            "outstanding_ar": 0,
            "name_score": 100,
        },
        {
            "account_id": "bellhaven",
            "parent_id": BELLHAVEN_PARENT_ID,
            "lifetime_revenue": 0,
            "outstanding_ar": 0,
            "name_score": 95,
        },
    ]

    survivor = choose_survivor(candidates)

    assert survivor["account_id"] == "bellhaven"


def test_survivor_prefers_financial_history_within_same_parent():
    candidates = [
        {
            "account_id": "no-history",
            "parent_id": BELLHAVEN_PARENT_ID,
            "lifetime_revenue": 0,
            "outstanding_ar": 0,
            "name_score": 100,
        },
        {
            "account_id": "history",
            "parent_id": BELLHAVEN_PARENT_ID,
            "lifetime_revenue": 50000,
            "outstanding_ar": 0,
            "name_score": 95,
        },
    ]

    survivor = choose_survivor(candidates)

    assert survivor["account_id"] == "history"


def test_represented_bellhaven_account_is_not_stale():
    account = {
        "account_id": "represented-account",
        "name": "Bellhaven of Testville",
        "parent_id": BELLHAVEN_PARENT_ID,
        "billing_street": "100 Main St",
        "billing_city": "Testville",
        "billing_state": "OH",
        "billing_zip": "44000",
        "status": "Active",
        "lifetime_revenue": 50000,
        "outstanding_ar": 5000,
    }

    proposals = find_stale_bellhaven_accounts(
        [account],
        {"represented-account"},
    )

    assert proposals == []


def test_reverse_chow_links_historical_account():
    historical = {
        "account_id": "old-bellhaven",
        "name": "Bellhaven of Testville",
        "parent_id": BELLHAVEN_PARENT_ID,
        "billing_street": "100 Main St",
        "billing_city": "Testville",
        "billing_state": "OH",
        "billing_zip": "44000",
        "status": "Active",
        "lifetime_revenue": 130000,
        "outstanding_ar": 5200,
        "chow_current_account": "",
        "duplicate_of_account": "",
    }

    successor = {
        "account_id": "new-operator",
        "name": "New Operator of Testville",
        "parent_id": "different-parent",
        "billing_street": "100 Main Street",
        "billing_city": "Testville",
        "billing_state": "OH",
        "billing_zip": "44000",
        "status": "Active",
        "lifetime_revenue": 0,
        "outstanding_ar": 0,
        "chow_current_account": "",
        "duplicate_of_account": "",
    }

    proposals = find_stale_bellhaven_accounts(
        [historical, successor],
        set(),
    )

    assert len(proposals) == 1
    assert proposals[0]["type"] == "LINK_CHOW_SUCCESSOR"

    assert (
        proposals[0]["changes"]["chow_current_account"]
        == "new-operator"
    )


def test_already_resolved_duplicate_is_not_reproposed():
    """
    Once a duplicate has been marked Inactive and points to the selected
    survivor, rerunning reconciliation must not propose MARK_DUPLICATE again.
    """
    facility = {
        "name": "Bellhaven of Owosso",
        "address": "1120 W Main St",
        "city": "Owosso",
        "state": "MI",
        "zip": "48867",
    }

    survivor = {
        "account_id": "survivor",
        "name": "Bellhaven of Owosso",
        "parent_id": BELLHAVEN_PARENT_ID,
        "parent_name": "Bellhaven Senior Living",
        "billing_street": "1120 W Main St",
        "billing_city": "Owosso",
        "billing_state": "MI",
        "billing_zip": "48867",
        "care_type": "Assisted Living",
        "status": "Active",
        "phone": "",
        "lifetime_revenue": 0,
        "outstanding_ar": 0,
        "duplicate_of_account": "",
        "chow_current_account": "",
        "note": "",
    }

    loser = {
        **survivor,
        "account_id": "loser",
        "billing_street": "1120 West Main Street",
        "status": "Inactive",
        "duplicate_of_account": "survivor",
    }

    result = reconcile_facility(
        facility,
        [survivor, loser],
    )

    proposal_types = [
        proposal["type"]
        for proposal in result["proposals"]
    ]

    assert "MARK_DUPLICATE" not in proposal_types
    assert "SAME_LOCATION_REVIEW" not in proposal_types


def test_already_linked_chow_successor_is_not_reproposed():
    """
    Once a historical Bellhaven account already points to its identified
    successor, rerunning the reverse pass must not propose another CHOW link
    or incorrectly classify the historical account as stale.
    """
    historical = {
        "account_id": "historical",
        "name": "Bellhaven of Sandusky",
        "parent_id": BELLHAVEN_PARENT_ID,
        "billing_street": "2715 Columbus Ave",
        "billing_city": "Sandusky",
        "billing_state": "OH",
        "billing_zip": "44870",
        "status": "Active",
        "lifetime_revenue": 130000,
        "outstanding_ar": 5200,
        "chow_current_account": "successor",
        "duplicate_of_account": "",
    }

    successor = {
        "account_id": "successor",
        "name": "Millstone Care of Sandusky",
        "parent_id": "different-parent",
        "billing_street": "2715 Columbus Ave",
        "billing_city": "Sandusky",
        "billing_state": "OH",
        "billing_zip": "44870",
        "status": "Active",
        "lifetime_revenue": 0,
        "outstanding_ar": 0,
        "chow_current_account": "",
        "duplicate_of_account": "",
    }

    proposals = find_stale_bellhaven_accounts(
        [historical, successor],
        set(),
    )

    proposal_types = [
        proposal["type"]
        for proposal in proposals
    ]

    assert "LINK_CHOW_SUCCESSOR" not in proposal_types
    assert "STALE_BELLHAVEN_ACCOUNT" not in proposal_types


def test_completed_chow_pair_is_not_same_location_review():
    """
    After CHOW_CREATE has created the new Bellhaven account and linked the
    historical account to it, rerunning reconciliation must recognize the
    relationship as resolved rather than generating SAME_LOCATION_REVIEW.
    """
    facility = {
        "name": "Bellhaven of Marietta",
        "address": "805 Colegate Dr",
        "city": "Marietta",
        "state": "OH",
        "zip": "45750",
    }

    current_account = {
        "account_id": "current-bellhaven",
        "name": "Bellhaven of Marietta",
        "parent_id": BELLHAVEN_PARENT_ID,
        "parent_name": "Bellhaven Senior Living",
        "billing_street": "805 Colegate Dr",
        "billing_city": "Marietta",
        "billing_state": "OH",
        "billing_zip": "45750",
        "care_type": "",
        "status": "Active",
        "phone": "",
        "lifetime_revenue": 0,
        "outstanding_ar": 0,
        "chow_current_account": "",
        "duplicate_of_account": "",
        "note": "",
    }

    historical_account = {
        "account_id": "historical-cedar-trail",
        "name": "Bellhaven of Marietta",
        "parent_id": "cedar-trail-parent",
        "parent_name": "Cedar Trail Communities",
        "billing_street": "805 Colegate Drive",
        "billing_city": "Marietta",
        "billing_state": "OH",
        "billing_zip": "45750",
        "care_type": "Skilled Nursing",
        "status": "Active",
        "phone": "(419) 353-5019",
        "lifetime_revenue": 51250,
        "outstanding_ar": 3800,
        "chow_current_account": "current-bellhaven",
        "duplicate_of_account": "",
        "note": "",
    }

    result = reconcile_facility(
        facility,
        [
            current_account,
            historical_account,
        ],
    )

    proposal_types = [
        proposal["type"]
        for proposal in result["proposals"]
    ]

    assert "SAME_LOCATION_REVIEW" not in proposal_types
    assert "CHOW_CREATE" not in proposal_types
    assert proposal_types == ["NO_CHANGE"]