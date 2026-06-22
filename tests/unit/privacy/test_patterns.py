"""Tests for privacy.patterns."""

from __future__ import annotations

import pytest

from mcp_atlassian.privacy.patterns import (
    BUILTIN_PATTERNS,
    CREDIT_CARD,
    EMAIL,
    IBAN,
    IPV4,
    PHONE,
)


class TestBuiltinPatterns:
    def test_registry_keys(self) -> None:
        assert set(BUILTIN_PATTERNS) == {
            "email",
            "phone",
            "ipv4",
            "iban",
            "credit_card",
        }

    @pytest.mark.parametrize(
        "text",
        [
            "alice@example.com",
            "first.last+tag@sub.example.co",
            "USER_99@example.io",
        ],
    )
    def test_email_matches(self, text: str) -> None:
        assert EMAIL.search(text) is not None

    @pytest.mark.parametrize(
        "text",
        ["not an email", "@nope.com", "missing@"],
    )
    def test_email_does_not_match(self, text: str) -> None:
        assert EMAIL.search(text) is None

    @pytest.mark.parametrize(
        "text",
        [
            "+1 (415) 555-2671",
            "+49 30 1234 5678",
            "415-555-2671",
        ],
    )
    def test_phone_matches(self, text: str) -> None:
        assert PHONE.search(text) is not None

    def test_phone_skips_short_numbers(self) -> None:
        assert PHONE.search("v1.2.3") is None

    @pytest.mark.parametrize("text", ["10.0.0.1", "192.168.1.1", "255.255.255.255"])
    def test_ipv4_matches(self, text: str) -> None:
        assert IPV4.search(text) is not None

    @pytest.mark.parametrize(
        "text", ["256.0.0.1", "999.999.999.999", "no.numbers.here.x"]
    )
    def test_ipv4_does_not_match(self, text: str) -> None:
        assert IPV4.search(text) is None

    def test_iban_matches(self) -> None:
        assert IBAN.search("DE89370400440532013000") is not None

    def test_iban_does_not_match(self) -> None:
        assert IBAN.search("12345678") is None

    @pytest.mark.parametrize(
        "text", ["4242 4242 4242 4242", "4242-4242-4242-4242", "4242424242424242"]
    )
    def test_credit_card_matches(self, text: str) -> None:
        assert CREDIT_CARD.search(text) is not None

    def test_credit_card_skips_too_short(self) -> None:
        # 12 digits is below the 13-19 range.
        assert CREDIT_CARD.search("12345678 9012") is None
