# backend/utils.py
import re
import json
import pandas as pd
import openai
from openai import OpenAI

def filter_dataframe_by_fund_name(df, fund_name, exact_match=False):
    """
    Safely filter a DataFrame by fund name, handling special characters properly.
    
    Args:
        df: DataFrame to filter
        fund_name: The fund name to search for
        exact_match: If True, use exact matching; if False, use contains with escaped characters
        
    Returns:
        Filtered DataFrame
    """
    import re
    
    if exact_match:
        return df[df["FundName"] == fund_name]
    else:
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
    is_filtered = len(df) < len(df.copy())
    print(f"DEBUG utils.py: Is filtered dataframe: {is_filtered}")
    
    if is_filtered:
        fund_name = df.iloc[0]['FundName'] if not df.empty else None
        print(f"DEBUG utils.py: Working with filtered df, fund_name: {fund_name}")
        if fund_name:
            matched_fund = match_fund_name(fund_name, df.copy())
            print(f"DEBUG utils.py: After matching, matched_fund: {matched_fund}")
            if matched_fund is None:
                print("DEBUG utils.py: No match found, returning empty DataFrame")
                return pd.DataFrame()
            df = df[df['FundName'] == matched_fund]
            print(f"DEBUG utils.py: After filtering for matched fund, df has {len(df)} rows")
    
    # Ensure ApproachType is string
    df["ApproachType"] = df["ApproachType"].fillna("").astype(str)
    sub = df[df["ApproachType"].str.upper() == "AGE"].copy()
    print(f"DEBUG utils.py: After AGE approach filter, df has {len(sub)} rows")
    
    matches = sub[(sub["AgeMin"].astype(float) <= user_age) & (sub["AgeMax"].astype(float) >= user_age)]
    print(f"DEBUG utils.py: After age range filter, found {len(matches)} matches")
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

def project_super_balance(current_age: int, retirement_age: int, current_balance: float, current_income: float,
                          wage_growth: float, employer_contribution_rate: float, investment_return: float,
                          inflation_rate: float, current_fund_row: pd.Series) -> float:
    """
    Projects the superannuation balance at retirement on a monthly basis.
    
    Args:
        current_age: Current age
        retirement_age: Target retirement age
        current_balance: Current super balance
        current_income: Current annual income (starting salary)
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
    print(f"  Starting annual salary: ${current_income:,.2f}")
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
        current_annual_salary = current_income * ((1 + wage_growth/100) ** year)
        
        # Calculate monthly contribution from current annual salary
        monthly_contribution = (current_annual_salary * employer_contribution_rate / 100) / 12
        
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
