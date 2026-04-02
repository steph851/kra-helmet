"""
KRA INTEGRATION — iTax, eTIMS, and Kenya Gazette connectors.
BOUNDARY: Fetches public data and provides filing guidance. Never submits filings directly.
All KRA interactions are read-only or guidance-based — actual filing happens on iTax.
"""
from .itax import ITaxConnector
from .etims import ETIMSConnector
from .gazette import GazetteConnector

__all__ = ["ITaxConnector", "ETIMSConnector", "GazetteConnector"]
