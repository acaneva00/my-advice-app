-- Create a new user with profile in a transaction
CREATE OR REPLACE FUNCTION create_user_with_profile(
    user_uuid UUID,
    user_email VARCHAR,
    first_name VARCHAR,
    last_name VARCHAR,
    phone VARCHAR,
    privacy_version VARCHAR,
    terms_version VARCHAR,
    current_age INTEGER DEFAULT NULL,
    current_balance DECIMAL DEFAULT NULL,
    current_income DECIMAL DEFAULT NULL,
    retirement_age INTEGER DEFAULT NULL,
    current_fund VARCHAR DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    profile_id UUID;
BEGIN
    -- Insert into users table
    INSERT INTO users (
        id, 
        email, 
        first_name, 
        last_name, 
        phone, 
        consent_timestamp,
        privacy_version,
        terms_version
    ) VALUES (
        user_uuid,
        user_email,
        first_name,
        last_name,
        phone,
        now(),
        privacy_version,
        terms_version
    );
    
    -- Insert initial financial profile if any data provided
    IF current_age IS NOT NULL OR current_balance IS NOT NULL OR current_fund IS NOT NULL THEN
        INSERT INTO user_financial_profiles (
            user_id,
            current_age,
            current_balance,
            current_income,
            retirement_age,
            current_fund
        ) VALUES (
            user_uuid,
            current_age,
            current_balance,
            current_income,
            retirement_age,
            current_fund
        )
        RETURNING id INTO profile_id;
    END IF;
    
    -- Record privacy consents
    INSERT INTO privacy_consents (
        user_id,
        consent_type,
        version
    ) VALUES 
    (user_uuid, 'privacy_policy', privacy_version),
    (user_uuid, 'terms_of_service', terms_version);
    
    RETURN user_uuid;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Update user financial profile with new information
CREATE OR REPLACE FUNCTION update_financial_profile(
    p_user_id UUID,
    p_current_age INTEGER DEFAULT NULL,
    p_current_balance DECIMAL DEFAULT NULL,
    p_current_income DECIMAL DEFAULT NULL,
    p_retirement_age INTEGER DEFAULT NULL,
    p_current_fund VARCHAR DEFAULT NULL,
    p_super_included BOOLEAN DEFAULT NULL,
    p_retirement_income_option VARCHAR DEFAULT NULL,
    p_retirement_income DECIMAL DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    existing_profile_id UUID;
    profile_id UUID;
BEGIN
    -- Check if user has an existing active profile
    SELECT id INTO existing_profile_id
    FROM user_financial_profiles
    WHERE user_id = p_user_id AND is_active = TRUE
    LIMIT 1;
    
    IF existing_profile_id IS NOT NULL THEN
        -- Update existing profile
        UPDATE user_financial_profiles
        SET 
            current_age = COALESCE(p_current_age, current_age),
            current_balance = COALESCE(p_current_balance, current_balance),
            current_income = COALESCE(p_current_income, current_income),
            retirement_age = COALESCE(p_retirement_age, retirement_age),
            current_fund = COALESCE(p_current_fund, current_fund),
            super_included = COALESCE(p_super_included, super_included),
            retirement_income_option = COALESCE(p_retirement_income_option, retirement_income_option),
            retirement_income = COALESCE(p_retirement_income, retirement_income),
            updated_at = now()
        WHERE id = existing_profile_id
        RETURNING id INTO profile_id;
    ELSE
        -- Create new profile
        INSERT INTO user_financial_profiles (
            user_id,
            current_age,
            current_balance,
            current_income,
            retirement_age,
            current_fund,
            super_included,
            retirement_income_option,
            retirement_income
        ) VALUES (
            p_user_id,
            p_current_age,
            p_current_balance,
            p_current_income,
            p_retirement_age,
            p_current_fund,
            p_super_included,
            p_retirement_income_option,
            p_retirement_income
        )
        RETURNING id INTO profile_id;
    END IF;
    
    RETURN profile_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Record a chat message
CREATE OR REPLACE FUNCTION record_chat_message(
    p_session_id UUID,
    p_sender_type VARCHAR,
    p_content TEXT,
    p_metadata JSONB DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    message_id UUID;
BEGIN
    INSERT INTO chat_messages (
        session_id,
        sender_type,
        content,
        metadata
    ) VALUES (
        p_session_id,
        p_sender_type,
        p_content,
        p_metadata
    )
    RETURNING id INTO message_id;
    
    RETURN message_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create or find chat session
CREATE OR REPLACE FUNCTION find_or_create_chat_session(
    p_user_id UUID,
    p_platform VARCHAR,
    p_external_session_id VARCHAR DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    session_id UUID;
BEGIN
    -- Check for existing active session
    SELECT id INTO session_id
    FROM chat_sessions
    WHERE user_id = p_user_id 
    AND platform = p_platform
    AND is_active = TRUE
    AND (p_external_session_id IS NULL OR external_session_id = p_external_session_id)
    ORDER BY started_at DESC
    LIMIT 1;
    
    -- Create new session if none exists
    IF session_id IS NULL THEN
        INSERT INTO chat_sessions (
            user_id,
            platform,
            external_session_id
        ) VALUES (
            p_user_id,
            p_platform,
            p_external_session_id
        )
        RETURNING id INTO session_id;
    END IF;
    
    RETURN session_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Record user intent
CREATE OR REPLACE FUNCTION record_user_intent(
    p_user_id UUID,
    p_session_id UUID,
    p_intent_type VARCHAR,
    p_intent_data JSONB
)
RETURNS UUID AS $$
DECLARE
    intent_id UUID;
BEGIN
    INSERT INTO user_intents (
        user_id,
        session_id,
        intent_type,
        intent_data
    ) VALUES (
        p_user_id,
        p_session_id,
        p_intent_type,
        p_intent_data
    )
    RETURNING id INTO intent_id;
    
    RETURN intent_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create advisor-client relationship
CREATE OR REPLACE FUNCTION create_advisor_client_relationship(
    p_advisor_id UUID,
    p_client_id UUID,
    p_status VARCHAR DEFAULT 'pending'
)
RETURNS UUID AS $$
DECLARE
    relationship_id UUID;
BEGIN
    INSERT INTO advisor_client_relationships (
        advisor_id,
        client_id,
        status
    ) VALUES (
        p_advisor_id,
        p_client_id,
        p_status
    )
    RETURNING id INTO relationship_id;
    
    -- Create notification for client
    INSERT INTO notifications (
        user_id,
        title,
        message,
        notification_type
    ) VALUES (
        p_client_id,
        'New Advisor Connection',
        (SELECT first_name || ' ' || last_name FROM advisors WHERE id = p_advisor_id) || 
        ' would like to connect with you as your financial advisor.',
        'advisor'
    );
    
    RETURN relationship_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Get user data for advisors (compliant with privacy regulations)
CREATE OR REPLACE FUNCTION get_client_data_for_advisor(
    p_advisor_id UUID,
    p_client_id UUID
)
RETURNS TABLE (
    client_id UUID,
    first_name VARCHAR,
    last_name VARCHAR,
    email VARCHAR,
    current_age INTEGER,
    current_balance DECIMAL,
    current_income DECIMAL,
    retirement_age INTEGER,
    current_fund VARCHAR,
    retirement_balance DECIMAL,
    relationship_start TIMESTAMP WITH TIME ZONE,
    most_recent_session TIMESTAMP WITH TIME ZONE,
    session_count INTEGER
) AS $$
BEGIN
    -- Validate relationship
    IF NOT advisor_has_client_access(p_advisor_id, p_client_id) THEN
        RAISE EXCEPTION 'Advisor does not have access to this client';
    END IF;
    
    RETURN QUERY
    SELECT 
        u.id as client_id,
        u.first_name,
        u.last_name,
        u.email,
        fp.current_age,
        fp.current_balance,
        fp.current_income,
        fp.retirement_age,
        fp.current_fund,
        fp.retirement_balance,
        acr.relationship_start,
        (SELECT MAX(started_at) FROM chat_sessions WHERE user_id = p_client_id) as most_recent_session,
        (SELECT COUNT(*) FROM chat_sessions WHERE user_id = p_client_id) as session_count
    FROM users u
    LEFT JOIN user_financial_profiles fp ON u.id = fp.user_id AND fp.is_active = TRUE
    JOIN advisor_client_relationships acr ON u.id = acr.client_id
    WHERE u.id = p_client_id
    AND acr.advisor_id = p_advisor_id
    AND acr.status = 'active'
    AND (acr.relationship_end IS NULL OR acr.relationship_end > now());
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;