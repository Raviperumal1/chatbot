from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass

from email_validator import (
    EmailNotValidError,
    EmailSyntaxError,
    EmailUndeliverableError,
    validate_email,
)

logger = logging.getLogger(__name__)

# Providers common enough in your lead pool that a near-miss is almost
# certainly a typo, not an intentional less-common domain.
COMMON_EMAIL_DOMAINS = [
    "gmail.com",
    "yahoo.com",
    "yahoo.co.in",
    "hotmail.com",
    "hotmail.co.in",
    "outlook.com",
    "live.com",
    "icloud.com",
    "rediffmail.com",
    "protonmail.com",
    "zoho.com",
    "aol.com",
]


@dataclass
class EmailValidationResult:
    is_valid: bool
    normalized_email: str | None = None
    error: str | None = None
    suggestion: str | None = None  # e.g. "gmail.com" when they typed "gmial.com"


def suggest_domain_fix(domain: str) -> str | None:
    """Close-but-not-exact match against common providers.
    Returns None for an exact match or nothing close enough (cutoff=0.8
    keeps this from firing on legitimately different, uncommon domains)."""
    domain = domain.lower().strip()
    if domain in COMMON_EMAIL_DOMAINS:
        return None
    matches = difflib.get_close_matches(domain, COMMON_EMAIL_DOMAINS, n=1, cutoff=0.8)
    return matches[0] if matches else None


def validate_email_address(raw_email: str, check_deliverability: bool = True) -> EmailValidationResult:
    """
    Validates a *complete* email string (not free text - extract the
    candidate substring first if the user might type a full sentence).

    check_deliverability=True does a live MX/DNS lookup. Set it to False
    for offline unit tests, or if you want syntax-only validation on a
    latency-sensitive path.
    """
    email = raw_email.strip()

    try:
        result = validate_email(email, check_deliverability=check_deliverability)
    except EmailUndeliverableError as e:
        # Syntax is fine, but the domain has no mail servers (no MX, and
        # no fallback A/AAAA either) - almost always a typo or a domain
        # that simply doesn't exist.
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        logger.info("Email failed deliverability check: %s (%s)", email, e)
        return EmailValidationResult(is_valid=False, error=str(e), suggestion=suggest_domain_fix(domain))
    except EmailSyntaxError as e:
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        return EmailValidationResult(is_valid=False, error=str(e), suggestion=suggest_domain_fix(domain))
    except EmailNotValidError as e:
        # Catch-all for anything else the library flags.
        return EmailValidationResult(is_valid=False, error=str(e))

    return EmailValidationResult(is_valid=True, normalized_email=result.normalized)