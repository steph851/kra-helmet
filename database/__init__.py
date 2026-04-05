"""
DATABASE — PostgreSQL layer for KRA Deadline Tracker.
Import specific modules directly when needed:
  from database.connection import db_available
"""
# Lazy imports - don't eager load models at import time
__all__ = ["db_available", "get_session", "init_database", "get_engine"]