"""Built-in regex patterns for PII redaction.

Each pattern targets a single category of PII (email, phone, IPv4, ...).
Users opt in to specific patterns via the ``PRIVACY_PII_PATTERNS`` env var
and can supply additional regexes via ``PRIVACY_PII_CUSTOM_REGEX``.
"""

from __future__ import annotations

import re

EMAIL: re.Pattern[str] = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# E.164-ish + common separators. Conservative on length to avoid eating issue
# IDs / version numbers.
PHONE: re.Pattern[str] = re.compile(
    r"(?<![\w.])"
    r"\+?\d{1,3}[\s.\-]?"
    r"(?:\(\d{1,4}\)[\s.\-]?)?"
    r"\d{2,4}[\s.\-]?\d{2,4}[\s.\-]?\d{2,4}"
    r"(?![\w.])"
)

IPV4: re.Pattern[str] = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)

# IBAN: country (2 letters) + check digits (2) + BBAN (up to 30 alphanum).
IBAN: re.Pattern[str] = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")

# Credit card numbers (Visa/MC/Amex/Discover lengths). Allows spaces or dashes
# between groups of 4. Luhn validation is intentionally not performed; the
# false-positive cost (redacting a non-card 16-digit value) is acceptable.
CREDIT_CARD: re.Pattern[str] = re.compile(r"\b(?:\d[ \-]*?){13,19}\b")

BUILTIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": EMAIL,
    "phone": PHONE,
    "ipv4": IPV4,
    "iban": IBAN,
    "credit_card": CREDIT_CARD,
}
