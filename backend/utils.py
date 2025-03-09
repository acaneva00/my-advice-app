# backend/utils.py
import re
import json
import pandas as pd
import openai
from openai import OpenAI
from backend.cashflow import calculate_income_net_of_super, calculate_after_tax_income

VARIABLE_TYPE_MAP = {
    # Boolean variables
    "super_included": {"type": "boolean", "true_values": ["yes", "true", "included", "includes", "part of", "package"],
                      "false_values": ["no", "false", "not included", "separate", "on top", "additional"]},
    "homeowner_status": {"type": "boolean", "true_values": ["own", "yes", "homeowner", "i own", "own home", "true"],
                        "false_values": ["rent", "no", "renting", "i rent", "tenant", "false"]},
    
    # Integer variables
    "current_age": {"type": "integer"},
    "retirement_age": {"type": "integer"},
    "retirement_drawdown_age": {"type": "integer"},
    
    # Float/Currency variables
    "current_balance": {"type": "currency"},
    "current_income": {"type": "currency"},
    "income_net_of_super": {"type": "currency"},
    "after_tax_income": {"type": "currency"},
    "retirement_balance": {"type": "currency"},
    "retirement_income": {"type": "currency"},
    "cash_assets": {"type": "currency"},
    "share_investments": {"type": "currency"},
    "investment_properties": {"type": "currency"},
    "non_financial_assets": {"type": "currency"},
    
    # String enum variables
    "relationship_status": {"type": "enum", "values": ["single", "couple"]},
    "retirement_income_option": {"type": "enum", 
                               "values": ["same_as_current", "modest_single", "modest_couple", 
                                         "comfortable_single", "comfortable_couple", "custom"]},
    
    # String variables (no conversion needed)
    "current_fund": {"type": "string"},
    "nominated_fund": {"type": "string"}
}

def convert_variable_type(variable_name, value):
    """
    Convert a variable to its correct type based on the VARIABLE_TYPE_MAP.
    
    Args:
        variable_name: The name of the variable
        value: The raw value to convert
        
    Returns:
        The converted value with the correct type
    """
    if value is None:
        return None
        
    # Get type info from the map
    type_info = VARIABLE_TYPE_MAP.get(variable_name)
    if not type_info:
        return value  # No conversion info available
    
    var_type = type_info.get("type")
    
    # Handle different types
    if var_type == "boolean":
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            value_lower = value.lower().strip()
            # Check true values
            for true_value in type_info.get("true_values", []):
                if true_value in value_lower:
                    return True
            # Check false values
            for false_value in type_info.get("false_values", []):
                if false_value in value_lower:
                    return False
            # Default to None if unclear
            return None
    
    elif var_type == "integer":
        try:
            if isinstance(value, str):
                # Remove any non-numeric characters except decimals
                clean_value = ''.join(c for c in value if c.isdigit() or c == '.')
                return int(float(clean_value))
            elif isinstance(value, (int, float)):
                return int(value)
        except (ValueError, TypeError):
            return None
    
    elif var_type == "currency":
        try:
            if isinstance(value, str):
                # Remove currency symbols and commas
                clean_value = value.replace('$', '').replace(',', '').strip().lower()
                
                # Handle suffixes
                if clean_value.endswith('k'):
                    return float(clean_value[:-1]) * 1000
                elif clean_value.endswith('m'):
                    return float(clean_value[:-1]) * 1000000
                else:
                    return float(clean_value)
            elif isinstance(value, (int, float)):
                return float(value)
        except (ValueError, TypeError):
            return None
    
    elif var_type == "enum":
        if isinstance(value, str):
            value_lower = value.lower().strip()
            valid_values = type_info.get("values", [])
            
            # Exact match
            if value_lower in valid_values:
                return value_lower
                
            # Partial match
            for valid_value in valid_values:
                if valid_value in value_lower or value_lower in valid_value:
                    return valid_value
        
        # If no match, return original
        return value
    
    # Default: return original value
    return value

