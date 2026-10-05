import json
import re
from pathlib import Path

from rapidfuzz.fuzz import ratio


DATA_DIR = Path("data")
WEBSITE_SNAPSHOT = DATA_DIR / "website_facilities.json"
CRM_SNAPSHOT = DATA_DIR / "crm_accounts.json"
PROPOSALS_FILE = DATA_DIR / "proposals.json"

BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"
BELLHAVEN_PARENT_NAME = "Bellhaven Senior Living (Parent Account)"


ADDRESS_REPLACEMENTS = {
    "avenue": "ave",
    "boulevard": "blvd",
    "drive": "dr",
    "lane": "ln",
    "road": "rd",
    "street": "st",
    "highway": "hwy",
    "parkway": "pkwy",
    "northwest": "nw",
    "northeast": "ne",
    "southwest": "sw",
    "southeast": "se",
    "north": "n",
    "south": "s",
    "east": "e",
    "west": "w",
}


def normalize_text(value):
    """Normalize general text for comparison."""
    value = str(value or "").lower().strip()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_address(value):
    """Normalize common address abbreviations."""
    value = normalize_text(value)

    return " ".join(
        ADDRESS_REPLACEMENTS.get(word, word)
        for word in value.split()
    )


def normalize_zip(value):
    """Use the five-digit ZIP for comparison."""
    return str(value or "").strip()[:5]


def website_location(facility):
    """Normalize website street + city as one comparable location."""
    return normalize_address(
        f"{facility.get('address', '')} "
        f"{facility.get('city', '')}"
    )


def crm_location(account):
    """Normalize CRM street + city as one comparable location."""
    return normalize_address(
        f"{account.get('billing_street', '')} "
        f"{account.get('billing_city', '')}"
    )


def candidate_evidence(facility, account):
    """Calculate auditable identity evidence for one CRM candidate."""
    name_score = ratio(
        normalize_text(facility.get("name")),
        normalize_text(account.get("name")),
    )

    address_score = ratio(
        website_location(facility),
        crm_location(account),
    )

    state_match = (
        normalize_text(facility.get("state"))
        == normalize_text(account.get("billing_state"))
    )

    zip_match = (
        normalize_zip(facility.get("zip"))
        == normalize_zip(account.get("billing_zip"))
    )

    exact_location = (
        address_score >= 95
        and state_match
        and zip_match
    )

    weighted_score = (
        name_score * 0.30
        + address_score * 0.40
        + (100 if state_match else 0) * 0.10
        + (100 if zip_match else 0) * 0.20
    )

    return {
        "account_id": account.get("account_id"),
        "name": account.get("name"),
        "parent_id": account.get("parent_id"),
        "parent_name": account.get("parent_name"),
        "billing_street": account.get("billing_street"),
        "billing_city": account.get("billing_city"),
        "billing_state": account.get("billing_state"),
        "billing_zip": account.get("billing_zip"),
        "care_type": account.get("care_type"),
        "status": account.get("status"),
        "phone": account.get("phone"),
        "lifetime_revenue": account.get("lifetime_revenue", 0),
        "outstanding_ar": account.get("outstanding_ar", 0),
        "duplicate_of_account": account.get(
            "duplicate_of_account", ""
        ),
        "chow_current_account": account.get(
            "chow_current_account", ""
        ),
        "note": account.get("note", ""),
        "name_score": round(name_score, 1),
        "address_score": round(address_score, 1),
        "state_match": state_match,
        "zip_match": zip_match,
        "exact_location": exact_location,
        "weighted_score": round(weighted_score, 1),
    }


def find_candidates(facility, accounts):
    """Rank all CRM records for one website facility."""
    candidates = [
        candidate_evidence(facility, account)
        for account in accounts
    ]

    candidates.sort(
        key=lambda item: item["weighted_score"],
        reverse=True,
    )

    return candidates


def find_same_location_candidates(facility, candidates):
    """
    Identify CRM records that plausibly represent the same physical facility.

    We accept three evidence paths:

    1. Exact normalized street/city + state + ZIP.
    2. Exact street/city + state with a highly similar name, allowing a bad ZIP.
    3. Exact ZIP/state + highly similar name, allowing a stale or PO Box address.

    Name alone is never sufficient.
    """
    matches = []

    for candidate in candidates:
        exact_location = candidate["exact_location"]

        address_with_bad_zip = (
            candidate["address_score"] >= 95
            and candidate["state_match"]
            and candidate["name_score"] >= 90
        )

        name_zip_with_bad_address = (
            candidate["zip_match"]
            and candidate["state_match"]
            and candidate["name_score"] >= 90
        )

        if (
            exact_location
            or address_with_bad_zip
            or name_zip_with_bad_address
        ):
            matches.append(candidate)

    return matches


