"""
DATABASE CONNECTION — PostgreSQL connection management for KRA Deadline Tracker.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from .models import Base


# Database URL from environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://helmet:helmet@localhost:5432/kra_helmet"
)

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,  # Recycle connections after 30 minutes
    echo=False,  # Set to True for SQL query logging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_engine():
    """Get the SQLAlchemy engine."""
    return engine


def get_session() -> Session:
    """Get a database session."""
    return SessionLocal()


def init_database():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(bind=engine)