def filter_dataframe_by_fund_name(df, fund_name, exact_match=False):
    """
    Safely filter a DataFrame by fund name, handling special characters properly.
    """
    print(f"DEBUG filter_dataframe_by_fund_name: Filtering for '{fund_name}', exact_match={exact_match}")
    
    if exact_match:
        # For exact matching, use straight equality (this handles special characters correctly)
        return df[df["FundName"] == fund_name]
    else:
        # For contains matching, escape any regex special characters first
        import re
        escaped_fund_name = re.escape(fund_name)
        return df[df["FundName"].str.contains(escaped_fund_name, case=False, na=False)]

def match_fund_name(input_fund: str, df) -> str:
    """Use LLM to match user's fund input to the actual fund name in the database."""
    print(f"DEBUG utils.py: Entering match_fund_name with input: {input_fund}")
    
    # Get unique fund names from the DataFrame
    fund_names = df['FundName'].unique().tolist()
    print(f"DEBUG utils.py: Available fund names: {fund_names}")
    fund_names_str = "\n".join(fund_names)
    
    system_prompt = (
        "You are a superannuation fund name matcher. Given a user's input and a list of "
        "available fund names, find the best matching fund. Consider abbreviations, common names, "
        "and variations. Return EXACTLY the matching fund name from the list, or 'None' if no match found.\n\n"
        "For example:\n"
        "- 'ART Super' should match 'Australian Retirement Trust (ART)'\n"
        "- 'Aussie Super' should match 'AustralianSuper'\n"
        "- 'Colonial' should match 'Colonial First State FirstChoice'"
    )
    
    user_prompt = f"""Available fund names:
{fund_names_str}
User input: {input_fund}
Return the exact matching fund name from the list, or 'None' if no match found."""

    # Get OpenAI API key from environment variable
    client = OpenAI()
        
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0
    )
    
    matched_name = response.choices[0].message.content.strip()
    matched_name = matched_name.strip("'\"")
    print(f"DEBUG: Fund name matcher - Input: {input_fund}, Matched: {matched_name}")
    if matched_name == 'None' or matched_name not in fund_names:
        return None
    return matched_name

def parse_age_from_query(query: str) -> int:
    match = re.search(r"(\d+)\s*year", query.lower())
    if match:
        print(f"DEBUG: parse_age_from_query found age='{match.group(1)}'")
        return int(match.group(1))
    return 0

def parse_balance_from_query(query: str) -> float:
    matches = re.findall(r"(\d[\d,\.]*[kKmM]?)", query)
    best_val = 0.0
    for raw in matches:
        multiplier = 1
        if raw.lower().endswith("k"):
            multiplier = 1000
            raw = raw[:-1]
        elif raw.lower().endswith("m"):
            multiplier = 1000000
            raw = raw[:-1]
        cleaned = re.sub(r"[^0-9\.]", "", raw)
        if not cleaned:
            continue
        try:
            val = float(cleaned) * multiplier
            if val > best_val:
                best_val = val
        except ValueError:
            pass
    print(f"DEBUG: parse_balance_from_query returning best_val={best_val}")
    return best_val

def parse_admin_fee_json(json_string: str):
    try:
        tiers = json.loads(json_string)
        tiers.sort(key=lambda t: t["min_bal"])
        return tiers
    except Exception as e:
        print(f"DEBUG: parse_admin_fee_json error: {e}")
        return []

def compute_tiered_admin_fee(tiers, balance: float) -> float:
    admin_fee_dollars = 0.0
    for tier in tiers:
        if balance <= tier["min_bal"]:
            break
        applicable_balance = min(balance, tier["max_bal"]) - tier["min_bal"]
        if applicable_balance < 0:
            applicable_balance = 0
        admin_fee_dollars += applicable_balance * (tier["rate"] / 100.0)
    return admin_fee_dollars

