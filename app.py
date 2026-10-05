import json
from pathlib import Path

import streamlit as st

from decision_store import (
    get_decision,
    proposal_fingerprint,
    record_decision,
)
from executor import execute_proposal


DATA_DIR = Path("data")
PROPOSALS_FILE = DATA_DIR / "proposals.json"

NON_EXECUTABLE_TYPES = {
    "SAME_LOCATION_REVIEW",
    "STALE_BELLHAVEN_ACCOUNT",
}


st.set_page_config(
    page_title="Bellhaven CRM Review",
    page_icon="🏥",
    layout="wide",
)


def load_proposals():
    if not PROPOSALS_FILE.exists():
        return []

    with PROPOSALS_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    proposals = []

    for result in payload.get(
        "facility_results",
        [],
    ):
        for proposal in result.get(
            "proposals",
            [],
        ):
            if proposal.get("type") != "NO_CHANGE":
                proposals.append(proposal)

    proposals.extend(
        payload.get(
            "stale_bellhaven_accounts",
            [],
        )
    )

    return proposals


def format_address(record, website=False):
    if not record:
        return "N/A"

    if website:
        parts = [
            record.get("address"),
            record.get("city"),
            record.get("state"),
            record.get("zip"),
        ]
    else:
        parts = [
            record.get("billing_street"),
            record.get("billing_city"),
            record.get("billing_state"),
            record.get("billing_zip"),
        ]

    return ", ".join(
        str(part)
        for part in parts
        if part
    )


def format_care_offerings(website):
    offerings = website.get("care_offerings")

    if not offerings:
        return website.get(
            "care_type",
            "N/A",
        )

    if isinstance(offerings, list):
        return ", ".join(
            str(item)
            for item in offerings
        )

    return str(offerings)


def proposal_title(proposal):
    website = proposal.get("website") or {}
    target = proposal.get("target_account") or {}

    return (
        website.get("name")
        or target.get("name")
        or "Unnamed proposal"
    )


def render_changes(changes):
    if not changes:
        st.info(
            "No automatic mutation is proposed. "
            "This item requires human judgment."
        )
        return

    rows = []

    for field, value in changes.items():
        if isinstance(value, bool):
            display_value = (
                "Yes" if value else "No"
            )
        elif value is None:
            display_value = ""
        else:
            display_value = str(value)

        rows.append(
            {
                "Field": str(field),
                "Proposed value": display_value,
            }
        )

    st.table(rows)


def render_review_controls(proposal):
    fingerprint = proposal_fingerprint(
        proposal
    )

    existing = get_decision(proposal)

    if existing:
        decision = existing.get(
            "decision",
            "unknown",
        )

        status = existing.get(
            "execution_status"
        )

        if decision == "approved":
            st.success(
                "Approved and recorded. "
                f"Execution status: {status}"
            )
        else:
            st.info(
                "Rejected / no action. "
                "This exact unchanged proposal "
                "will not require review again."
            )

        return

    proposal_type = proposal.get("type")

    if proposal_type in NON_EXECUTABLE_TYPES:
        st.warning(
            "The automated system intentionally "
            "does not provide an Approve button "
            "for this ambiguous proposal. "
            "Available evidence does not justify "
            "an automatic CRM mutation."
        )

        if st.button(
            "Reject / No Action",
            key=f"reject-{fingerprint}",
            type="secondary",
        ):
            record_decision(
                proposal,
                "rejected",
                execution_status="no_action",
                message=(
                    "Human reviewer determined "
                    "that available evidence does "
                    "not justify a CRM mutation."
                ),
            )

            st.rerun()

        return

    st.warning(
        "Approval will execute this proposal "
        "against the live assessment CRM."
    )

    approve_col, reject_col = st.columns(2)

    with approve_col:
        if st.button(
            "Approve & Execute",
            key=f"approve-{fingerprint}",
            type="primary",
        ):
            try:
                result = execute_proposal(
                    proposal
                )

                record_decision(
                    proposal,
                    "approved",
                    execution_status="success",
                    message=(
                        "CRM mutation completed "
                        "successfully."
                    ),
                )

                st.success(
                    "CRM mutation completed."
                )

                st.json(result)

            except Exception as error:
                st.error(
                    "CRM mutation failed. "
                    "The proposal was NOT recorded "
                    "as approved."
                )

                st.exception(error)

    with reject_col:
        if st.button(
            "Reject / No Action",
            key=f"reject-{fingerprint}",
            type="secondary",
        ):
            record_decision(
                proposal,
                "rejected",
                execution_status="no_action",
                message=(
                    "Human reviewer rejected "
                    "the proposed mutation."
                ),
            )

            st.rerun()


proposals = load_proposals()

st.title("Bellhaven CRM Reconciliation")

