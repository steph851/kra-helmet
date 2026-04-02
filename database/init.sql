-- KRA HELMET Database Initialization Script
-- This script creates the database schema for the KRA Helmet application

-- Create database if not exists (handled by docker-compose)
-- CREATE DATABASE IF NOT EXISTS kra_helmet;

-- Use the database
-- \c kra_helmet;

-- Create SMEs table
CREATE TABLE IF NOT EXISTS smes (
    id SERIAL PRIMARY KEY,
    pin VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    business_name VARCHAR(255),
    business_type VARCHAR(100),
    industry VARCHAR(100),
    county VARCHAR(100),
    sub_county VARCHAR(100),
    annual_turnover_kes DECIMAL(15, 2) DEFAULT 0,
    turnover_bracket VARCHAR(50),
    has_employees BOOLEAN DEFAULT FALSE,
    employee_count INTEGER DEFAULT 0,
    is_vat_registered BOOLEAN DEFAULT FALSE,
    has_etims BOOLEAN DEFAULT FALSE,
    phone VARCHAR(20),
    email VARCHAR(255),
    preferred_language VARCHAR(10) DEFAULT 'en',
    preferred_channel VARCHAR(20) DEFAULT 'whatsapp',
    rental_income_annual_kes DECIMAL(15, 2),
    classification JSONB,
    onboarded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index on PIN for faster lookups
CREATE INDEX IF NOT EXISTS idx_smes_pin ON smes(pin);
CREATE INDEX IF NOT EXISTS idx_smes_active ON smes(active);

-- Create filings table
CREATE TABLE IF NOT EXISTS filings (
    id SERIAL PRIMARY KEY,
    pin VARCHAR(20) NOT NULL,
    tax_type VARCHAR(50) NOT NULL,
    period VARCHAR(20) NOT NULL,
    amount_kes DECIMAL(15, 2) DEFAULT 0,
    reference VARCHAR(100),
    filed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    recorded_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pin) REFERENCES smes(pin) ON DELETE CASCADE
);

-- Create indexes for filings
CREATE INDEX IF NOT EXISTS idx_filings_pin ON filings(pin);
CREATE INDEX IF NOT EXISTS idx_filings_tax_type ON filings(tax_type);
CREATE INDEX IF NOT EXISTS idx_filings_period ON filings(period);
CREATE INDEX IF NOT EXISTS idx_filings_filed_at ON filings(filed_at);

-- Create obligations table
CREATE TABLE IF NOT EXISTS obligations (
    id SERIAL PRIMARY KEY,
    pin VARCHAR(20) NOT NULL,
    tax_type VARCHAR(50) NOT NULL,
    tax_name VARCHAR(100),
    description TEXT,
    frequency VARCHAR(20),
    deadline_day INTEGER,
    deadline_date VARCHAR(20),
    rate VARCHAR(50),
    penalty_late_filing DECIMAL(15, 2),
    penalty_late_payment_pct DECIMAL(5, 2),
    interest_monthly_pct DECIMAL(5, 2),
    etims_required BOOLEAN DEFAULT FALSE,
    itax_code VARCHAR(20),
    status VARCHAR(20) DEFAULT 'upcoming',
    confidence DECIMAL(3, 2) DEFAULT 0.85,
    source VARCHAR(50),
    next_deadline VARCHAR(20),
    recommended_file_by VARCHAR(20),
    days_until_deadline INTEGER,
    filing_month VARCHAR(30),
    auto_proceed BOOLEAN DEFAULT TRUE,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pin) REFERENCES smes(pin) ON DELETE CASCADE
);

-- Create indexes for obligations
CREATE INDEX IF NOT EXISTS idx_obligations_pin ON obligations(pin);
CREATE INDEX IF NOT EXISTS idx_obligations_tax_type ON obligations(tax_type);
CREATE INDEX IF NOT EXISTS idx_obligations_status ON obligations(status);
CREATE INDEX IF NOT EXISTS idx_obligations_next_deadline ON obligations(next_deadline);

-- Create monitoring_state table
CREATE TABLE IF NOT EXISTS monitoring_state (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL,
    source_key VARCHAR(100) NOT NULL,
    state_data JSONB NOT NULL,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_type, source_key)
);

-- Create indexes for monitoring_state
CREATE INDEX IF NOT EXISTS idx_monitoring_state_source_type ON monitoring_state(source_type);
CREATE INDEX IF NOT EXISTS idx_monitoring_state_source_key ON monitoring_state(source_key);

-- Create decision_memory table
CREATE TABLE IF NOT EXISTS decision_memory (
    id SERIAL PRIMARY KEY,
    pin VARCHAR(20) NOT NULL,
    decision_type VARCHAR(50) NOT NULL,
    context JSONB NOT NULL,
    outcome VARCHAR(50),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pin) REFERENCES smes(pin) ON DELETE CASCADE
);

-- Create indexes for decision_memory
CREATE INDEX IF NOT EXISTS idx_decision_memory_pin ON decision_memory(pin);
CREATE INDEX IF NOT EXISTS idx_decision_memory_decision_type ON decision_memory(decision_type);
CREATE INDEX IF NOT EXISTS idx_decision_memory_timestamp ON decision_memory(timestamp);

-- Create audit_trail table
CREATE TABLE IF NOT EXISTS audit_trail (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    agent VARCHAR(100),
    sme_pin VARCHAR(20),
    details JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for audit_trail
CREATE INDEX IF NOT EXISTS idx_audit_trail_event_type ON audit_trail(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_trail_sme_pin ON audit_trail(sme_pin);
CREATE INDEX IF NOT EXISTS idx_audit_trail_timestamp ON audit_trail(timestamp);

-- Create users table for access control
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    api_key_hash VARCHAR(255),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE
);

-- Create indexes for users
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- Create alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    pin VARCHAR(20) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    channel VARCHAR(20),
    message TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    scheduled_at TIMESTAMP WITH TIME ZONE,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pin) REFERENCES smes(pin) ON DELETE CASCADE
);

-- Create indexes for alerts
CREATE INDEX IF NOT EXISTS idx_alerts_pin ON alerts(pin);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_scheduled_at ON alerts(scheduled_at);

-- Create escalations table
CREATE TABLE IF NOT EXISTS escalations (
    id SERIAL PRIMARY KEY,
    pin VARCHAR(20) NOT NULL,
    tier VARCHAR(20) NOT NULL,
    reason TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pin) REFERENCES smes(pin) ON DELETE CASCADE
);

-- Create indexes for escalations
CREATE INDEX IF NOT EXISTS idx_escalations_pin ON escalations(pin);
CREATE INDEX IF NOT EXISTS idx_escalations_tier ON escalations(tier);
CREATE INDEX IF NOT EXISTS idx_escalations_status ON escalations(status);

-- Create model_updates table for learning system
CREATE TABLE IF NOT EXISTS model_updates (
    id SERIAL PRIMARY KEY,
    update_type VARCHAR(50) NOT NULL,
    old_weights JSONB,
    new_weights JSONB,
    reasoning TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    applied_at TIMESTAMP WITH TIME ZONE,
    applied_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for model_updates
CREATE INDEX IF NOT EXISTS idx_model_updates_status ON model_updates(status);
CREATE INDEX IF NOT EXISTS idx_model_updates_created_at ON model_updates(created_at);

-- Grant permissions to the helmet user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO helmet;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO helmet;
