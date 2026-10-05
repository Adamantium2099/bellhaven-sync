import json
from pathlib import Path

import requests

from config import API_BASE_URL, HEADERS


DATA_DIR = Path("data")
CRM_SNAPSHOT = DATA_DIR / "crm_accounts.json"

MUTABLE_ACCOUNT_FIELDS = {
    "name",
    "parent_id",
    "status",
    "note",
    "care_type",
    "phone",
    "billing_street",
    "billing_city",
    "billing_state",
    "billing_zip",
    "chow_current_account",
    "duplicate_of_account",
}


def _request(method, path, **kwargs):
    """
    Make an authenticated CRM API request and raise a useful error
    if the API rejects it.
    """
    response = requests.request(
        method,
        f"{API_BASE_URL}{path}",
        headers=HEADERS,
        timeout=30,
        **kwargs,
    )

    if not response.ok:
        raise RuntimeError(
            f"CRM API {method} {path} failed "
            f"with HTTP {response.status_code}: "
            f"{response.text}"
        )

    if not response.content:
        return None

    return response.json()


def get_account(account_id):
    """Retrieve one CRM account."""
    return _request(
        "GET",
        f"/accounts/{account_id}",
    )


def list_accounts(page_size=100):
    """Retrieve every CRM account using API pagination."""
    accounts = []
    page = 1

    while True:
        payload = _request(
            "GET",
            "/accounts",
            params={
                "page": page,
                "page_size": page_size,
            },
        )

        rows = payload.get("data", [])
        accounts.extend(rows)

        total = payload.get("total", len(accounts))

        if len(accounts) >= total or not rows:
            break

        page += 1

    return accounts


def save_accounts_snapshot(accounts):
    """Save a local read-only snapshot for reconciliation."""
    DATA_DIR.mkdir(exist_ok=True)

    with CRM_SNAPSHOT.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            accounts,
            file,
            indent=2,
            ensure_ascii=False,
        )


def refresh_accounts_snapshot():
    """Pull the current CRM state and save it locally."""
    accounts = list_accounts()
    save_accounts_snapshot(accounts)
    return accounts


def update_account(account_id, changes):
    """
    Apply a narrow partial update to an existing CRM account.

    Only fields explicitly documented by the API as mutable are allowed.
    """
    if not changes:
        raise ValueError(
            "Refusing to PATCH an account with no changes."
        )

    unsupported = (
        set(changes)
        - MUTABLE_ACCOUNT_FIELDS
    )

    if unsupported:
        raise ValueError(
            "Unsupported CRM account fields: "
            + ", ".join(sorted(unsupported))
        )

    return _request(
        "PATCH",
        f"/accounts/{account_id}",
        json=changes,
    )


def create_account(account_data):
    """
    Create a CRM account.

    This method exists for approved proposals only. The review/execution
    layer is responsible for supplying a legitimate account payload.
    """
    if not account_data:
        raise ValueError(
            "Refusing to create an empty CRM account."
        )

    unsupported = (
        set(account_data)
        - MUTABLE_ACCOUNT_FIELDS
    )

    if unsupported:
        raise ValueError(
            "Unsupported CRM account fields: "
            + ", ".join(sorted(unsupported))
        )

    return _request(
        "POST",
        "/accounts",
        json=account_data,
    )


def main():
    accounts = refresh_accounts_snapshot()

    print(
        f"CRM accounts downloaded: {len(accounts)}"
    )
    print(
        f"Snapshot saved to: {CRM_SNAPSHOT}"
    )


if __name__ == "__main__":
    main()