def choose_survivor(candidates):
    """
    Select the best survivor when duplicate CRM records represent the same
    physical facility.

    Prefer:
    1. Bellhaven-owned record
    2. record with financial history
    3. record whose name most closely matches the website
    """
    return sorted(
        candidates,
        key=lambda item: (
            item["parent_id"] == BELLHAVEN_PARENT_ID,
            item["lifetime_revenue"] > 0,
            item["outstanding_ar"] > 0,
            item["name_score"],
        ),
        reverse=True,
    )[0]


def needs_name_update(facility, account):
    """Determine whether CRM name materially differs from website truth."""
    return (
        normalize_text(facility.get("name"))
        != normalize_text(account.get("name"))
    )


def needs_zip_update(facility, account):
    """Determine whether CRM ZIP differs from website truth."""
    return (
        normalize_zip(facility.get("zip"))
        != normalize_zip(account.get("billing_zip"))
    )


def chow_required(account):
    """
    Apply Clipboard's CHOW safeguard.

    Reparenting is prohibited when the existing account has both historical
    revenue and outstanding AR.
    """
    return (
        account.get("lifetime_revenue", 0) > 0
        and account.get("outstanding_ar", 0) > 0
    )


def make_create_proposal(facility, reason):
    """Propose creating a new Bellhaven CRM account."""
    return {
        "type": "CREATE_ACCOUNT",
        "confidence": "HIGH",
        "website": facility,
        "target_account": None,
        "changes": {
            "name": facility.get("name"),
            "parent_id": BELLHAVEN_PARENT_ID,
            "status": "Active",
        },
        "reason": reason,
    }


