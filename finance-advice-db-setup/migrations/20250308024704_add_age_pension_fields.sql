-- Add Age Pension fields to user_financial_profiles table
ALTER TABLE user_financial_profiles 
ADD COLUMN relationship_status VARCHAR(10) DEFAULT NULL,
ADD COLUMN homeowner_status BOOLEAN DEFAULT NULL,
ADD COLUMN cash_assets NUMERIC DEFAULT NULL,
ADD COLUMN share_investments NUMERIC DEFAULT NULL,
ADD COLUMN investment_properties NUMERIC DEFAULT NULL,
ADD COLUMN non_financial_assets NUMERIC DEFAULT NULL;

-- Update the update_financial_profile stored procedure
CREATE OR REPLACE FUNCTION update_financial_profile(
  p_user_id UUID,
  p_current_age INTEGER DEFAULT NULL,
  p_current_balance NUMERIC DEFAULT NULL,
  p_current_income NUMERIC DEFAULT NULL,
  p_retirement_age INTEGER DEFAULT NULL,
  p_current_fund VARCHAR DEFAULT NULL,
  p_super_included BOOLEAN DEFAULT NULL,
  p_retirement_income_option VARCHAR DEFAULT NULL,
  p_retirement_income NUMERIC DEFAULT NULL,
  p_income_net_of_super NUMERIC DEFAULT NULL,
  p_after_tax_income NUMERIC DEFAULT NULL,
  p_retirement_balance NUMERIC DEFAULT NULL,
  p_retirement_drawdown_age INTEGER DEFAULT NULL,
  p_relationship_status VARCHAR DEFAULT NULL,
  p_homeowner_status BOOLEAN DEFAULT NULL,
  p_cash_assets NUMERIC DEFAULT NULL,
  p_share_investments NUMERIC DEFAULT NULL,
  p_investment_properties NUMERIC DEFAULT NULL,
  p_non_financial_assets NUMERIC DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
  profile_id UUID;
BEGIN
  -- Check if user exists
  IF NOT EXISTS (SELECT 1 FROM users WHERE id = p_user_id) THEN
    RAISE EXCEPTION 'User with ID % does not exist', p_user_id;
  END IF;
  
  -- Create or update financial profile
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
    relationship_status = COALESCE(p_relationship_status, relationship_status),
    homeowner_status = COALESCE(p_homeowner_status, homeowner_status),
    cash_assets = COALESCE(p_cash_assets, cash_assets),
    share_investments = COALESCE(p_share_investments, share_investments),
    investment_properties = COALESCE(p_investment_properties, investment_properties),
    non_financial_assets = COALESCE(p_non_financial_assets, non_financial_assets),
    updated_at = NOW()
  WHERE user_id = p_user_id
  RETURNING id INTO profile_id;
  
  -- If profile doesn't exist, create it
  IF profile_id IS NULL THEN
    INSERT INTO user_financial_profiles (
      user_id, current_age, current_balance, current_income, retirement_age,
      current_fund, super_included, retirement_income_option, retirement_income,
      income_net_of_super, after_tax_income, retirement_balance, retirement_drawdown_age,
      relationship_status, homeowner_status, cash_assets, share_investments, 
      investment_properties, non_financial_assets
    ) VALUES (
      p_user_id, p_current_age, p_current_balance, p_current_income, p_retirement_age,
      p_current_fund, p_super_included, p_retirement_income_option, p_retirement_income,
      p_income_net_of_super, p_after_tax_income, p_retirement_balance, p_retirement_drawdown_age,
      p_relationship_status, p_homeowner_status, p_cash_assets, p_share_investments,
      p_investment_properties, p_non_financial_assets
    )
    RETURNING id INTO profile_id;
  END IF;
  
  RETURN profile_id;
END;
$$ LANGUAGE plpgsql;