def compute_fee_breakdown(row: pd.Series, balance: float) -> dict:
    # Investment fee
    inv_str = str(row["InvestmentFee"]).replace("%", "").strip()
    investment_rate = float(inv_str)
    investment_fee = balance * (investment_rate / 100.0)

    # Administration fee via tiered approach
    admin_fee_json = str(row["AdminFee"])
    tiers = parse_admin_fee_json(admin_fee_json)
    admin_fee = compute_tiered_admin_fee(tiers, balance)
    print(f"DEBUG: For fund={row['FundName']}, computed admin_fee={admin_fee}")

    # Member fee (fixed fee)
    member_str = str(row["MemberFee"]).replace("$", "").strip()
    try:
        member_fee = float(member_str)
    except ValueError:
        member_fee = 0.0

    total_fee = investment_fee + admin_fee + member_fee
    print(f"DEBUG: For fund={row['FundName']}, investment_fee={investment_fee}, member_fee={member_fee}, total_fee={total_fee}")
    
    return {
        "investment_fee": investment_fee,
        "admin_fee": admin_fee,
        "member_fee": member_fee,
        "total_fee": total_fee
    }

def find_applicable_funds(df: pd.DataFrame, user_age: int):
    """Find applicable funds based on age, with smart fund name matching."""
    print(f"DEBUG utils.py: Entering find_applicable_funds with dataframe of {len(df)} rows")
    print(f"DEBUG utils.py: First few fund names in df: {df['FundName'].head().tolist()}")
    
    # If this is a filtered dataframe (i.e., searching for a specific fund)
    original_df_size = len(df.copy())
    is_filtered = len(df) < original_df_size
    print(f"DEBUG utils.py: Is filtered dataframe: {is_filtered}")
    
    # For fee comparison, when we're already filtering by fund name,
    # just return the dataframe as is if it's not empty
    if is_filtered and not df.empty:
        print("DEBUG utils.py: Already filtered by fund name and not empty, returning as is")
        # Check if there's already an exact age match
        df["ApproachType"] = df["ApproachType"].fillna("").astype(str)
        age_match = df[(df["ApproachType"].str.upper() == "AGE") & 
                      (df["AgeMin"].astype(float) <= user_age) & 
                      (df["AgeMax"].astype(float) >= user_age)]
        
        if not age_match.empty:
            print("DEBUG utils.py: Found age match in filtered data, returning that")
            return age_match
        else:
            print("DEBUG utils.py: No age match in filtered data, returning first row")
            return df.head(1)
    
    # Ensure ApproachType is string
    df["ApproachType"] = df["ApproachType"].fillna("").astype(str)
    sub = df[df["ApproachType"].str.upper() == "AGE"].copy()
    print(f"DEBUG utils.py: After AGE approach filter, df has {len(sub)} rows")
    
    # Try to find an exact match for age
    matches = sub[(sub["AgeMin"].astype(float) <= user_age) & (sub["AgeMax"].astype(float) >= user_age)]
    print(f"DEBUG utils.py: After age range filter, found {len(matches)} matches")
    
    # If no matches found and we're not doing a fund name search, try a broader approach
    if matches.empty and not is_filtered:
        # For general search, try returning all funds with default values
        default_funds = df[df["ApproachType"].str.upper() == "AGE"].drop_duplicates(subset=["FundName"])
        if not default_funds.empty:
            print(f"DEBUG utils.py: No age matches, returning {len(default_funds)} default funds")
            return default_funds
    
    return matches

def retrieve_relevant_context(query, text_corpus, top_k=1):
    paragraphs = text_corpus.split("\n\n")
    scores = []
    query_words = set(query.lower().split())
    for paragraph in paragraphs:
        paragraph_words = set(paragraph.lower().split())
        overlap = len(query_words.intersection(paragraph_words))
        scores.append((overlap, paragraph))
    scores.sort(key=lambda x: x[0], reverse=True)
    top_paragraphs = [p for _, p in scores[:top_k]]
    return "\n".join(top_paragraphs)

