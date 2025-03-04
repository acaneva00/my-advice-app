-- View for user profile summary (used by chat applications)
CREATE OR REPLACE VIEW user_profile_summary AS
SELECT 
    u.id AS user_id,
    u.email,
    u.first_name,
    u.last_name,
    ufp.current_age,
    ufp.current_balance,
    ufp.current_income,
    ufp.retirement_age,
    ufp.current_fund,
    ufp.super_included,
    ufp.income_net_of_super,
    ufp.after_tax_income,
    ufp.retirement_balance,
    ufp.retirement_income,
    ufp.retirement_income_option,
    ufp.retirement_drawdown_age,
    pc.version AS privacy_version,
    u.consent_timestamp,
    CASE WHEN u.is_deleted THEN TRUE ELSE FALSE END AS account_deleted
FROM 
    users u
LEFT JOIN 
    user_financial_profiles ufp ON u.id = ufp.user_id AND ufp.is_active = TRUE
LEFT JOIN 
    (
        SELECT DISTINCT ON (user_id) 
            user_id, 
            version, 
            consented_at
        FROM 
            privacy_consents
        WHERE 
            consent_type = 'privacy_policy'
        ORDER BY 
            user_id, consented_at DESC
    ) pc ON u.id = pc.user_id;

-- View for advisor dashboard
CREATE OR REPLACE VIEW advisor_client_dashboard AS
SELECT 
    a.id AS advisor_id,
    a.first_name AS advisor_first_name,
    a.last_name AS advisor_last_name,
    u.id AS client_id,
    u.first_name AS client_first_name,
    u.last_name AS client_last_name,
    u.email AS client_email,
    acr.status AS relationship_status,
    acr.relationship_start,
    ufp.current_age,
    ufp.current_balance,
    ufp.current_income,
    ufp.retirement_age,
    ufp.current_fund,
    ufp.retirement_balance,
    (SELECT MAX(started_at) FROM chat_sessions WHERE user_id = u.id) AS last_interaction,
    (SELECT COUNT(*) FROM chat_sessions WHERE user_id = u.id) AS session_count,
    (SELECT COUNT(*) FROM user_intents WHERE user_id = u.id) AS intent_count
FROM 
    advisors a
JOIN 
    advisor_client_relationships acr ON a.id = acr.advisor_id
JOIN 
    users u ON acr.client_id = u.id
LEFT JOIN 
    user_financial_profiles ufp ON u.id = ufp.user_id AND ufp.is_active = TRUE
WHERE 
    (acr.relationship_end IS NULL OR acr.relationship_end > now())
    AND u.is_deleted = FALSE
    AND a.is_active = TRUE;

-- View for chat history with intent analysis
CREATE OR REPLACE VIEW chat_history_with_intents AS
SELECT 
    cs.id AS session_id,
    cs.user_id,
    cs.platform,
    cs.started_at,
    cs.ended_at,
    cm.id AS message_id,
    cm.sender_type,
    cm.content,
    cm.sent_at,
    ui.intent_type,
    ui.intent_data
FROM 
    chat_sessions cs
JOIN 
    chat_messages cm ON cs.id = cm.session_id
LEFT JOIN 
    user_intents ui ON cs.id = ui.session_id AND cs.user_id = ui.user_id
ORDER BY 
    cs.started_at DESC, cm.sent_at ASC;

-- View for privacy compliance reporting
CREATE OR REPLACE VIEW privacy_compliance_summary AS
SELECT 
    u.id AS user_id,
    u.email,
    u.is_deleted,
    u.deletion_date,
    pp.version AS privacy_policy_version,
    pp.consented_at AS privacy_policy_consent_date,
    tos.version AS terms_version,
    tos.consented_at AS terms_consent_date,
    (SELECT COUNT(*) FROM audit_logs WHERE user_id = u.id) AS user_audit_count,
    (SELECT COUNT(*) FROM chat_sessions WHERE user_id = u.id) AS session_count,
    (SELECT MAX(started_at) FROM chat_sessions WHERE user_id = u.id) AS last_session_date
FROM 
    users u
LEFT JOIN 
    (
        SELECT DISTINCT ON (user_id) 
            user_id, 
            version, 
            consented_at
        FROM 
            privacy_consents
        WHERE 
            consent_type = 'privacy_policy'
        ORDER BY 
            user_id, consented_at DESC
    ) pp ON u.id = pp.user_id
LEFT JOIN 
    (
        SELECT DISTINCT ON (user_id) 
            user_id, 
            version, 
            consented_at
        FROM 
            privacy_consents
        WHERE 
            consent_type = 'terms_of_service'
        ORDER BY 
            user_id, consented_at DESC
    ) tos ON u.id = tos.user_id;

-- View for user financial progression over time
CREATE OR REPLACE VIEW user_financial_progression AS
WITH intent_progression AS (
    SELECT
        ui.user_id,
        ui.created_at,
        ui.intent_type,
        ui.intent_data->'current_balance' AS balance,
        ui.intent_data->'current_income' AS income,
        ui.intent_data->'current_fund' AS fund,
        ui.intent_data->'retirement_age' AS retirement_age
    FROM
        user_intents ui
    WHERE
        ui.intent_data IS NOT NULL
)
SELECT
    ui.user_id,
    u.first_name,
    u.last_name,
    u.email,
    ui.created_at AS recorded_date,
    ui.intent_type,
    ui.balance::DECIMAL AS balance_at_time,
    ui.income::DECIMAL AS income_at_time,
    ui.fund::TEXT AS fund_at_time,
    ui.retirement_age::INTEGER AS retirement_age_at_time,
    ufp.current_balance AS current_balance,
    ufp.current_income AS current_income,
    ufp.current_fund AS current_fund,
    ufp.retirement_age AS current_retirement_age
FROM
    intent_progression ui
JOIN
    users u ON ui.user_id = u.id
LEFT JOIN
    user_financial_profiles ufp ON u.id = ufp.user_id AND ufp.is_active = TRUE
ORDER BY
    ui.user_id, ui.created_at;