"""
DATABASE CONNECTION — PostgreSQL connection management for KRA Deadline Tracker.
Supports Neon (free PostgreSQL) with SSL. Falls back gracefully when no DB/dependencies.
"""
import os

# Database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Module-level state (lazy-initialized)
_engine = None
_SessionLocal = None
_db_available = False


def _fix_neon_url(url: str) -> str:
    """Neon uses postgres:// but SQLAlchemy needs postgresql://."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # Ensure sslmode=require for Neon
    if "neon.tech" in url and "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url += f"{sep}sslmode=require"
    return url


def _init_engine():
    """Initialize the database engine (called once on first use)."""
    global _engine, _SessionLocal, _db_available

    if not DATABASE_URL:
        _db_available = False
        return

    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker, Session
        from sqlalchemy.pool import QueuePool
    except ImportError:
        _db_available = False
        return

    try:
        from .models import Base
        url = _fix_neon_url(DATABASE_URL)
        _engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=3,
            max_overflow=5,
            pool_timeout=30,
            pool_recycle=300,
            pool_pre_ping=True,
            echo=False,
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

        # Test connection
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        _db_available = True
        print(f"[DB] PostgreSQL connected")
    except Exception as e:
        print(f"[DB] PostgreSQL unavailable: {e}")
        _engine = None
        _SessionLocal = None
        _db_available = False


def db_available() -> bool:
    """Check if database is available."""
    if _engine is None and DATABASE_URL:
        _init_engine()
    return _db_available


def get_engine():
    """Get the SQLAlchemy engine."""
    if _engine is None:
        _init_engine()
    return _engine


def get_session():
    """Get a database session. Raises RuntimeError if DB not available."""
    if _engine is None:
        _init_engine()
    if not _SessionLocal:
        raise RuntimeError("Database not configured. Set DATABASE_URL env var.")
    return _SessionLocal()


def init_database():
    """Initialize the database by creating all tables."""
    if _engine is None:
        _init_engine()
    if _engine and _db_available:
        try:
            from .models import Base
            Base.metadata.create_all(bind=_engine)
            print("[DB] Tables created/verified")
        except Exception as e:
            print(f"[DB] Table creation warning: {e}")
    else:
        print("[DB] Skipping table creation — no database configured")