def determine_intent(query: str) -> str:
    """
    Basic intent detection based on keywords.
    Returns one of:
      "compare_fees", "rank_fees", "project_balance", 
      "retirement_income", "find_cheapest", or "unknown"
    """
    query_lower = query.lower()
    if "compare fees" in query_lower or "compare" in query_lower:
        return "compare_fees"
    elif "rank" in query_lower:
        return "rank_fees"
    elif "project" in query_lower or "growth" in query_lower:
        return "project_balance"
    elif "income" in query_lower or "drawdown" in query_lower:
        return "retirement_income"
    elif "cheapest" in query_lower or "lowest fee" in query_lower:
        return "find_cheapest"
    else:
        return "unknown"

def find_cheapest_superfund(df: pd.DataFrame, balance: float, investment_needs: str = None, insurance_needs: str = None) -> dict:
    """
    Compares all funds in the provided DataFrame and returns the cheapest fund based on total fees.
    Returns a dictionary with:
      - 'fund_name': Name of the cheapest fund.
      - 'total_fee': Total fee in dollars.
      - 'num_funds': Total number of funds compared.
      - 'fee_percentage': The fee as a percentage of the given balance.
    """
    fees = []
    for idx, row in df.iterrows():
        breakdown = compute_fee_breakdown(row, balance)
        total_fee = breakdown.get("total_fee", 0.0)
        fees.append((row["FundName"], total_fee))
    
    if not fees:
        return {"error": "No funds found."}
    
    # Sort funds by total fee (lowest first)
    fees.sort(key=lambda x: x[1])
    cheapest_fund = fees[0]
    fee_percentage = (cheapest_fund[1] / balance) * 100 if balance > 0 else 0.0
    
    result = {
        "fund_name": cheapest_fund[0],
        "total_fee": cheapest_fund[1],
        "num_funds": len(fees),
        "fee_percentage": fee_percentage
    }
    return result

def project_super_balance(current_age: int, retirement_age: int, current_balance: float, income_net_of_super: float,
                          wage_growth: float, employer_contribution_rate: float, investment_return: float,
                          inflation_rate: float, current_fund_row: pd.Series) -> float:
    """
    Projects the superannuation balance at retirement on a monthly basis.
    
    Args:
        current_age: Current age
        retirement_age: Target retirement age
        current_balance: Current super balance
        income_net_of_super: Current annual income excluding super (starting salary)
        wage_growth: Annual wage growth rate (percentage)
        employer_contribution_rate: Employer contribution rate (percentage)
        investment_return: Expected annual investment return (percentage)
        inflation_rate: Expected annual inflation rate (percentage)
        current_fund_row: DataFrame row containing fund fee structure
        
    Note:
        Default economic assumptions are defined in backend/constants.py and can be imported from there.
    """
    total_months = (retirement_age - current_age) * 12
    balance = current_balance
    
    print(f"Initial values:")
    print(f"  Starting balance: ${balance:,.2f}")
    print(f"  Starting annual salary: ${income_net_of_super:,.2f}")
    print(f"  Employer contribution rate: {employer_contribution_rate}%")
    print(f"  Annual wage growth rate: {wage_growth}%")
    print("--------------------------------------------------")

    # Calculate net monthly investment return
    net_annual_return = investment_return - inflation_rate
    net_monthly_return = (1 + net_annual_return / 100) ** (1/12) - 1

    for month in range(1, total_months + 1):
        # Calculate the year we're in (0-based)
        year = (month - 1) // 12
        
        # Calculate current annual salary with compound growth
        current_annual_salary = income_net_of_super * ((1 + wage_growth/100) ** year)
        
        # Calculate monthly contribution from current annual salary after 15% contributions tax
        monthly_contribution = (current_annual_salary * employer_contribution_rate / 100) * 0.85 / 12
        
        # Store previous balance for logging
        previous_balance = balance
        
        # Recalculate fees based on current balance
        breakdown = compute_fee_breakdown(current_fund_row, balance)
        monthly_fee = breakdown.get("total_fee", 0.0) / 12.0
        
        # Update balance with contribution, fee, and returns
        balance = (balance + monthly_contribution - monthly_fee) * (1 + net_monthly_return)
        
        # Debug prints
        print(f"Month {month}:")
        print(f"  Previous balance: ${previous_balance:,.2f}")
        print(f"  Monthly contribution: ${monthly_contribution:,.2f}")
        print(f"  Annual fee: ${breakdown.get('total_fee', 0.0):,.2f}")
        print(f"  Monthly fee: ${monthly_fee:,.2f}")
        print(f"  Current annual salary: ${current_annual_salary:,.2f}")
        print(f"  Investment return: {investment_return:.2f}%")
        print(f"  Inflation rate: {inflation_rate:.2f}%")
        print(f"  Net annual return: {net_annual_return:.2f}%")
        print(f"  Net monthly return: {net_monthly_return*100:.4f}%")
        print(f"  Updated balance: ${balance:,.2f}")
        print("--------------------------------------------------")
    
    return balance

