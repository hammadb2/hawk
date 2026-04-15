"""Map HAWK account state → hawk-scanner-v2 trust_level for scoring."""
from __future__ import annotations

from sqlalchemy.orm import Session

from models import Domain, User


def _paid_like(user: User) -> bool:
    if user.plan in ("starter", "pro", "agency"):
        return True
    return bool(getattr(user, "stripe_subscription_id", None) or "")


def scanner_trust_level(
    db: Session,
    user: User | None,
    domain: str,
    *,
    remediation_acknowledged: bool,
) -> str:
    """
    public — strict floor (marketing, prospects, unauthenticated).
    subscriber — paid + domain on account; softer floor (still hard to get an A on a clean pass).
    certified — same as subscriber plus remediation attestation (honor-system checkbox on rescan).
    """
    if user is None:
        return "public"
    d = (domain or "").strip().lower()
    if not d or not _paid_like(user):
        return "public"
    owned = (
        db.query(Domain)
        .filter(Domain.user_id == user.id, Domain.domain.ilike(d))
        .first()
    )
    if not owned:
        return "public"
    if remediation_acknowledged:
        return "certified"
    return "subscriber"
