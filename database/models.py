"""
DATABASE MODELS — SQLAlchemy ORM models for KRA Deadline Tracker data.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import relationship

EAT = timezone(timedelta(hours=3))


def _now_eat():
    return datetime.now(EAT)

class Base(DeclarativeBase):
    pass


class SME(Base):
    """SME profile data."""
    __tablename__ = "smes"
    
    pin = Column(String(20), primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    business_name = Column(String(200))
    business_type = Column(String(50))
    industry = Column(String(100))
    county = Column(String(50))
    sub_county = Column(String(50))
    annual_turnover_kes = Column(Float, default=0)
    turnover_bracket = Column(String(20))
    has_employees = Column(Boolean, default=False)
    employee_count = Column(Integer, default=0)
    is_vat_registered = Column(Boolean, default=False)
    has_etims = Column(Boolean, default=False)
    phone = Column(String(20))
    email = Column(String(100))
    preferred_language = Column(String(5), default="en")
    preferred_channel = Column(String(20), default="whatsapp")
    rental_income_annual_kes = Column(Float)
    classification = Column(JSON)
    onboarded_at = Column(DateTime(timezone=True), default=_now_eat)
    last_updated = Column(DateTime(timezone=True), default=_now_eat, onupdate=_now_eat)
    active = Column(Boolean, default=True)
    
    # Relationships
    filings = relationship("Filing", back_populates="sme", cascade="all, delete-orphan")
    obligations = relationship("Obligation", back_populates="sme", cascade="all, delete-orphan")
    decisions = relationship("DecisionMemory", back_populates="sme", cascade="all, delete-orphan")


class Filing(Base):
    """Tax filing records."""
    __tablename__ = "filings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pin = Column(String(20), ForeignKey("smes.pin"), nullable=False, index=True)
    tax_type = Column(String(50), nullable=False)
    period = Column(String(10), nullable=False)  # YYYY-MM format
    amount_kes = Column(Float, default=0)
    reference = Column(String(100))
    filed_at = Column(DateTime(timezone=True), default=_now_eat)
    recorded_by = Column(String(50))
    
    # Relationships
    sme = relationship("SME", back_populates="filings")


class Obligation(Base):
    """Tax obligation tracking."""
    __tablename__ = "obligations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pin = Column(String(20), ForeignKey("smes.pin"), nullable=False, index=True)
    tax_type = Column(String(50), nullable=False)
    tax_name = Column(String(100))
    description = Column(Text)
    frequency = Column(String(20))
    deadline_day = Column(Integer)
    deadline_date = Column(String(20))
    rate = Column(String(50))
    penalty_late_filing = Column(Float)
    penalty_late_payment_pct = Column(Float)
    interest_monthly_pct = Column(Float)
    etims_required = Column(Boolean, default=False)
    itax_code = Column(String(20))
    status = Column(String(20), default="upcoming")
    confidence = Column(Float, default=0.85)
    source = Column(String(50))
    next_deadline = Column(String(20))
    recommended_file_by = Column(String(20))
    days_until_deadline = Column(Integer)
    filing_month = Column(String(30))
    auto_proceed = Column(Boolean, default=True)
    checked_at = Column(DateTime(timezone=True), default=_now_eat)
    
    # Relationships
    sme = relationship("SME", back_populates="obligations")


class MonitoringState(Base):
    """Monitoring state for KRA, gazette, and eTIMS."""
    __tablename__ = "monitoring_state"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String(50), nullable=False, index=True)  # kra, gazette, etims
    source_key = Column(String(100), nullable=False)
    state_data = Column(JSON, nullable=False)
    last_updated = Column(DateTime(timezone=True), default=_now_eat, onupdate=_now_eat)


class Subscription(Base):
    """SME subscription state."""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pin = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(200), default="")
    plan = Column(String(20), nullable=False, default="trial")
    plan_name = Column(String(50), default="")
    status = Column(String(20), nullable=False, default="active", index=True)
    amount_paid_kes = Column(Float, default=0)
    started_at = Column(DateTime(timezone=True), default=_now_eat)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_eat)

    # Relationships
    payments = relationship("Payment", back_populates="subscription", cascade="all, delete-orphan",
                            order_by="Payment.recorded_at")


class Payment(Base):
    """M-Pesa payment records (append-only ledger)."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pin = Column(String(20), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=False)
    amount_kes = Column(Float, nullable=False)
    mpesa_ref = Column(String(100), default="", index=True)
    phone = Column(String(200), default="")  # encrypted
    plan = Column(String(20), nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=_now_eat)

    # Relationships
    subscription = relationship("Subscription", back_populates="payments")


class AuditTrailEntry(Base):
    """Immutable audit trail entries."""
    __tablename__ = "audit_trail"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)
    agent = Column(String(100))
    sme_pin = Column(String(20), index=True)
    details = Column(JSON)
    timestamp = Column(DateTime(timezone=True), default=_now_eat, index=True)


class DecisionMemory(Base):
    """Decision memory for learning system."""
    __tablename__ = "decision_memory"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pin = Column(String(20), ForeignKey("smes.pin"), nullable=False, index=True)
    decision_type = Column(String(50), nullable=False, index=True)
    context = Column(JSON, nullable=False)
    outcome = Column(String(50))
    timestamp = Column(DateTime(timezone=True), default=_now_eat, index=True)
    
    # Relationships
    sme = relationship("SME", back_populates="decisions")