def calculate_retirement_drawdown(retirement_balance: float, retirement_age: int, annual_income: float, 
                                 investment_return: float, inflation_rate: float, current_fund_row: pd.Series = None) -> int:
    """
    Calculate when retirement savings will be depleted, given a retirement balance,
    annual income drawdown, and investment returns.
    
    Args:
        retirement_balance: Balance at retirement
        retirement_age: Age at retirement
        annual_income: Annual income desired in retirement
        investment_return: Expected annual investment return (percentage)
        inflation_rate: Expected annual inflation rate (percentage)
        current_fund_row: DataFrame row containing fund fee structure
        
    Returns:
        Age at which retirement savings will be depleted
    """
    # Convert annual rates to monthly
    net_annual_return = investment_return - inflation_rate
    net_monthly_return = (1 + net_annual_return / 100) ** (1/12) - 1
    monthly_income = annual_income / 12
    
    balance = retirement_balance
    current_age = retirement_age
    months = 0
    
    print(f"Initial values for drawdown calculation:")
    print(f"  Starting balance: ${balance:,.2f}")
    print(f"  Monthly income: ${monthly_income:,.2f}")
    print(f"  Net annual return: {net_annual_return:.2f}%")
    print(f"  Net monthly return: {net_monthly_return*100:.4f}%")
    print("--------------------------------------------------")
    
    while balance > 0 and months < 1200:  # Cap at 100 years (1200 months) to prevent infinite loops
        # Calculate fees if fund information is provided
        monthly_fee = 0
        if current_fund_row is not None:
            fee_breakdown = compute_fee_breakdown(current_fund_row, balance)
            monthly_fee = fee_breakdown.get("total_fee", 0.0) / 12.0
            
        # Calculate investment growth
        investment_growth = balance * net_monthly_return

        # Update balance with investment growth, fees, and income drawdown
        balance = balance + investment_growth - monthly_fee - monthly_income
        
        months += 1
        
        if months % 12 == 0:  # Log every year
            years = months // 12
            current_age = retirement_age + years
            print(f"After {years} years (age {current_age}):")
            print(f"  Remaining balance: ${balance:,.2f}")
            if current_fund_row is not None:
                print(f"  Monthly fee: ${monthly_fee:.2f}")
            print("--------------------------------------------------")        

        if balance <= 0:
            break
    
    # Calculate final age (whole years)
    depletion_age = retirement_age + (months // 12)
    
    # If we hit our cap, return a special value
    if months >= 1200:
        return 200  # Special value indicating funds won't run out in a normal lifetime
    
    return depletion_age

def get_asfa_standards() -> dict:
    """
    Returns the ASFA Retirement Standards with descriptions.
    These are the current standards as of March 2025.
    """
    return {
        "modest_single": {
            "annual_amount": 32000,
            "description": "Basic activities and limited leisure, simple housing and healthcare"
        },
        "modest_couple": {
            "annual_amount": 46000,
            "description": "Basic needs and limited leisure for couples, simple housing and healthcare"
        },
        "comfortable_single": {
            "annual_amount": 52000,
            "description": "Good standard of living with private health insurance, leisure activities, and newer cars"
        },
        "comfortable_couple": {
            "annual_amount": 75000,
            "description": "Good standard of living for couples with private health insurance, more leisure activities, and newer cars"
        }
    }

def calculate_age_pension(
    relationship_status: str,  # "single" or "couple"
    homeowner_status: bool,    # True for homeowner, False for non-homeowner
    total_assets: float,       # Total assets excluding principal residence if homeowner
    current_income: float,     # Employment income (not deemed)
    financial_assets: float    # Financial assets for deeming (cash, investments, super)
) -> dict:
    """
    Calculate Australian Age Pension based on assets test and income test.
    Returns both tests results and the lower amount (which is what gets paid).
    All monetary amounts are in annual terms.
    """
    from backend.constants import age_pension_params
    
    # Convert to fortnightly amounts for calculations
    max_pension = age_pension_params["MAX_PENSION_SINGLE"] if relationship_status == "single" else age_pension_params["MAX_PENSION_COUPLE"]
    max_pension_fortnight = max_pension / 26
    current_income_fortnight = current_income / 26  # Changed from other_income
    
    # Determine assets thresholds based on relationship and homeowner status
    if relationship_status == "single":
        if homeowner_status:
            assets_threshold = age_pension_params["ASSETS_THRESHOLD_HOMEOWNER_SINGLE"]
        else:
            assets_threshold = age_pension_params["ASSETS_THRESHOLD_NON_HOMEOWNER_SINGLE"]
    else:  # couple
        if homeowner_status:
            assets_threshold = age_pension_params["ASSETS_THRESHOLD_HOMEOWNER_COUPLE"]
        else:
            assets_threshold = age_pension_params["ASSETS_THRESHOLD_NON_HOMEOWNER_COUPLE"]
    
    # Calculate deemed income
    if relationship_status == "single":
        deeming_threshold = age_pension_params["DEEMING_THRESHOLD_SINGLE"]
    else:
        deeming_threshold = age_pension_params["DEEMING_THRESHOLD_COUPLE"]
    
    if financial_assets <= deeming_threshold:
        deemed_income = financial_assets * age_pension_params["DEEMING_RATE_LOWER"]
    else:
        deemed_income = (deeming_threshold * age_pension_params["DEEMING_RATE_LOWER"]) + \
                        ((financial_assets - deeming_threshold) * age_pension_params["DEEMING_RATE_HIGHER"])
    
    # Convert deemed income to fortnightly
    deemed_income_fortnight = deemed_income / 26
    
    # Total assessable income (fortnightly)
    total_income_fortnight = current_income_fortnight + deemed_income_fortnight
    
    # Income test
    income_threshold = age_pension_params["INCOME_THRESHOLD_SINGLE"] if relationship_status == "single" else age_pension_params["INCOME_THRESHOLD_COUPLE"]
    
    if total_income_fortnight <= income_threshold:
        income_test_pension = max_pension_fortnight
    else:
        reduction = (total_income_fortnight - income_threshold) * age_pension_params["INCOME_TAPER_RATE"]
        income_test_pension = max(0, max_pension_fortnight - reduction)
    
    # Assets test
    if total_assets <= assets_threshold:
        assets_test_pension = max_pension_fortnight
    else:
        reduction = (total_assets - assets_threshold) * age_pension_params["ASSETS_TAPER_RATE"]
        assets_test_pension = max(0, max_pension_fortnight - reduction)
    
    # The lower of the two tests applies
    pension_fortnight = min(income_test_pension, assets_test_pension)
    annual_pension = pension_fortnight * 26
    
    return {
        "annual_pension": annual_pension,
        "fortnightly_pension": pension_fortnight,
        "income_test_pension_annual": income_test_pension * 26,
        "assets_test_pension_annual": assets_test_pension * 26,
        "determining_test": "income" if income_test_pension <= assets_test_pension else "assets",
        "deemed_income_annual": deemed_income,
        "max_pension_annual": max_pension
    }