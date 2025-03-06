-- Update financial profile stored procedure to include additional fields
CREATE OR REPLACE FUNCTION update_financial_profile(
    p_user_id UUID,
    p_current_age INTEGER DEFAULT NULL,
    p_current_balance DECIMAL DEFAULT NULL,
    p_current_income DECIMAL DEFAULT NULL,
    p_retirement_age INTEGER DEFAULT NULL,
    p_current_fund VARCHAR DEFAULT NULL,
    p_super_included BOOLEAN DEFAULT NULL,
    p_retirement_income_option VARCHAR DEFAULT NULL,
    p_retirement_income DECIMAL DEFAULT NULL,
    p_income_net_of_super DECIMAL DEFAULT NULL,
    p_after_tax_income DECIMAL DEFAULT NULL,
    p_retirement_balance DECIMAL DEFAULT NULL,
    p_retirement_drawdown_age INTEGER DEFAULT NULL
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
            income_net_of_super = COALESCE(p_income_net_of_super, income_net_of_super),
            after_tax_income = COALESCE(p_after_tax_income, after_tax_income),
            retirement_balance = COALESCE(p_retirement_balance, retirement_balance),
            retirement_drawdown_age = COALESCE(p_retirement_drawdown_age, retirement_drawdown_age),
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
            retirement_income,
            income_net_of_super,
            after_tax_income,
            retirement_balance,
            retirement_drawdown_age
        ) VALUES (
            p_user_id,
            p_current_age,
            p_current_balance,
            p_current_income,
            p_retirement_age,
            p_current_fund,
            p_super_included,
            p_retirement_income_option,
            p_retirement_income,
            p_income_net_of_super,
            p_after_tax_income,
            p_retirement_balance,
            p_retirement_drawdown_age
        )
        RETURNING id INTO profile_id;
    END IF;
    
    RETURN profile_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Add comment to document the change
COMMENT ON FUNCTION update_financial_profile(UUID, INTEGER, DECIMAL, DECIMAL, INTEGER, VARCHAR, BOOLEAN, VARCHAR, DECIMAL, DECIMAL, DECIMAL, DECIMAL, INTEGER) IS 
'Updated to include income_net_of_super, after_tax_income, retirement_balance, and retirement_drawdown_age fields';