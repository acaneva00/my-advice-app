-- Schema for users (authentication handled by Supabase Auth)
CREATE TABLE users (
    id UUID PRIMARY KEY REFERENCES auth.users(id),
    email VARCHAR NOT NULL,
    first_name VARCHAR,
    last_name VARCHAR,
    phone VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    consent_timestamp TIMESTAMP WITH TIME ZONE,
    privacy_version VARCHAR,
    terms_version VARCHAR,
    marketing_opt_in BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,
    deletion_date TIMESTAMP WITH TIME ZONE
);

-- Schema for user financial profiles
CREATE TABLE user_financial_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    current_age INTEGER,
    current_balance DECIMAL(15, 2),
    current_income DECIMAL(15, 2),
    retirement_age INTEGER,
    current_fund VARCHAR,
    super_included BOOLEAN,
    income_net_of_super DECIMAL(15, 2),
    after_tax_income DECIMAL(15, 2),
    retirement_balance DECIMAL(15, 2),
    retirement_income DECIMAL(15, 2),
    retirement_income_option VARCHAR,
    retirement_drawdown_age INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Schema for chat sessions
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    platform VARCHAR NOT NULL, -- 'webchat', 'whatsapp', 'instagram', etc.
    external_session_id VARCHAR, -- Platform-specific session identifier
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    ended_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE
);

-- Schema for chat messages
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    sender_type VARCHAR NOT NULL, -- 'user' or 'assistant'
    content TEXT NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    metadata JSONB -- For any platform-specific metadata
);

-- Schema for advisor relationships
CREATE TABLE advisors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    auth_id UUID REFERENCES auth.users(id),
    email VARCHAR NOT NULL,
    first_name VARCHAR NOT NULL,
    last_name VARCHAR NOT NULL,
    phone VARCHAR,
    afsl_number VARCHAR, -- Australian Financial Services License number
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Schema for advisor-client relationships
CREATE TABLE advisor_client_relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    advisor_id UUID NOT NULL REFERENCES advisors(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    relationship_start TIMESTAMP WITH TIME ZONE DEFAULT now(),
    relationship_end TIMESTAMP WITH TIME ZONE,
    status VARCHAR NOT NULL, -- 'active', 'pending', 'terminated'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    UNIQUE (advisor_id, client_id)
);

-- Schema for recording intent and actions during conversation
CREATE TABLE user_intents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    intent_type VARCHAR NOT NULL, -- 'compare_fees', 'project_balance', etc.
    intent_data JSONB, -- Store all relevant data for this intent
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Schema for audit logs (for compliance tracking)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    advisor_id UUID REFERENCES advisors(id) ON DELETE SET NULL,
    action_type VARCHAR NOT NULL, -- 'view', 'edit', 'delete', etc.
    resource_type VARCHAR NOT NULL, -- 'profile', 'message', etc.
    resource_id UUID NOT NULL,
    action_timestamp TIMESTAMP WITH TIME ZONE DEFAULT now(),
    ip_address VARCHAR,
    user_agent VARCHAR
);

-- Schema for storing privacy consents
CREATE TABLE privacy_consents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type VARCHAR NOT NULL, -- 'privacy_policy', 'terms_of_service', 'data_sharing'
    version VARCHAR NOT NULL,
    consented_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    ip_address VARCHAR,
    user_agent VARCHAR
);

-- Schema for storing user notifications
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR NOT NULL,
    message TEXT NOT NULL,
    notification_type VARCHAR NOT NULL, -- 'system', 'advisor', 'financial'
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);