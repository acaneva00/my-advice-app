-- Enable Row Level Security on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_financial_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE advisors ENABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_client_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- Create a function to check if a user is an advisor
CREATE OR REPLACE FUNCTION is_advisor(user_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM advisors WHERE auth_id = user_id AND is_active = TRUE
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create a function to check if an advisor has access to a client
CREATE OR REPLACE FUNCTION advisor_has_client_access(advisor_id UUID, client_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 
    FROM advisor_client_relationships 
    WHERE advisor_id = advisor_id 
    AND client_id = client_id 
    AND status = 'active'
    AND (relationship_end IS NULL OR relationship_end > now())
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Users table policies
CREATE POLICY user_self_access ON users
  FOR ALL USING (auth.uid() = id);

CREATE POLICY advisor_client_access ON users
  FOR SELECT USING (
    is_advisor(auth.uid()) AND 
    EXISTS (
      SELECT 1 FROM advisor_client_relationships 
      WHERE advisor_id = (SELECT id FROM advisors WHERE auth_id = auth.uid())
      AND client_id = users.id
      AND status = 'active'
      AND (relationship_end IS NULL OR relationship_end > now())
    )
  );

-- User financial profiles policies
CREATE POLICY profile_self_access ON user_financial_profiles
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY profile_advisor_access ON user_financial_profiles
  FOR SELECT USING (
    is_advisor(auth.uid()) AND 
    EXISTS (
      SELECT 1 FROM advisor_client_relationships 
      WHERE advisor_id = (SELECT id FROM advisors WHERE auth_id = auth.uid())
      AND client_id = user_financial_profiles.user_id
      AND status = 'active'
      AND (relationship_end IS NULL OR relationship_end > now())
    )
  );

-- Chat sessions policies
CREATE POLICY session_self_access ON chat_sessions
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY session_advisor_access ON chat_sessions
  FOR SELECT USING (
    is_advisor(auth.uid()) AND 
    EXISTS (
      SELECT 1 FROM advisor_client_relationships 
      WHERE advisor_id = (SELECT id FROM advisors WHERE auth_id = auth.uid())
      AND client_id = chat_sessions.user_id
      AND status = 'active'
      AND (relationship_end IS NULL OR relationship_end > now())
    )
  );

-- Chat messages policies
CREATE POLICY messages_self_access ON chat_messages
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM chat_sessions
      WHERE chat_sessions.id = chat_messages.session_id
      AND chat_sessions.user_id = auth.uid()
    )
  );

CREATE POLICY messages_advisor_access ON chat_messages
  FOR SELECT USING (
    is_advisor(auth.uid()) AND 
    EXISTS (
      SELECT 1 FROM chat_sessions
      JOIN advisor_client_relationships ON chat_sessions.user_id = advisor_client_relationships.client_id
      WHERE chat_sessions.id = chat_messages.session_id
      AND advisor_client_relationships.advisor_id = (SELECT id FROM advisors WHERE auth_id = auth.uid())
      AND advisor_client_relationships.status = 'active'
      AND (advisor_client_relationships.relationship_end IS NULL OR advisor_client_relationships.relationship_end > now())
    )
  );

-- Advisor self-access policy
CREATE POLICY advisor_self_access ON advisors
  FOR ALL USING (auth.uid() = auth_id);

-- Administrators would have a separate policy with proper role checks

-- Advisor-client relationships policies
CREATE POLICY relationship_advisor_access ON advisor_client_relationships
  FOR ALL USING (
    (SELECT id FROM advisors WHERE auth_id = auth.uid()) = advisor_id
  );

CREATE POLICY relationship_client_view ON advisor_client_relationships
  FOR SELECT USING (
    client_id = auth.uid()
  );

-- User intents policies
CREATE POLICY intents_self_access ON user_intents
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY intents_advisor_access ON user_intents
  FOR SELECT USING (
    is_advisor(auth.uid()) AND 
    EXISTS (
      SELECT 1 FROM advisor_client_relationships 
      WHERE advisor_id = (SELECT id FROM advisors WHERE auth_id = auth.uid())
      AND client_id = user_intents.user_id
      AND status = 'active'
      AND (relationship_end IS NULL OR relationship_end > now())
    )
  );

-- Audit logs policies
CREATE POLICY audit_self_access ON audit_logs
  FOR SELECT USING (auth.uid() = user_id);
  
CREATE POLICY audit_advisor_access ON audit_logs
  FOR SELECT USING (
    is_advisor(auth.uid()) AND 
    (
      (SELECT id FROM advisors WHERE auth_id = auth.uid()) = advisor_id OR
      EXISTS (
        SELECT 1 FROM advisor_client_relationships 
        WHERE advisor_id = (SELECT id FROM advisors WHERE auth_id = auth.uid())
        AND client_id = audit_logs.user_id
        AND status = 'active'
        AND (relationship_end IS NULL OR relationship_end > now())
      )
    )
  );

-- Privacy consents policies
CREATE POLICY consents_self_access ON privacy_consents
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY consents_advisor_access ON privacy_consents
  FOR SELECT USING (
    is_advisor(auth.uid()) AND 
    EXISTS (
      SELECT 1 FROM advisor_client_relationships 
      WHERE advisor_id = (SELECT id FROM advisors WHERE auth_id = auth.uid())
      AND client_id = privacy_consents.user_id
      AND status = 'active'
      AND (relationship_end IS NULL OR relationship_end > now())
    )
  );

-- Notifications policies
CREATE POLICY notifications_self_access ON notifications
  FOR ALL USING (auth.uid() = user_id);