"""
DATABASE REPOSITORY — Data access layer for KRA Helmet.
Replaces JSON file operations with PostgreSQL database operations.
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from .models import SME, Filing, Obligation, MonitoringState, DecisionMemory
from .connection import get_session


class SMERepository:
    """Repository for SME data operations."""
    
    def __init__(self, session: Optional[Session] = None):
        self.session = session or get_session()
    
    def create(self, sme_data: Dict[str, Any]) -> SME:
        """Create a new SME record."""
        sme = SME(**sme_data)
        self.session.add(sme)
        self.session.commit()
        self.session.refresh(sme)
        return sme
    
    def get_by_pin(self, pin: str) -> Optional[SME]:
        """Get SME by PIN."""
        return self.session.query(SME).filter(SME.pin == pin).first()
    
    def get_all(self, active_only: bool = True) -> List[SME]:
        """Get all SMEs."""
        query = self.session.query(SME)
        if active_only:
            query = query.filter(SME.active == True)
        return query.all()
    
    def update(self, pin: str, data: Dict[str, Any]) -> Optional[SME]:
        """Update SME data."""
        sme = self.get_by_pin(pin)
        if not sme:
            return None
        for key, value in data.items():
            setattr(sme, key, value)
        sme.last_updated = datetime.utcnow()
        self.session.commit()
        self.session.refresh(sme)
        return sme
    
    def delete(self, pin: str) -> bool:
        """Soft delete SME by setting active=False."""
        sme = self.get_by_pin(pin)
        if not sme:
            return False
        sme.active = False
        self.session.commit()
        return True


class FilingRepository:
    """Repository for filing records."""
    
    def __init__(self, session: Optional[Session] = None):
        self.session = session or get_session()
    
    def create(self, filing_data: Dict[str, Any]) -> Filing:
        """Create a new filing record."""
        filing = Filing(**filing_data)
        self.session.add(filing)
        self.session.commit()
        self.session.refresh(filing)
        return filing
    
    def get_by_pin(self, pin: str, tax_type: Optional[str] = None) -> List[Filing]:
        """Get filings for an SME."""
        query = self.session.query(Filing).filter(Filing.pin == pin)
        if tax_type:
            query = query.filter(Filing.tax_type == tax_type)
        return query.order_by(desc(Filing.filed_at)).all()
    
    def get_all(self) -> List[Filing]:
        """Get all filings."""
        return self.session.query(Filing).order_by(desc(Filing.filed_at)).all()


class ObligationRepository:
    """Repository for obligation tracking."""
    
    def __init__(self, session: Optional[Session] = None):
        self.session = session or get_session()
    
    def create(self, obligation_data: Dict[str, Any]) -> Obligation:
        """Create a new obligation record."""
        obligation = Obligation(**obligation_data)
        self.session.add(obligation)
        self.session.commit()
        self.session.refresh(obligation)
        return obligation
    
    def get_by_pin(self, pin: str) -> List[Obligation]:
        """Get obligations for an SME."""
        return self.session.query(Obligation).filter(Obligation.pin == pin).all()
    
    def update(self, obligation_id: int, data: Dict[str, Any]) -> Optional[Obligation]:
        """Update obligation data."""
        obligation = self.session.query(Obligation).filter(Obligation.id == obligation_id).first()
        if not obligation:
            return None
        for key, value in data.items():
            setattr(obligation, key, value)
        self.session.commit()
        self.session.refresh(obligation)
        return obligation
    
    def delete_by_pin(self, pin: str) -> int:
        """Delete all obligations for an SME."""
        count = self.session.query(Obligation).filter(Obligation.pin == pin).delete()
        self.session.commit()
        return count


class MonitoringStateRepository:
    """Repository for monitoring state."""
    
    def __init__(self, session: Optional[Session] = None):
        self.session = session or get_session()
    
    def get_state(self, source_type: str, source_key: str) -> Optional[Dict[str, Any]]:
        """Get monitoring state."""
        state = self.session.query(MonitoringState).filter(
            and_(
                MonitoringState.source_type == source_type,
                MonitoringState.source_key == source_key
            )
        ).first()
        return state.state_data if state else None
    
    def set_state(self, source_type: str, source_key: str, state_data: Dict[str, Any]) -> MonitoringState:
        """Set monitoring state."""
        state = self.session.query(MonitoringState).filter(
            and_(
                MonitoringState.source_type == source_type,
                MonitoringState.source_key == source_key
            )
        ).first()
        
        if state:
            state.state_data = state_data
            state.last_updated = datetime.utcnow()
        else:
            state = MonitoringState(
                source_type=source_type,
                source_key=source_key,
                state_data=state_data
            )
            self.session.add(state)
        
        self.session.commit()
        self.session.refresh(state)
        return state
    
    def get_all_states(self, source_type: Optional[str] = None) -> List[MonitoringState]:
        """Get all monitoring states."""
        query = self.session.query(MonitoringState)
        if source_type:
            query = query.filter(MonitoringState.source_type == source_type)
        return query.all()


class DecisionMemoryRepository:
    """Repository for decision memory (learning system)."""
    
    def __init__(self, session: Optional[Session] = None):
        self.session = session or get_session()
    
    def create(self, decision_data: Dict[str, Any]) -> DecisionMemory:
        """Create a new decision memory entry."""
        decision = DecisionMemory(**decision_data)
        self.session.add(decision)
        self.session.commit()
        self.session.refresh(decision)
        return decision
    
    def get_by_pin(self, pin: str, limit: int = 100) -> List[DecisionMemory]:
        """Get decision history for an SME."""
        return self.session.query(DecisionMemory).filter(
            DecisionMemory.pin == pin
        ).order_by(desc(DecisionMemory.timestamp)).limit(limit).all()
    
    def get_by_type(self, decision_type: str, limit: int = 100) -> List[DecisionMemory]:
        """Get decisions by type."""
        return self.session.query(DecisionMemory).filter(
            DecisionMemory.decision_type == decision_type
        ).order_by(desc(DecisionMemory.timestamp)).limit(limit).all()
    
    def get_recent(self, hours: int = 24, limit: int = 100) -> List[DecisionMemory]:
        """Get recent decisions."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return self.session.query(DecisionMemory).filter(
            DecisionMemory.timestamp >= cutoff
        ).order_by(desc(DecisionMemory.timestamp)).limit(limit).all()
    
    def get_all(self, limit: int = 1000) -> List[DecisionMemory]:
        """Get all decisions."""
        return self.session.query(DecisionMemory).order_by(
            desc(DecisionMemory.timestamp)
        ).limit(limit).all()
