-- Auto-update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply the trigger to all tables with updated_at
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_financial_profiles_updated_at
    BEFORE UPDATE ON user_financial_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_advisors_updated_at
    BEFORE UPDATE ON advisors
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_advisor_client_relationships_updated_at
    BEFORE UPDATE ON advisor_client_relationships
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Audit logging function
CREATE OR REPLACE FUNCTION log_audit_event()
RETURNS TRIGGER AS $$
DECLARE
    current_user_id UUID;
    is_current_user_advisor BOOLEAN;
    resource_type TEXT;
BEGIN
    -- Get current user
    current_user_id := auth.uid();
    
    -- Determine if current user is an advisor
    SELECT EXISTS (SELECT 1 FROM advisors WHERE auth_id = current_user_id) INTO is_current_user_advisor;
    
    -- Set resource type based on table
    CASE TG_TABLE_NAME
        WHEN 'users' THEN resource_type := 'profile';
        WHEN 'user_financial_profiles' THEN resource_type := 'financial_profile';
        WHEN 'chat_sessions' THEN resource_type := 'chat_session';
        WHEN 'chat_messages' THEN resource_type := 'chat_message';
        WHEN 'advisor_client_relationships' THEN resource_type := 'client_relationship';
        ELSE resource_type := TG_TABLE_NAME;
    END CASE;
    
    -- Insert audit log
    INSERT INTO audit_logs (
        user_id,
        advisor_id,
        action_type,
        resource_type,
        resource_id,
        ip_address,
        user_agent
    ) VALUES (
        CASE WHEN NOT is_current_user_advisor THEN current_user_id ELSE NULL END,
        CASE WHEN is_current_user_advisor THEN (SELECT id FROM advisors WHERE auth_id = current_user_id) ELSE NULL END,
        TG_OP, -- 'INSERT', 'UPDATE', or 'DELETE'
        resource_type,
        CASE 
            WHEN TG_OP = 'DELETE' THEN OLD.id 
            ELSE NEW.id 
        END,
        COALESCE(
            current_setting('request.headers', true)::json->>'x-forwarded-for',
            current_setting('request.headers', true)::json->>'x-real-ip',
            'unknown'
        ),
        COALESCE(
            current_setting('request.headers', true)::json->>'user-agent',
            'unknown'
        )
    );
    
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Apply audit triggers to sensitive tables
CREATE TRIGGER audit_user_financial_profiles
    AFTER INSERT OR UPDATE OR DELETE ON user_financial_profiles
    FOR EACH ROW
    EXECUTE FUNCTION log_audit_event();

CREATE TRIGGER audit_advisor_client_relationships
    AFTER INSERT OR UPDATE OR DELETE ON advisor_client_relationships
    FOR EACH ROW
    EXECUTE FUNCTION log_audit_event();

-- Handle account deletions (GDPR/Privacy compliance)
CREATE OR REPLACE FUNCTION handle_user_deletion()
RETURNS TRIGGER AS $$
BEGIN
    -- Mark user as deleted but keep record
    UPDATE users
    SET is_deleted = TRUE,
        deletion_date = now(),
        email = 'deleted_' || OLD.id || '@deleted.example.com',
        first_name = 'Deleted',
        last_name = 'User',
        phone = NULL
    WHERE id = OLD.id;
    
    -- Return NULL to prevent the actual deletion
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create trigger to handle user deletion
CREATE TRIGGER prevent_user_deletion
    BEFORE DELETE ON users
    FOR EACH ROW
    EXECUTE FUNCTION handle_user_deletion();

-- Function to handle privacy consent tracking
CREATE OR REPLACE FUNCTION track_privacy_consent()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.privacy_version IS DISTINCT FROM OLD.privacy_version OR 
       NEW.terms_version IS DISTINCT FROM OLD.terms_version THEN
        
        -- Insert privacy policy consent if changed
        IF NEW.privacy_version IS DISTINCT FROM OLD.privacy_version THEN
            INSERT INTO privacy_consents (
                user_id,
                consent_type,
                version,
                ip_address,
                user_agent
            ) VALUES (
                NEW.id,
                'privacy_policy',
                NEW.privacy_version,
                COALESCE(
                    current_setting('request.headers', true)::json->>'x-forwarded-for',
                    current_setting('request.headers', true)::json->>'x-real-ip',
                    'unknown'
                ),
                COALESCE(
                    current_setting('request.headers', true)::json->>'user-agent',
                    'unknown'
                )
            );
        END IF;
        
        -- Insert terms of service consent if changed
        IF NEW.terms_version IS DISTINCT FROM OLD.terms_version THEN
            INSERT INTO privacy_consents (
                user_id,
                consent_type,
                version,
                ip_address,
                user_agent
            ) VALUES (
                NEW.id,
                'terms_of_service',
                NEW.terms_version,
                COALESCE(
                    current_setting('request.headers', true)::json->>'x-forwarded-for',
                    current_setting('request.headers', true)::json->>'x-real-ip',
                    'unknown'
                ),
                COALESCE(
                    current_setting('request.headers', true)::json->>'user-agent',
                    'unknown'
                )
            );
        END IF;
        
        -- Update consent timestamp
        NEW.consent_timestamp = now();
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Apply consent tracking trigger
CREATE TRIGGER track_user_consent
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION track_privacy_consent();