st.caption(
    "Human-in-the-loop review of Bellhaven "
    "website-to-CRM remediation proposals. "
    "Nothing writes to the CRM without "
    "explicit approval."
)

if not proposals:
    st.warning(
        "No actionable proposals found. "
        "Run `python matcher.py` first."
    )
    st.stop()


decided_count = sum(
    1
    for proposal in proposals
    if get_decision(proposal)
)

pending_count = (
    len(proposals)
    - decided_count
)

high_confidence_count = sum(
    1
    for proposal in proposals
    if proposal.get("confidence") == "HIGH"
)

review_count = sum(
    1
    for proposal in proposals
    if proposal.get("type")
    in NON_EXECUTABLE_TYPES
)


col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Actionable proposals",
    len(proposals),
)

col2.metric(
    "Pending review",
    pending_count,
)

col3.metric(
    "High confidence",
    high_confidence_count,
)

col4.metric(
    "Needs judgment",
    review_count,
)


st.divider()


selected_filter = st.selectbox(
    "Filter proposals",
    [
        "All",
        "Pending only",
        "High confidence",
        "Needs judgment",
    ],
)


filtered = []

for proposal in proposals:
    decision = get_decision(proposal)

    if (
        selected_filter == "Pending only"
        and decision
    ):
        continue

    if (
        selected_filter == "High confidence"
        and proposal.get("confidence") != "HIGH"
    ):
        continue

    if (
        selected_filter == "Needs judgment"
        and proposal.get("type")
        not in NON_EXECUTABLE_TYPES
    ):
        continue

    filtered.append(proposal)


for index, proposal in enumerate(
    filtered,
    start=1,
):
    proposal_type = proposal.get(
        "type",
        "UNKNOWN",
    )

    confidence = proposal.get(
        "confidence",
        "UNKNOWN",
    )

    title = proposal_title(proposal)

    decision = get_decision(proposal)

    if decision:
        decision_label = (
            decision.get(
                "decision",
                "decided",
            ).upper()
        )
    else:
        decision_label = "PENDING"

    with st.expander(
        f"{index}. {title} | "
        f"{proposal_type} | "
        f"{confidence} | "
        f"{decision_label}",
        expanded=False,
    ):
        website = (
            proposal.get("website")
            or {}
        )

        target = (
            proposal.get("target_account")
            or {}
        )

        successor = (
            proposal.get("successor_account")
            or {}
        )

        survivor = (
            proposal.get("survivor_account")
            or {}
        )

        left, right = st.columns(2)

        with left:
            st.subheader("Website evidence")

            if website:
                st.write(
                    "**Name:**",
                    website.get(
                        "name",
                        "N/A",
                    ),
                )

                st.write(
                    "**Address:**",
                    format_address(
                        website,
                        website=True,
                    ),
                )

                st.write(
                    "**Care offerings:**",
                    format_care_offerings(
                        website
                    ),
                )

                if website.get("url"):
                    st.write(
                        "**Source:**",
                        website.get("url"),
                    )
            else:
                st.write(
                    "No current Bellhaven "
                    "website facility matched."
                )

        with right:
            st.subheader("Current CRM record")

            if target:
                st.write(
                    "**Name:**",
                    target.get(
                        "name",
                        "N/A",
                    ),
                )

                st.write(
                    "**Account ID:**",
                    target.get(
                        "account_id",
                        "N/A",
                    ),
                )

                st.write(
                    "**Parent:**",
                    target.get(
                        "parent_name",
                        "None",
                    )
                    or "None",
                )

                st.write(
                    "**Address:**",
                    format_address(target),
                )

                st.write(
                    "**Status:**",
                    target.get(
                        "status",
                        "N/A",
                    ),
                )

                st.write(
                    "**Lifetime revenue:**",
                    f"${target.get('lifetime_revenue', 0):,.0f}",
                )

                st.write(
                    "**Outstanding AR:**",
                    f"${target.get('outstanding_ar', 0):,.0f}",
                )
            else:
                st.write(
                    "No corresponding CRM "
                    "account currently exists."
                )

        st.subheader("Why this was proposed")

        st.write(
            proposal.get(
                "reason",
                "No reason provided.",
            )
        )

        if survivor:
            st.subheader(
                "Proposed surviving account"
            )

            st.write(
                f"{survivor.get('name')} "
                f"({survivor.get('account_id')})"
            )

        if successor:
            st.subheader(
                "CHOW successor"
            )

            st.write(
                f"{successor.get('name')} "
                f"({successor.get('account_id')})"
            )

            st.write(
                "The historical account will "
                "remain intact except for its "
                "`chow_current_account` link."
            )

        st.subheader("Proposed changes")

        render_changes(
            proposal.get(
                "changes",
                {},
            )
        )

        st.caption(
            "Proposal fingerprint: "
            + proposal_fingerprint(
                proposal
            )[:12]
        )

        st.divider()

        render_review_controls(proposal)