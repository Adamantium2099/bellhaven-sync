import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path("data")
DECISIONS_FILE = DATA_DIR / "decisions.json"


def _canonical_proposal(proposal):
    """
    Return the stable parts of a proposal that define the decision.

    If the target, proposed changes, website evidence, or successor changes,
    the fingerprint changes and the proposal can legitimately be reviewed
    again.
    """
    target = proposal.get("target_account") or {}
    successor = proposal.get("successor_account") or {}
    survivor = proposal.get("survivor_account") or {}
    website = proposal.get("website") or {}

    return {
        "type": proposal.get("type"),
        "target_account_id": target.get("account_id"),
        "successor_account_id": successor.get("account_id"),
        "survivor_account_id": survivor.get("account_id"),
        "website": {
            "name": website.get("name"),
            "address": website.get("address"),
            "city": website.get("city"),
            "state": website.get("state"),
            "zip": website.get("zip"),
        },
        "changes": proposal.get("changes", {}),
    }


def proposal_fingerprint(proposal):
    """Create a deterministic SHA-256 identifier for a proposal."""
    canonical = _canonical_proposal(proposal)

    serialized = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def load_decisions():
    """Load prior local review decisions."""
    if not DECISIONS_FILE.exists():
        return {}

    with DECISIONS_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_decisions(decisions):
    """Persist review decisions locally."""
    DATA_DIR.mkdir(exist_ok=True)

    with DECISIONS_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            decisions,
            file,
            indent=2,
            ensure_ascii=False,
        )


def get_decision(proposal):
    """Return the previous decision for this exact proposal, if any."""
    decisions = load_decisions()
    fingerprint = proposal_fingerprint(proposal)
    return decisions.get(fingerprint)


def record_decision(
    proposal,
    decision,
    execution_status=None,
    message=None,
):
    """
    Record an approval/rejection and optional execution result.
    """
    if decision not in {
        "approved",
        "rejected",
    }:
        raise ValueError(
            "Decision must be 'approved' or 'rejected'."
        )

    decisions = load_decisions()
    fingerprint = proposal_fingerprint(proposal)

    decisions[fingerprint] = {
        "decision": decision,
        "decided_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "proposal_type": proposal.get("type"),
        "target_account_id": (
            (proposal.get("target_account") or {})
            .get("account_id")
        ),
        "execution_status": execution_status,
        "message": message,
    }

    save_decisions(decisions)

    return fingerprint


def proposal_was_decided(proposal):
    """Check whether this exact proposal already has a decision."""
    return get_decision(proposal) is not None