"""Tests for input validation — the first line of defense."""
import pytest
from agents.validation.input_validator import InputValidator


@pytest.fixture
def v():
    return InputValidator()


# ── PIN validation ──────────────────────────────────────────────

class TestPinValidation:
    def test_valid_pin(self, v):
        ok, result = v.validate_pin("A123456789B")
        assert ok
        assert result == "A123456789B"

    def test_valid_pin_lowercase_normalized(self, v):
        ok, result = v.validate_pin("a123456789b")
        assert ok
        assert result == "A123456789B"

    def test_valid_pin_with_spaces(self, v):
        ok, result = v.validate_pin("  A123456789B  ")
        assert ok
        assert result == "A123456789B"

    def test_empty_pin(self, v):
        ok, msg = v.validate_pin("")
        assert not ok

    def test_short_pin(self, v):
        ok, msg = v.validate_pin("A1234")
        assert not ok

    def test_invalid_format_no_letters(self, v):
        ok, msg = v.validate_pin("12345678901")
        assert not ok

    def test_invalid_format_too_many_digits(self, v):
        ok, msg = v.validate_pin("A1234567890B")
        assert not ok


# ── Phone validation ────────────────────────────────────────────

class TestPhoneValidation:
    def test_valid_07_phone(self, v):
        ok, result = v.validate_phone("0712345678")
        assert ok

    def test_valid_01_phone(self, v):
        ok, result = v.validate_phone("0112345678")
        assert ok

    def test_valid_plus254(self, v):
        ok, result = v.validate_phone("+254712345678")
        assert ok

    def test_empty_phone_ok(self, v):
        ok, _ = v.validate_phone("")
        assert ok  # phone is optional

    def test_invalid_phone(self, v):
        ok, msg = v.validate_phone("123")
        assert not ok

    def test_phone_with_dashes_cleaned(self, v):
        ok, result = v.validate_phone("0712-345-678")
        assert ok


# ── Email validation ────────────────────────────────────────────

class TestEmailValidation:
    def test_valid_email(self, v):
        ok, _ = v.validate_email("test@example.com")
        assert ok

    def test_none_email_ok(self, v):
        ok, _ = v.validate_email(None)
        assert ok

    def test_empty_email_ok(self, v):
        ok, _ = v.validate_email("")
        assert ok

    def test_invalid_email(self, v):
        ok, msg = v.validate_email("not-an-email")
        assert not ok

    def test_email_without_domain(self, v):
        ok, msg = v.validate_email("user@")
        assert not ok


# ── Period validation ───────────────────────────────────────────

class TestPeriodValidation:
    def test_valid_period(self, v):
        ok, _ = v.validate_period("2026-03")
        assert ok

    def test_valid_december(self, v):
        ok, _ = v.validate_period("2026-12")
        assert ok

    def test_invalid_month_13(self, v):
        ok, _ = v.validate_period("2026-13")
        assert not ok

    def test_invalid_month_00(self, v):
        ok, _ = v.validate_period("2026-00")
        assert not ok

    def test_invalid_format(self, v):
        ok, _ = v.validate_period("March 2026")
        assert not ok

    def test_empty_period(self, v):
        ok, _ = v.validate_period("")
        assert not ok

    def test_year_out_of_range(self, v):
        ok, _ = v.validate_period("1999-01")
        assert not ok


# ── Amount validation ───────────────────────────────────────────

class TestAmountValidation:
    def test_valid_amount(self, v):
        ok, val = v.validate_amount(105000)
        assert ok
        assert val == 105000.0

    def test_zero_amount(self, v):
        ok, val = v.validate_amount(0)
        assert ok

    def test_string_amount(self, v):
        ok, val = v.validate_amount("50000")
        assert ok
        assert val == 50000.0

    def test_negative_amount(self, v):
        ok, msg = v.validate_amount(-100)
        assert not ok

    def test_absurd_amount(self, v):
        ok, msg = v.validate_amount(99_999_999_999)
        assert not ok

    def test_non_numeric(self, v):
        ok, msg = v.validate_amount("abc")
        assert not ok


# ── Full profile validation ─────────────────────────────────────

class TestProfileValidation:
    def test_valid_profile(self, v, sample_profile):
        ok, errors = v.validate_profile(sample_profile)
        assert ok
        assert errors == []

    def test_missing_pin(self, v, sample_profile):
        sample_profile["pin"] = ""
        ok, errors = v.validate_profile(sample_profile)
        assert not ok
        assert any("PIN" in e for e in errors)

    def test_missing_name(self, v, sample_profile):
        sample_profile["name"] = ""
        ok, errors = v.validate_profile(sample_profile)
        assert not ok

    def test_invalid_industry(self, v, sample_profile):
        sample_profile["industry"] = "gambling"
        ok, errors = v.validate_profile(sample_profile)
        assert not ok
        assert any("industry" in e.lower() for e in errors)

    def test_invalid_bracket(self, v, sample_profile):
        sample_profile["turnover_bracket"] = "billions"
        ok, errors = v.validate_profile(sample_profile)
        assert not ok

    def test_invalid_business_type(self, v, sample_profile):
        sample_profile["business_type"] = "ngo"
        ok, errors = v.validate_profile(sample_profile)
        assert not ok

    def test_multiple_errors(self, v):
        ok, errors = v.validate_profile({
            "pin": "bad",
            "name": "",
            "industry": "invalid",
            "business_type": "invalid",
        })
        assert not ok
        assert len(errors) >= 3


# ── Filing validation ───────────────────────────────────────────

class TestFilingValidation:
    def test_valid_filing(self, v):
        ok, errors = v.validate_filing("A123456789B", "turnover_tax", "2026-03", 105000)
        assert ok

    def test_invalid_pin(self, v):
        ok, errors = v.validate_filing("bad", "turnover_tax", "2026-03")
        assert not ok

    def test_empty_tax_type(self, v):
        ok, errors = v.validate_filing("A123456789B", "", "2026-03")
        assert not ok

    def test_invalid_period(self, v):
        ok, errors = v.validate_filing("A123456789B", "turnover_tax", "bad")
        assert not ok

    def test_negative_amount(self, v):
        ok, errors = v.validate_filing("A123456789B", "turnover_tax", "2026-03", -100)
        assert not ok
