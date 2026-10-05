from crm_client import (
    create_account,
    update_account,
)
from matcher import BELLHAVEN_PARENT_ID


DIRECT_UPDATE_TYPES = {
    "UPDATE_NAME",
    "UPDATE_ZIP",
    "REPARENT",
    "LINK_CHOW_SUCCESSOR",
}


def build_new_account_payload(facility):
    """
    Build the minimum sensible CRM account payload from verified
    Bellhaven website evidence.
    """
    return {
        "name": facility.get("name"),
        "parent_id": BELLHAVEN_PARENT_ID,
        "status": "Active",
        "billing_street": facility.get("address"),
        "billing_city": facility.get("city"),
        "billing_state": facility.get("state"),
        "billing_zip": facility.get("zip"),
    }


def execute_direct_update(proposal):
    target = proposal.get("target_account") or {}
    account_id = target.get("account_id")

    if not account_id:
        raise ValueError(
            "Direct update proposal has no target account."
        )

    changes = proposal.get("changes") or {}

    if not changes:
        raise ValueError(
            "Direct update proposal has no changes."
        )

    return update_account(
        account_id,
        changes,
    )


def execute_create_account(proposal):
    facility = proposal.get("website") or {}

    if not facility:
        raise ValueError(
            "CREATE_ACCOUNT proposal has no website evidence."
        )

    payload = build_new_account_payload(
        facility
    )

    return create_account(payload)


def execute_mark_duplicate(proposal):
    target = proposal.get("target_account") or {}
    survivor = proposal.get("survivor_account") or {}

    target_id = target.get("account_id")
    survivor_id = survivor.get("account_id")

    if not target_id or not survivor_id:
        raise ValueError(
            "Duplicate proposal is missing an account ID."
        )

    return update_account(
        target_id,
        {
            "duplicate_of_account": survivor_id,
            "status": "Inactive",
        },
    )


def execute_chow_create(proposal):
    """
    Execute the CHOW safeguard:

    1. Create the new Bellhaven current account.
    2. Link the historical account to that new account.

    The historical account's parent, status, name, address, and
    financial history remain untouched.
    """
    facility = proposal.get("website") or {}
    historical = proposal.get("target_account") or {}

    historical_id = historical.get("account_id")

    if not facility or not historical_id:
        raise ValueError(
            "CHOW proposal is missing required evidence."
        )

    new_account_payload = (
        build_new_account_payload(facility)
    )

    new_account = create_account(
        new_account_payload
    )

    new_account_id = (
        new_account.get("account_id")
        if isinstance(new_account, dict)
        else None
    )

    if not new_account_id:
        raise RuntimeError(
            "CRM created the CHOW account but did not "
            "return an account_id. Historical account "
            "was NOT modified."
        )

    try:
        updated_historical = update_account(
            historical_id,
            {
                "chow_current_account":
                    new_account_id,
            },
        )
    except Exception as error:
        raise RuntimeError(
            "New CHOW account was created successfully "
            f"as {new_account_id}, but linking the "
            "historical account failed. Manual recovery "
            "is required before retrying."
        ) from error

    return {
        "new_account": new_account,
        "historical_account":
            updated_historical,
    }


def execute_proposal(proposal):
    """
    Route an approved proposal to the only mutation procedure
    permitted for its proposal type.
    """
    proposal_type = proposal.get("type")

    if proposal_type in DIRECT_UPDATE_TYPES:
        return execute_direct_update(
            proposal
        )

    if proposal_type == "CREATE_ACCOUNT":
        return execute_create_account(
            proposal
        )

    if proposal_type == "MARK_DUPLICATE":
        return execute_mark_duplicate(
            proposal
        )

    if proposal_type == "CHOW_CREATE":
        return execute_chow_create(
            proposal
        )

    if proposal_type in {
        "SAME_LOCATION_REVIEW",
        "STALE_BELLHAVEN_ACCOUNT",
    }:
        raise ValueError(
            f"{proposal_type} has no automatic mutation. "
            "It must be rejected/no-action or resolved "
            "into a concrete proposal."
        )

    if proposal_type == "NO_CHANGE":
        raise ValueError(
            "NO_CHANGE proposals are not executable."
        )

    raise ValueError(
        f"Unsupported proposal type: {proposal_type}"
    )