def reconcile_facility(facility, accounts):
    """Produce remediation proposals for one website facility."""
    candidates = find_candidates(facility, accounts)

    same_location = find_same_location_candidates(
        facility,
        candidates,
    )

    proposals = []

    # No convincing physical-location match.
    if not same_location:
        best = candidates[0]

        # Name alone is deliberately insufficient.
        proposals.append(
            make_create_proposal(
                facility,
                (
                    "No CRM account has sufficiently strong physical-location "
                    "evidence. The best candidate is not safe to match based "
                    "on name/geography alone."
                ),
            )
        )

        return {
            "website": facility,
            "identity_status": "NO_LOCATION_MATCH",
            "best_candidate": best,
            "same_location_accounts": [],
            "proposals": proposals,
        }

    survivor = choose_survivor(same_location)

    # Multiple records can mean either true duplicates or historical
    # ownership records at the same physical property.
    if len(same_location) > 1:
        losers = [
            account
            for account in same_location
            if account["account_id"] != survivor["account_id"]
        ]

        for loser in losers:
            
                        # A historical account that explicitly points to the selected
            # current account is an already-resolved CHOW relationship, not
            # an ambiguous same-location record.
            resolved_chow_pair = (
                loser.get("chow_current_account")
                == survivor["account_id"]
            )

            if resolved_chow_pair:
                continue
            same_parent = (
                loser["parent_id"] == survivor["parent_id"]
            )

            very_similar_name = (
                loser["name_score"] >= 90
            )

            no_financial_history = (
                loser["lifetime_revenue"] == 0
                and loser["outstanding_ar"] == 0
            )

            if (
                same_parent
                and very_similar_name
                and no_financial_history
            ):
                # Idempotency:
                # If this losing copy has already been marked inactive and
                # points to the selected survivor, the desired CRM state has
                # already been reached. Do not propose the same write again.
                already_resolved_duplicate = (
                    loser.get("status") == "Inactive"
                    and loser.get("duplicate_of_account")
                    == survivor["account_id"]
                )

                if not already_resolved_duplicate:
                    proposals.append(
                        {
                            "type": "MARK_DUPLICATE",
                            "confidence": "HIGH",
                            "website": facility,
                            "target_account": loser,
                            "survivor_account": survivor,
                            "changes": {
                                "duplicate_of_account": survivor["account_id"],
                                "status": "Inactive",
                            },
                            "reason": (
                                "A second CRM record represents the same "
                                "facility under the same parent, has a highly "
                                "similar name, and has no financial history. "
                                "Treat it as a duplicate copy."
                            ),
                        }
                    )

            else:
                proposals.append(
                    {
                        "type": "SAME_LOCATION_REVIEW",
                        "confidence": "MEDIUM",
                        "website": facility,
                        "target_account": loser,
                        "survivor_account": survivor,
                        "changes": {},
                        "reason": (
                            "Another CRM account exists at the same physical "
                            "location, but ownership, naming, or financial "
                            "evidence does not make it safe to classify as "
                            "a duplicate automatically."
                        ),
                    }
                )

    # Wrong parent.
    if survivor["parent_id"] != BELLHAVEN_PARENT_ID:
        if chow_required(survivor):
            proposals.append(
                {
                    "type": "CHOW_CREATE",
                    "confidence": "HIGH",
                    "website": facility,
                    "target_account": survivor,
                    "changes": {
                        "create_new_account": True,
                        "new_parent_id": BELLHAVEN_PARENT_ID,
                        "preserve_old_account": True,
                        "set_old_chow_current_account": True,
                    },
                    "reason": (
                        "The website identifies Bellhaven as the current "
                        "operator, but the CRM account belongs to another "
                        "parent and has both lifetime revenue and outstanding "
                        "AR. CHOW policy requires preserving the historical "
                        "account and creating a new current account."
                    ),
                }
            )

            # A CHOW creates a new Bellhaven account, so do not also rename
            # or reparent the historical account.
            return {
                "website": facility,
                "identity_status": "MATCHED",
                "best_candidate": candidates[0],
                "same_location_accounts": same_location,
                "proposals": proposals,
            }

        proposals.append(
            {
                "type": "REPARENT",
                "confidence": "HIGH",
                "website": facility,
                "target_account": survivor,
                "changes": {
                    "parent_id": BELLHAVEN_PARENT_ID,
                },
                "reason": (
                    "Strong physical-location evidence identifies this CRM "
                    "record as the website facility. It is assigned to the "
                    "wrong parent, and CHOW financial protection is not "
                    "triggered."
                ),
            }
        )

    # Stale facility name.
    if needs_name_update(facility, survivor):
        proposals.append(
            {
                "type": "UPDATE_NAME",
                "confidence": "HIGH",
                "website": facility,
                "target_account": survivor,
                "changes": {
                    "name": facility.get("name"),
                },
                "reason": (
                    "Physical-location evidence strongly identifies the CRM "
                    "record, but its facility name is stale or inconsistent "
                    "with Bellhaven's current website."
                ),
            }
        )

    # ZIP mismatch.
    if needs_zip_update(facility, survivor):
        proposals.append(
            {
                "type": "UPDATE_ZIP",
                "confidence": "HIGH",
                "website": facility,
                "target_account": survivor,
                "changes": {
                    "billing_zip": normalize_zip(
                        facility.get("zip")
                    ),
                },
                "reason": (
                    "The facility identity is strongly established by name "
                    "and street/city evidence, but the CRM ZIP differs from "
                    "the current website."
                ),
            }
        )

    if not proposals:
        proposals.append(
            {
                "type": "NO_CHANGE",
                "confidence": "HIGH",
                "website": facility,
                "target_account": survivor,
                "changes": {},
                "reason": (
                    "CRM identity, ownership, and key compared fields are "
                    "consistent with the current Bellhaven website."
                ),
            }
        )

    return {
        "website": facility,
        "identity_status": "MATCHED",
        "best_candidate": candidates[0],
        "same_location_accounts": same_location,
        "proposals": proposals,
    }


