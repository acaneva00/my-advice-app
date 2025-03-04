-- Indexes for users table
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_deleted ON users(is_deleted);

-- Indexes for user_financial_profiles table
CREATE INDEX idx_profiles_user_id ON user_financial_profiles(user_id);
CREATE INDEX idx_profiles_is_active ON user_financial_profiles(is_active);
CREATE INDEX idx_profiles_current_fund ON user_financial_profiles(current_fund);

-- Indexes for chat_sessions table
CREATE INDEX idx_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX idx_sessions_platform ON chat_sessions(platform);
CREATE INDEX idx_sessions_external_id ON chat_sessions(external_session_id);
CREATE INDEX idx_sessions_started_at ON chat_sessions(started_at);
CREATE INDEX idx_sessions_is_active ON chat_sessions(is_active);

-- Indexes for chat_messages table
CREATE INDEX idx_messages_session_id ON chat_messages(session_id);
CREATE INDEX idx_messages_sent_at ON chat_messages(sent_at);
CREATE INDEX idx_messages_sender_type ON chat_messages(sender_type);

-- Indexes for advisors table
CREATE INDEX idx_advisors_auth_id ON advisors(auth_id);
CREATE INDEX idx_advisors_email ON advisors(email);
CREATE INDEX idx_advisors_is_active ON advisors(is_active);

-- Indexes for advisor_client_relationships table
CREATE INDEX idx_relationships_advisor_id ON advisor_client_relationships(advisor_id);
CREATE INDEX idx_relationships_client_id ON advisor_client_relationships(client_id);
CREATE INDEX idx_relationships_status ON advisor_client_relationships(status);
CREATE INDEX idx_relationships_start ON advisor_client_relationships(relationship_start);

-- Indexes for user_intents table
CREATE INDEX idx_intents_user_id ON user_intents(user_id);
CREATE INDEX idx_intents_session_id ON user_intents(session_id);
CREATE INDEX idx_intents_type ON user_intents(intent_type);
CREATE INDEX idx_intents_created_at ON user_intents(created_at);

-- Indexes for audit_logs table
CREATE INDEX idx_audit_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_advisor_id ON audit_logs(advisor_id);
CREATE INDEX idx_audit_action_type ON audit_logs(action_type);
CREATE INDEX idx_audit_resource_type ON audit_logs(resource_type);
CREATE INDEX idx_audit_resource_id ON audit_logs(resource_id);
CREATE INDEX idx_audit_timestamp ON audit_logs(action_timestamp);

-- Indexes for privacy_consents table
CREATE INDEX idx_consents_user_id ON privacy_consents(user_id);
CREATE INDEX idx_consents_type ON privacy_consents(consent_type);
CREATE INDEX idx_consents_version ON privacy_consents(version);
CREATE INDEX idx_consents_timestamp ON privacy_consents(consented_at);

-- Indexes for notifications table
CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_is_read ON notifications(is_read);
CREATE INDEX idx_notifications_created_at ON notifications(created_at);
CREATE INDEX idx_notifications_type ON notifications(notification_type);