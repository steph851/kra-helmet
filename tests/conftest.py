"""
Shared fixtures for all tests.
Sets up temp directories so tests don't touch production data.
"""
import json
import os
import sys
from pathlib import Path
import pytest

# Ensure project root is importable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Set dummy API key so base agent doesn't crash (but won't call Claude)
os.environ.setdefault("ANTHROPIC_API_KEY", "")


@pytest.fixture
def sample_profile():
    """A valid SME profile for testing."""
    return {
        "pin": "A123456789B",
        "name": "Test Trader",
        "business_name": "Test Trader Ltd",
        "business_type": "sole_proprietor",
        "industry": "retail_wholesale",
        "county": "Nairobi",
        "annual_turnover_kes": 3500000,
        "turnover_bracket": "1m_to_8m",
        "has_employees": True,
        "employee_count": 2,
        "is_vat_registered": False,
        "has_etims": False,
        "phone": "0712345678",
        "email": "test@example.com",
        "preferred_language": "en",
        "preferred_channel": "whatsapp",
        "rental_income_annual_kes": None,
        "classification": {
            "industry": "retail_wholesale",
            "industry_label": "Retail / Wholesale Shop",
            "turnover_bracket": "1m_to_8m",
            "obligations": ["turnover_tax", "paye", "nssf", "shif", "housing_levy"],
            "wht_triggers": ["rent_commercial"],
            "etims_required": False,
            "notes": None,
        },
    }


@pytest.fixture
def sample_obligations():
    """Obligations after deadline calculation."""
    return [
        {
            "tax_type": "turnover_tax",
            "tax_name": "Turnover Tax (TOT)",
            "frequency": "monthly",
            "deadline_day": 20,
            "rate": "3.0%",
            "status": "upcoming",
            "next_deadline": "2026-04-20",
            "days_until_deadline": 22,
            "confidence": 0.95,
            "auto_proceed": True,
        },
        {
            "tax_type": "paye",
            "tax_name": "Pay As You Earn (PAYE)",
            "frequency": "monthly",
            "deadline_day": 9,
            "rate": "progressive (10%-35%)",
            "status": "upcoming",
            "next_deadline": "2026-04-09",
            "days_until_deadline": 11,
            "confidence": 0.95,
            "auto_proceed": True,
        },
    ]


@pytest.fixture
def overdue_obligations():
    """Obligations that are overdue — for penalty testing."""
    return [
        {
            "tax_type": "turnover_tax",
            "tax_name": "Turnover Tax (TOT)",
            "frequency": "monthly",
            "deadline_day": 20,
            "rate": "3.0%",
            "status": "overdue",
            "next_deadline": "2026-02-20",
            "days_until_deadline": -37,
            "estimated_amount_kes": 105000,
            "confidence": 0.95,
        },
        {
            "tax_type": "paye",
            "tax_name": "Pay As You Earn (PAYE)",
            "frequency": "monthly",
            "deadline_day": 9,
            "rate": "progressive (10%-35%)",
            "status": "overdue",
            "next_deadline": "2026-02-09",
            "days_until_deadline": -48,
            "estimated_amount_kes": 25000,
            "confidence": 0.95,
        },
    ]