def find_stale_bellhaven_accounts(
    accounts,
    represented_account_ids,
):
    """
    Surface Bellhaven CRM accounts not represented by a current website
    facility.

    If an unmatched historical Bellhaven account has both lifetime revenue
    and outstanding AR, and exactly one active account under another parent
    exists at the same physical address, propose linking that account as the
    CHOW successor.

    Otherwise leave the account untouched and send it to human review.
    """
    proposals = []

    for account in accounts:
        if account.get("parent_id") != BELLHAVEN_PARENT_ID:
            continue

        if account.get("account_id") in represented_account_ids:
            continue

        successor_candidates = []

        for other in accounts:
            if other.get("account_id") == account.get("account_id"):
                continue

            if other.get("parent_id") in ("", BELLHAVEN_PARENT_ID):
                continue

            if other.get("status") != "Active":
                continue

            same_street = (
                normalize_address(other.get("billing_street", ""))
                == normalize_address(account.get("billing_street", ""))
            )

            same_city = (
                normalize_text(other.get("billing_city", ""))
                == normalize_text(account.get("billing_city", ""))
            )

            same_state = (
                normalize_text(other.get("billing_state", ""))
                == normalize_text(account.get("billing_state", ""))
            )

            same_zip = (
                normalize_zip(other.get("billing_zip", ""))
                == normalize_zip(account.get("billing_zip", ""))
            )

            if same_street and same_city and same_state and same_zip:
                successor_candidates.append(other)

        if chow_required(account) and len(successor_candidates) == 1:
            successor = successor_candidates[0]

            # Idempotency:
            # If the historical account already points to this exact
            # successor, the desired state has been reached. Preserve the
            # historical account and do not propose another write.
            already_linked = (
                account.get("chow_current_account")
                == successor["account_id"]
            )

            if already_linked:
                continue

            proposals.append(
                {
                    "type": "LINK_CHOW_SUCCESSOR",
                    "confidence": "HIGH",
                    "website": None,
                    "target_account": account,
                    "successor_account": successor,
                    "changes": {
                        "chow_current_account": successor["account_id"],
                    },
                    "reason": (
                        "This historical Bellhaven account is no longer on "
                        "Bellhaven's current website, has both lifetime "
                        "revenue and outstanding AR, and exactly one active "
                        "account under another parent exists at the same "
                        "physical location. Preserve the historical account "
                        "and link it to the current account."
                    ),
                }
            )

        else:
            proposals.append(
                {
                    "type": "STALE_BELLHAVEN_ACCOUNT",
                    "confidence": "MEDIUM",
                    "website": None,
                    "target_account": account,
                    "changes": {},
                    "reason": (
                        "This account remains under the Bellhaven parent but "
                        "is not represented by a current Bellhaven website "
                        "facility. Website absence alone is insufficient for "
                        "an automatic destructive change."
                    ),
                }
            )

    return proposals


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    DATA_DIR.mkdir(exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


def main():
    facilities = load_json(WEBSITE_SNAPSHOT)
    accounts = load_json(CRM_SNAPSHOT)

    results = [
        reconcile_facility(facility, accounts)
        for facility in facilities
    ]

    # Collect every CRM account that was physically represented by a
    # current Bellhaven website facility. This includes the selected
    # survivor as well as same-location records sent to duplicate or
    # ownership review.
    represented_account_ids = set()

    for result in results:
        for account in result.get(
            "same_location_accounts",
            [],
        ):
            account_id = account.get("account_id")

            if account_id:
                represented_account_ids.add(account_id)

    # Only Bellhaven accounts not represented above should enter the
    # reverse/stale-account analysis.
    stale_accounts = find_stale_bellhaven_accounts(
        accounts,
        represented_account_ids,
    )

    output = {
        "facility_results": results,
        "stale_bellhaven_accounts": stale_accounts,
    }

    save_json(PROPOSALS_FILE, output)

    proposal_counts = {}

    # Count ordinary website-to-CRM reconciliation proposals.
    for result in results:
        for proposal in result["proposals"]:
            proposal_type = proposal["type"]

            proposal_counts[proposal_type] = (
                proposal_counts.get(proposal_type, 0)
                + 1
            )

    # Count reverse-pass proposals by their real proposal type.
    for proposal in stale_accounts:
        proposal_type = proposal["type"]

        proposal_counts[proposal_type] = (
            proposal_counts.get(proposal_type, 0)
            + 1
        )

    print(
        f"Website facilities reconciled: "
        f"{len(results)}"
    )

    print(
        f"CRM accounts analyzed: "
        f"{len(accounts)}"
    )

    print(
        f"CRM accounts represented by current website: "
        f"{len(represented_account_ids)}"
    )

    print(
        f"Output saved to: "
        f"{PROPOSALS_FILE}"
    )

    print()

    print("PROPOSAL SUMMARY")
    print("-" * 60)

    for proposal_type, count in sorted(
        proposal_counts.items()
    ):
        print(
            f"{proposal_type:<30} "
            f"{count}"
        )

    print()
    print("ACTIONABLE PROPOSALS")
    print("-" * 60)

    for result in results:
        facility_name = result["website"]["name"]

        for proposal in result["proposals"]:
            if proposal["type"] == "NO_CHANGE":
                continue

            target = proposal.get("target_account")

            target_name = (
                target.get("name")
                if target
                else "NEW CRM ACCOUNT"
            )

            print(
                f"{proposal['type']:<20} | "
                f"{facility_name} | "
                f"{target_name}"
            )

    print()
    print("REVERSE / UNMATCHED BELLHAVEN PROPOSALS")
    print("-" * 60)

    for proposal in stale_accounts:
        account = proposal["target_account"]

        successor = proposal.get(
            "successor_account"
        )

        if successor:
            disposition = (
                f"Successor: {successor['name']}"
            )
        else:
            disposition = "Human review required"

        print(
            f"{proposal['type']:<20} | "
            f"{account['name']} | "
            f"{account['billing_street']}, "
            f"{account['billing_city']}, "
            f"{account['billing_state']} "
            f"{account['billing_zip']} | "
            f"Revenue ${account['lifetime_revenue']} | "
            f"AR ${account['outstanding_ar']} | "
            f"{disposition}"
        )


if __name__ == "__main__":
    main()