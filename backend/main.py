import os
import re
import openai
import pandas as pd
from backend.constants import economic_assumptions
from typing import Union, Tuple
from openai import OpenAI
from backend.charts import generate_fee_bar_chart
from backend.cashflow import calculate_income_net_of_super, calculate_after_tax_income
from backend.utils import (
    parse_age_from_query,
    parse_balance_from_query,
    compute_fee_breakdown,
    find_applicable_funds,
    retrieve_relevant_context,
    determine_intent,
    find_cheapest_superfund,
    project_super_balance,
    match_fund_name,
    filter_dataframe_by_fund_name,
    calculate_retirement_drawdown, 
    get_asfa_standards 
)

from backend.helper import (
    extract_intent_variables, 
    get_unified_variable_response, 
    ask_llm, 
    update_calculated_values,
    get_next_intent_info,
    handle_next_intent_transition,
    is_affirmative_response
)

# System prompts for LLM
SYSTEM_PROMPTS = {
    "intent_acknowledgment": """
        You are a friendly financial expert helping Australian consumers understand their money issues.
        Create a very brief, warm acknowledgment of what the user wants to know.
        Keep it short. Be conversational but concise.
        Examples:
        - For project_balance: Figuring out what you might retire with in super can be tricky. I'll try to keep this as simple as possible.
        - For compare_fees_nominated: Sure thing. Happy to show you how these funds compare.
        - For find_cheapest: No problems. Let's find which fund is cheapest for you based on your details.
        - For compare_fees_all: Happy to help. I'll analyze how your fund's fees compare to others.
    """,
    
    "unified_message": """
        You are a friendly, professional financial expert helping Australian consumers understand their money issues.
        Your responses must be CONCISE and CLEAR - get straight to the point while maintaining a warm tone.
        The user should immediately understand what information you need.
        Never use the same phrasing twice for requests.
        Examples of good, concise responses:
        - Can you please tell me, what's your current annual income?
        - When do you think you'd like to retire?
        - And what's your super balance?
        - Which super fund are you with?
    """,
    
    "fee_comparison": """
        You are a financial guru specializing in financial products in the Australian market - superfunds, insurance, investment accounts, etc.
        Based solely on the fee information provided (do not reference performance data),
        compare the fees between the funds. Explain which fee components contribute most to the differences.
        Be concise and clear in your response.
    """
}

# Check for OpenAI API key
if not os.environ.get("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable is not set")

def clean_response(response: str) -> str:
    # Remove leading and trailing single or double quotes
    return response.strip('\'"')

# Add the helper function here
def parse_numeric_with_suffix(value_str: str) -> float:
    """Parse numeric values that might include k/m suffixes."""
    # Remove any commas and spaces
    value_str = value_str.replace(",", "").strip().lower()
    # Match number and optional suffix
    match = re.match(r'^([\d.]+)([km])?$', value_str)
    if not match:
        return 0
    
    number = float(match.group(1))
    suffix = match.group(2)
    
    if suffix == 'k':
        number *= 1000
    elif suffix == 'm':
        number *= 1000000
        
    return number

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Load your CSV into a global variable 'df'
df = pd.read_csv(
    "superfunds.csv",
    header=0,
    sep=",",
    quotechar='"',
    skipinitialspace=True,
    index_col=False,
    engine="python"
)

def validate_response(var_name: str, user_message: str, context: dict) -> Tuple[bool, Union[float, str, None]]:
    """Validate user response for a specific variable and return (is_valid, parsed_value)"""
    try:
        if var_name in ["current income", "age", "super balance", "desired retirement age"]:
            value = parse_numeric_with_suffix(user_message)
            
            # Specific validation rules
            if var_name == "age" and (value < 15 or value > 100):
                return False, None
            if var_name == "desired retirement age":
                current_age = context.get("current_age", 0)
                if value <= current_age or value > 100:
                    return False, None
            if var_name in ["current income", "super balance"] and value < 0:
                return False, None
                
            return (value > 0), value
        else:
            # For non-numeric variables like fund names
            return True, user_message.strip()
    except Exception:
        return False, None

async def get_clarification_prompt(var_name: str, user_message: str, context: dict) -> str:
    # Debug prints to trace execution and inputs:
    print("DEBUG get_clarification_prompt: Entering function")
    print(f"DEBUG get_clarification_prompt: var_name = {var_name}")
    print(f"DEBUG get_clarification_prompt: user_message = '{user_message}'")
    print(f"DEBUG get_clarification_prompt: context = {context}")
    
    """Generate a friendly clarification request using LLM"""
    system_prompt = (
        "You are a friendly financial advisor seeking clarification on unclear information. "
        "Keep your response CONCISE and CLEAR while maintaining a helpful tone. "
        "Explain briefly what was unclear and what you need instead. "
        "Limit your response to 1-2 short sentences.\n\n"
        "Examples of good responses:\n"
        "- I didn't catch your age there. Could you provide it as a number?\n"
        "- That retirement age seems unusual. Please confirm your intended retirement age.\n"
        "- I need your annual income as a number, like 80000 or 80k."
    )
    
    user_prompt = f"""
    Variable we need: {var_name}
    User's response: {user_message}
    Current context: {context}
    
    Generate a CONCISE clarification request that:
    1. Briefly indicates why their response wasn't clear
    2. Explains what format you need
    3. Keeps a warm, helpful tone
    
    Keep it to one or two short sentences maximum.
    """
    result = await ask_llm(system_prompt, user_prompt)
    print("DEBUG get_clarification_prompt: LLM returned:", result)
    return result
    
def get_intent_acknowledgment(intent: str, user_query: str) -> str:
    """
    # This function has been replaced by get_unified_variable_response in helper.py
    # Keeping code commented for reference
    """
    return ""
    """
    system_prompt = (
        "You are a friendly financial expert helping Australian consumers understand their money issues."
        "Create a very brief, warm acknowledgment of what the user wants to know. "
        "Keep it short. Be conversational but concise.\n\n"
        "Examples:\n"
        "- For project_balance: Figuring out what you might retire with in super can be tricky. I'll try to keep this as simple as possible.\n"
        "- For compare_fees_nominated: Sure thing. Happy to show you how these funds compare.\n"
        "- For find_cheapest: No problems. Let's find which fund is cheapest for you based on your details.\n"
        "- For compare_fees_all: Happy to help. I'll analyze how your fund's fees compare to others."
    )
    
    user_prompt = f\"\"\"
    User's intent: {intent}
    Their query: {user_query}
    
    Generate a brief, friendly acknowledgment of what they want to know.
    Keep it short, and conversational.
    \"\"\"
    
    return ask_llm(system_prompt, user_prompt)
    """

async def process_compare_fees_nominated(context: dict) -> str:
    """Process compare_fees_nominated intent with the given context."""
    current_fund = context["current_fund"]
    nominated_fund = context["nominated_fund"]
    user_age = context["current_age"]
    user_balance = context["current_balance"]

    # First use the fund matcher to get exact names
    current_fund_match = match_fund_name(current_fund, df)
    nominated_fund_match = match_fund_name(nominated_fund, df)
    
    # Fix for quoted strings or other issues
    if isinstance(current_fund_match, str):
        current_fund_match = current_fund_match.strip("'\"")
    if isinstance(nominated_fund_match, str):
        nominated_fund_match = nominated_fund_match.strip("'\"")
    
    print(f"DEBUG main.py: After cleaning - current_fund_match: {current_fund_match}, nominated_fund_match: {nominated_fund_match}")
    
    if not current_fund_match or not nominated_fund_match:
        return f"Could not find one or both funds: {current_fund}, {nominated_fund}"        
    
    # Find applicable funds
    current_rows = find_applicable_funds(filter_dataframe_by_fund_name(df, current_fund_match), user_age)
    nominated_rows = find_applicable_funds(filter_dataframe_by_fund_name(df, nominated_fund_match), user_age)
    
    if current_rows.empty:
        return f"Could not find applicable fee data for your current fund: {current_fund}."
    if nominated_rows.empty:
        return f"Could not find applicable fee data for the nominated fund: {nominated_fund}."
    
    current_breakdown = compute_fee_breakdown(current_rows.iloc[0], user_balance)
    nominated_breakdown = compute_fee_breakdown(nominated_rows.iloc[0], user_balance)
    
    next_intent, suggestion_prompt = get_next_intent_info("compare_fees_nominated")
    context.setdefault('data', {})['suggested_next_intent'] = next_intent

    user_prompt = (
        f"Data: Your current fund ({current_fund}) has total annual fees of "
        f"${current_breakdown['total_fee']:,.2f} ({(current_breakdown['total_fee']/user_balance)*100:.2f}% of your balance). "
        f"The nominated fund ({nominated_fund}) has total annual fees of "
        f"${nominated_breakdown['total_fee']:,.2f} ({(nominated_breakdown['total_fee']/user_balance)*100:.2f}% of your balance)."
        f"Suggestion prompt: {suggestion_prompt}"
    )
    system_prompt = (
        "You are a financial guru that calculates total superannuation fees for Australian consumers. "
        "Based solely on the fee information provided (do not reference performance data), "
        "compare the fees between the user's current fund and the nominated fund. "
        "Explain which fee components (investment, admin, member) contribute most to any differences, "
        "and respond EXACTLY in the following format:\n\n"
        "Comparing your [CURRENT FUND] fund and [NOMINATED FUND], your fund charges [X]% of your account balance while [NOMINATED FUND] charges [X]%, "
        "primarily due to differences in [FEE COMPONENTS].\n\n"
        "Final paragraph: Use exactly the suggestion prompt provided in the data to ask about the next steps. "
        "Do not modify the suggestion prompt text.\n\n"
        "Do not include any extra commentary."
    )
    return await ask_llm(system_prompt, user_prompt)

async def process_compare_fees_all(context: dict) -> str:
    """Process compare_fees_all intent with the given context."""
    user_age = context["current_age"]
    user_balance = context["current_balance"]
    current_fund = context["current_fund"]
    
    matched_rows = find_applicable_funds(df, user_age)
    if matched_rows.empty:
        return "No applicable funds found for your age."
    
    fees = []
    for idx, row in matched_rows.iterrows():
        breakdown = compute_fee_breakdown(row, user_balance)
        total_fee = float(breakdown["total_fee"])
        fees.append((row["FundName"], total_fee))
    fees.sort(key=lambda x: x[1])
    
    cheapest = fees[0]
    expensive = fees[-1]  # Last in sorted order (highest fee)
    num_funds = len(fees)
    
    current_rank = None
    if current_fund:
        for i, (fund_name, fee) in enumerate(fees, start=1):
            # Use case-insensitive substring matching for rank determination
            if current_fund.lower() in fund_name.lower() or fund_name.lower() in current_fund.lower():
                current_rank = i
                break
    if not current_rank:
        current_rank = "undetermined"
    
    cheapest_percentage = (cheapest[1] / user_balance) * 100 if user_balance > 0 else 0.0
    expensive_percentage = (expensive[1] / user_balance) * 100 if user_balance > 0 else 0.0
    current_percentage = None
    if current_rank != "undetermined":
        # Find the fee for the current fund.
        for fund_name, fee in fees:
            if current_fund.lower() in fund_name.lower():
                current_percentage = (fee / user_balance) * 100
                break
    if current_percentage is None:
        current_percentage = 0.0
    
    next_intent, suggestion_prompt = get_next_intent_info("compare_fees_all")
    context.setdefault('data', {})['suggested_next_intent'] = next_intent

    user_prompt = (
        f"Data:\n"
        f"Number of funds compared: {num_funds}\n"
        f"Cheapest fund: {cheapest[0]} with an annual fee of ${cheapest[1]:,.2f} "
        f"({cheapest_percentage:.2f}% of your balance)\n"
        f"Most expensive fund: {expensive[0]} with an annual fee of ${expensive[1]:,.2f} "
        f"({expensive_percentage:.2f}% of your balance)\n"
        f"Your current fund: {current_fund if current_fund else 'N/A'} which ranks {current_rank} "
        f"among the {num_funds} funds, representing {current_percentage:.2f}% of your balance.\n"
        f"Suggestion prompt: {suggestion_prompt}\n"
        "Please use the data above."
    )
    
    system_prompt = (
        "You are a financial guru specializing in superannuation fees. "
        "Using only the fee data provided below, produce a response EXACTLY in the following format with no additional commentary:\n\n"
        "Of the [n] funds compared, [cheapest fund name] is the cheapest, with an annual fee of $[total annual fee] "
        "which is [percentage of account balance]% of your current account balance.\n\n"
        "The most expensive is [expensive fund name], with an annual fee of $[total annual fee] which is "
        "[percentage of account balance]% of your current account balance.\n\n"
        "Your account with [current fund name] ranks [ranking] among the [n] funds assessed. This represents "
        "[percentage of account balance]% of your current account balance.\n\n"
        "Then, provide a single concise sentence describing the major cause of the fee difference between your current fund "
        "and the cheapest fund (for example, whether the difference is primarily due to a higher admin fee, investment fee, or member fee)."
        "Do not modify the suggestion prompt text."
    )
    
    # Get the text response from the LLM
    llm_answer = await ask_llm(system_prompt, user_prompt)
    print(f"DEBUG main.py: Generated LLM answer, length: {len(llm_answer)}")
    
    try:
        # Import the chart generation function from backend.charts
        from backend.charts import generate_fee_bar_chart
        
        # Generate the chart HTML
        chart_html = generate_fee_bar_chart(fees)
        print(f"DEBUG main.py: Generated chart, HTML length: {len(chart_html)}")
        
        # Return combined response with text above and chart below
        final_response = f"{llm_answer}\n\n{chart_html}"
        return final_response
    except Exception as e:
        print(f"DEBUG main.py: Error generating chart: {e}")
        # Return just the text response if chart generation fails
        return llm_answer
    
async def process_find_cheapest(context: dict) -> str:
    """Process find_cheapest intent with the given context."""
    try:
        user_age = context.get("current_age", 0)
        user_balance = context.get("current_balance", 0)
        
        matched_rows = find_applicable_funds(df, user_age)
        if matched_rows.empty:
            return "No applicable funds found for your age."
        
        fees = []
        for idx, row in matched_rows.iterrows():
            breakdown = compute_fee_breakdown(row, user_balance)
            fees.append((row["FundName"], breakdown["total_fee"]))
        fees.sort(key=lambda x: x[1])
        
        cheapest = fees[0]
        num_funds = len(fees)
        fee_percentage = (cheapest[1] / user_balance) * 100 if user_balance > 0 else 0.0
    
        next_intent, suggestion_prompt = get_next_intent_info("find_cheapest")
        print(f"DEBUG process_find_cheapest: Setting suggested_next_intent to {next_intent}")
        context.setdefault('data', {})['suggested_next_intent'] = next_intent
        print(f"DEBUG process_find_cheapest: Context data after setting: {context.get('data')}")
        # Check if 'data' key exists, if not create it
        if 'data' not in context:
            context['data'] = {}
        
        # Store the nominated fund
        context['data']['nominated_fund'] = cheapest[0]  # Store the cheapest fund as nominated fund

        print(f"DEBUG process_find_cheapest: Final state of context: {context}")

        user_prompt = (
            f"Data: {num_funds} funds compared; Cheapest fund: {cheapest[0]}; "
            f"Annual fee: ${cheapest[1]:,.2f}; Fee percentage: {fee_percentage:.2f}%.\n"
            f"Suggestion prompt: {suggestion_prompt}"
        )
        system_prompt = (
            "You are a financial guru specializing in superannuation fees. "
            "Using only the fee data provided below, respond EXACTLY in the following format (replace placeholders with actual values):\n\n"
            "Of the {num_funds} funds compared, {cheapest_fund} is the cheapest, with an annual fee of ${total_fee} "
            "which is {fee_percentage}% of your current account balance.\n\n"
            "Final paragraph: Use exactly the suggestion prompt provided in the data to ask about the next steps. "
            "Do not modify the suggestion prompt text.\n\n"
            "Do not include any extra commentary or reference any funds other than the one provided in the data."
        )
        return await ask_llm(system_prompt, user_prompt)
    except Exception as e:
        # Add detailed error handling
        print(f"DEBUG process_find_cheapest: Error details: {repr(e)}")
        return f"I'm sorry, I encountered an error while finding the cheapest fund. Please try again."

async def process_project_balance(context: dict) -> str:
    """Process project_balance intent with the given context."""
    user_age = context["current_age"]
    current_fund = context["current_fund"]
    retirement_age = context["retirement_age"]
    user_balance = context["current_balance"]
    current_income = context["current_income"]
    super_included = context.get("super_included", False)
    
    print(f"DEBUG main.py: Searching for fund: {current_fund}")
    matched_fund = match_fund_name(current_fund, df)
    if matched_fund is None:
        return f"Could not find applicable fee data for your current fund: {current_fund}."
    print(f"DEBUG main.py: Matched fund name: {matched_fund}")
    
    # Now get the row for the matched fund using the safe filter function
    current_fund_rows = find_applicable_funds(
        filter_dataframe_by_fund_name(df, matched_fund, exact_match=True),
        user_age
    )   
    if current_fund_rows.empty:
        return f"Could not find applicable fee data for your current fund: {current_fund}."
    current_fund_row = current_fund_rows.iloc[0]
    
    # Use centralized assumptions
    wage_growth = economic_assumptions["WAGE_GROWTH"]
    employer_contribution_rate = economic_assumptions["EMPLOYER_CONTRIBUTION_RATE"]
    investment_return = economic_assumptions["INVESTMENT_RETURN"]
    inflation_rate = economic_assumptions["INFLATION_RATE"]
    
    # Calculate income net of super using the imported function
    income_net_of_super = calculate_income_net_of_super(current_income, super_included, employer_contribution_rate)
    print(f"DEBUG main.py: Calculated income_net_of_super: {income_net_of_super}, using super_included={super_included}")

    projected_balance = project_super_balance(
        int(user_age), 
        int(retirement_age), 
        float(user_balance), 
        float(income_net_of_super),  # Use income net of super here
        wage_growth, 
        employer_contribution_rate, 
        investment_return, 
        inflation_rate,
        current_fund_row
    )
    
    next_intent, suggestion_prompt = get_next_intent_info("project_balance")
    context.setdefault('data', {})['suggested_next_intent'] = next_intent 
    context.setdefault('data', {})['retirement_balance'] = projected_balance
        
    user_prompt = (
        f"Data:\n"
        f"Current age: {user_age}\n"
        f"Current balance: ${user_balance:,.0f}\n"
        f"Current income: ${current_income:,.0f}\n"
        f"Income net of super: ${income_net_of_super:,.0f}\n"
        f"Desired retirement age: {retirement_age}\n"
        f"Current fund: {matched_fund}\n"
        f"Assumptions: Wage growth = {wage_growth}%, Employer contribution rate = {employer_contribution_rate}%, "
        f"Gross investment return = {investment_return}%, Inflation rate = {inflation_rate}%.\n"
        f"Using your current fund's fee structure (which is recalculated monthly), the projected super balance at retirement is: "
        f"${projected_balance:,.0f}.\n"
        f"Suggestion prompt: {suggestion_prompt}"
    )
    
    system_prompt = (
        "You are a financial guru specializing in superannuation projections. "
        "1. First paragraph: Based solely on the data provided, produce a response EXACTLY in the following format:\n\n"
        "At retirement, you will have approximately $[projected_balance] in your account with $[current_fund]. \n"
        "This estimate is based on the default investment for your age, the fees specific to your account value and your fund's fee structures. \n\n"
        "2. Second paragraph: In one concise sentence, explain the primary assumptions driving this projection, "
        "specifically highlighting the impact of your current fund's fees (which are recalculated monthly), investment performance, wage growth, and inflation. \n\n"
        "3. Final paragraph: Use exactly the suggestion prompt provided in the data to ask about the next steps. "
        "Do not modify the suggestion prompt text.\n\n"
        "Keep your response friendly, clear, and focused, with no extraneous information or caveats."
    )
    
    return await ask_llm(system_prompt, user_prompt)

async def process_compare_balance_projection(context: dict) -> str:
    """Process compare_balance_projection intent with the given context."""
    user_age = context["current_age"]
    current_fund = context["current_fund"]
    nominated_fund = context["nominated_fund"]
    retirement_age = context["retirement_age"]
    user_balance = context["current_balance"]
    current_income = context["current_income"]
    super_included = context.get("super_included", False)

    # Calculate income net of super
    employer_contribution_rate = economic_assumptions["EMPLOYER_CONTRIBUTION_RATE"]
    income_net_of_super = calculate_income_net_of_super(current_income, super_included, employer_contribution_rate)
    
    print(f"DEBUG main.py: Searching for funds: {current_fund} and {nominated_fund}")
    
    # Match the current fund
    matched_current_fund = match_fund_name(current_fund, df)
    if matched_current_fund is None:
        return f"Could not find applicable fee data for your current fund: {current_fund}."
    
    # Match the nominated fund
    matched_nominated_fund = match_fund_name(nominated_fund, df)
    if matched_nominated_fund is None:
        return f"Could not find applicable fee data for your nominated fund: {nominated_fund}."
    
    print(f"DEBUG main.py: Matched fund names: {matched_current_fund} and {matched_nominated_fund}")
    
    # Replace with this code
    current_fund_rows = find_applicable_funds(
        filter_dataframe_by_fund_name(df, matched_current_fund, exact_match=True),
        user_age
    )
    nominated_fund_rows = find_applicable_funds(
        filter_dataframe_by_fund_name(df, matched_nominated_fund, exact_match=True),
        user_age
    )
    
    if current_fund_rows.empty:
        return f"Could not find applicable fee data for your current fund: {current_fund}."
    if nominated_fund_rows.empty:
        return f"Could not find applicable fee data for your nominated fund: {nominated_fund}."
    
    current_fund_row = current_fund_rows.iloc[0]
    nominated_fund_row = nominated_fund_rows.iloc[0]
    
    # Use centralized assumptions
    wage_growth = economic_assumptions["WAGE_GROWTH"]
    employer_contribution_rate = economic_assumptions["EMPLOYER_CONTRIBUTION_RATE"]
    investment_return = economic_assumptions["INVESTMENT_RETURN"]
    inflation_rate = economic_assumptions["INFLATION_RATE"]
    
    # Project balances for both funds
    current_projected_balance = project_super_balance(
        int(user_age), 
        int(retirement_age), 
        float(user_balance), 
        float(income_net_of_super),  
        wage_growth, 
        employer_contribution_rate, 
        investment_return, 
        inflation_rate,
        current_fund_row
    )
    
    nominated_projected_balance = project_super_balance(
        int(user_age), 
        int(retirement_age), 
        float(user_balance), 
        float(income_net_of_super),  
        wage_growth, 
        employer_contribution_rate, 
        investment_return, 
        inflation_rate,
        nominated_fund_row
    )
    
    # Calculate difference and percentage difference
    absolute_difference = nominated_projected_balance - current_projected_balance
    percentage_difference = (absolute_difference / current_projected_balance) * 100 if current_projected_balance > 0 else 0
    
    # Get fee breakdowns for context
    current_breakdown = compute_fee_breakdown(current_fund_row, user_balance)
    nominated_breakdown = compute_fee_breakdown(nominated_fund_row, user_balance)
    
    next_intent, suggestion_prompt = get_next_intent_info("compare_balance_projection")
    context.setdefault('data', {})['suggested_next_intent'] = next_intent


    user_prompt = (
        f"Data:\n"
        f"Current age: {user_age}\n"
        f"Current balance: ${user_balance:,.0f}\n"
        f"Current income (as provided): ${current_income:,.0f}\n"
        f"Income net of super: ${income_net_of_super:,.0f}\n"
        f"Desired retirement age: {retirement_age}\n"
        f"Current fund: {matched_current_fund}\n"
        f"Nominated fund: {matched_nominated_fund}\n"
        f"Assumptions: Wage growth = {wage_growth}%, Employer contribution rate = {employer_contribution_rate}%, "
        f"Gross investment return = {investment_return}%, Inflation rate = {inflation_rate}%.\n"
        f"Current fund annual fees: ${current_breakdown['total_fee']:,.2f} "
        f"({(current_breakdown['total_fee']/user_balance)*100:.2f}% of your balance)\n"
        f"Nominated fund annual fees: ${nominated_breakdown['total_fee']:,.2f} "
        f"({(nominated_breakdown['total_fee']/user_balance)*100:.2f}% of your balance)\n"
        f"Projected balance at retirement with {matched_current_fund}: ${current_projected_balance:,.0f}\n"
        f"Projected balance at retirement with {matched_nominated_fund}: ${nominated_projected_balance:,.0f}\n"
        f"Absolute difference: ${absolute_difference:,.0f}\n"
        f"Percentage difference: {percentage_difference:.2f}%\n"
        f"Suggestion prompt: {suggestion_prompt}"
    )
    
    system_prompt = (
        "You are a financial guru specializing in superannuation projections. "
        "Based solely on the data provided, produce a response comparing the projected balances "
        "between the two funds. Use this format:\n\n"
        "At retirement, your projected balance with [current_fund] would be approximately $[current_balance], "
        "while with [nominated_fund] it would be approximately $[nominated_balance].\n\n"
        "This represents a difference of $[difference] ([percentage]% [higher/lower]) over your working life.\n\n"
        "Then, add a concise explanation about how the difference in fees between the two funds compounds over time "
        "to create this gap in projected balances.\n\n"
        "Final paragraph: Use exactly the suggestion prompt provided in the data to ask about the next steps. "
    )
    
    return await ask_llm(system_prompt, user_prompt)

async def process_retirement_outcome(context: dict) -> str:
    """Process retirement_outcome intent with the given context."""
    print("DEBUG: Entering process_retirement_outcome function")
    user_age = context["current_age"]
    retirement_age = context["retirement_age"]
    retirement_balance = context.get("retirement_balance")
    
    # Fix the retirement_income_option handling
    retirement_income_option = context.get("retirement_income_option")
    print(f"DEBUG process_retirement_outcome: retirement_income_option type = {type(retirement_income_option)}, value = '{retirement_income_option}'")
    
    # Check if retirement_income_option is the string 'None'
    if retirement_income_option == 'None':
        # Try to get it from context.get('data') or other places
        print("DEBUG process_retirement_outcome: Got string 'None', checking state data")
        if 'data' in context and context['data'] and context['data'].get('retirement_income_option'):
            retirement_income_option = context['data'].get('retirement_income_option')
        # If that doesn't work, check if it's in the context dict directly
        elif 'retirement_income_option' in context:
            retirement_income_option = context['retirement_income_option']
    
    # Another fallback: assume same_as_current if option is missing but we have income
    if (retirement_income_option is None or retirement_income_option == 'None') and context.get('current_income', 0) > 0:
        print("DEBUG process_retirement_outcome: Assuming same_as_current as fallback")
        retirement_income_option = 'same_as_current'
    
    print(f"DEBUG process_retirement_outcome: Final retirement_income_option = '{retirement_income_option}'")
    
    retirement_income = context.get("retirement_income")
    current_income = context.get("current_income", 0)
    
    print(f"DEBUG process_retirement_outcome: retirement_income_option = '{retirement_income_option}'")
    print(f"DEBUG process_retirement_outcome: current_income = {current_income}")
    print(f"DEBUG process_retirement_outcome: retirement_income = {retirement_income}")

    # If no retirement balance, use project_balance function to get it
    if not retirement_balance:
        # We need to call project_balance logic to get retirement balance
        current_fund = context["current_fund"]
        user_balance = context["current_balance"]
        super_included = context.get("super_included", False)
        
        # First use LLM to match the fund name
        matched_fund = match_fund_name(current_fund, df)
        if matched_fund is None:
            return f"Could not find applicable fee data for your current fund: {current_fund}."
            
        # Now get the row for the matched fund
        current_fund_rows = find_applicable_funds(
            filter_dataframe_by_fund_name(df, matched_fund, exact_match=True),
            user_age
        )
        if current_fund_rows.empty:
            return f"Could not find applicable fee data for your current fund: {current_fund}."
        current_fund_row = current_fund_rows.iloc[0]
        
        # Use centralized assumptions
        wage_growth = economic_assumptions["WAGE_GROWTH"]
        employer_contribution_rate = economic_assumptions["EMPLOYER_CONTRIBUTION_RATE"]
        investment_return = economic_assumptions["INVESTMENT_RETURN"]
        inflation_rate = economic_assumptions["INFLATION_RATE"]
        
        # Calculate income net of super
        income_net_of_super = calculate_income_net_of_super(current_income, super_included, employer_contribution_rate)
        
        # Calculate retirement balance
        retirement_balance = project_super_balance(
            int(user_age), 
            int(retirement_age), 
            float(user_balance), 
            float(income_net_of_super),
            wage_growth, 
            employer_contribution_rate, 
            investment_return, 
            inflation_rate,
            current_fund_row
        )
    
    # Calculate annual income based on retirement_income_option
    annual_retirement_income = 0
    if retirement_income_option == "same_as_current":
        print("DEBUG process_retirement_outcome: Using same_as_current option")
        # Calculate after-tax income using the existing function
        annual_retirement_income = calculate_after_tax_income(current_income, retirement_age)
        print(f"DEBUG process_retirement_outcome: Calculated after-tax income: {annual_retirement_income}")
    elif retirement_income_option in ["modest_single", "modest_couple", "comfortable_single", "comfortable_couple"]:
        print(f"DEBUG process_retirement_outcome: Using ASFA standard: {retirement_income_option}")
        # Use ASFA standards
        asfa_standards = get_asfa_standards()
        annual_retirement_income = asfa_standards[retirement_income_option]["annual_amount"]
        print(f"DEBUG process_retirement_outcome: ASFA standard amount: {annual_retirement_income}")
    elif retirement_income_option == "custom":
        print(f"DEBUG process_retirement_outcome: Using custom amount: {context.get('retirement_income')}")
        if context.get("retirement_income") and context.get("retirement_income") > 0:
            annual_retirement_income = context.get("retirement_income")
        elif "data" in context and context.get("data", {}).get("retirement_income", 0) > 0:
            annual_retirement_income = context["data"]["retirement_income"]
        else:
            # Extract the custom amount from the user_message if present
            amount_match = None
            if "user_message" in context:
                amount_match = re.search(r'(\d[\d,.]*k?m?)', context["user_message"])
            elif "data" in context and "last_clarification_prompt" in context["data"]:
                amount_match = re.search(r'(\d[\d,.]*k?m?)', context["data"]["last_clarification_prompt"])
            if amount_match:
                from backend.main import parse_numeric_with_suffix
                annual_retirement_income = parse_numeric_with_suffix(amount_match.group(1))
            else:
                return "Could not determine your desired retirement income. Please specify a custom amount."
    elif retirement_income and retirement_income > 0:
        print(f"DEBUG process_retirement_outcome: Using custom amount: {retirement_income}")
        # Use custom amount
        annual_retirement_income = retirement_income
    else:
        print("DEBUG process_retirement_outcome: No valid income option found, returning error")
        # Fallback to a default if somehow we don't have a valid income
        return "Could not determine your desired retirement income. Please specify an income option."
    
    # Get next intent info from our centralized library
    next_intent, suggestion_prompt = get_next_intent_info("retirement_outcome")
    context.setdefault('data', {})['suggested_next_intent'] = next_intent
    context.setdefault('data', {})['retirement_income'] = annual_retirement_income
    
    # Use more conservative retirement investment return
    retirement_investment_return = economic_assumptions["RETIREMENT_INVESTMENT_RETURN"]
    inflation_rate = economic_assumptions["INFLATION_RATE"]
    
    # Calculate when funds will be depleted
    depletion_age = calculate_retirement_drawdown(
        float(retirement_balance),
        int(retirement_age),
        float(annual_retirement_income),
        retirement_investment_return,
        inflation_rate
    )

    context.setdefault('data', {})['retirement_drawdown_age'] = depletion_age
    # Store the depletion age in the context for future reference
    if "data" in context:
        context["data"]["retirement_drawdown_age"] = depletion_age
    
    # Format the retirement income option for display
    if retirement_income_option == "same_as_current":
        income_description = f"Same as your current after-tax income (${annual_retirement_income:,.0f} per year)"
    elif retirement_income_option in ["modest_single", "modest_couple", "comfortable_single", "comfortable_couple"]:
        asfa_standards = get_asfa_standards()
        standard_name = retirement_income_option.replace('_', ' ').title()
        income_description = f"ASFA {standard_name} Standard (${annual_retirement_income:,.0f} per year)"
    else:
        income_description = f"Custom amount of ${annual_retirement_income:,.0f} per year"
    
    # Special handling for the case where funds won't be depleted
    if depletion_age >= 200:
        depletion_message = "Your retirement savings are projected to last your lifetime."
    else:
        years_in_retirement = depletion_age - retirement_age
        depletion_message = f"Your retirement savings are projected to last until age {depletion_age}, which is {years_in_retirement} years after retirement."
    
    user_prompt = (
        f"Data:\n"
        f"Current age: {user_age}\n"
        f"Retirement age: {retirement_age}\n"
        f"Retirement balance: ${retirement_balance:,.0f}\n"
        f"Annual retirement income: {income_description}\n"
        f"Retirement investment return: {retirement_investment_return}%\n"
        f"Inflation rate: {inflation_rate}%\n"
        f"Depletion age: {depletion_age}\n"
        f"Suggestion prompt: {suggestion_prompt}"
    )
    
    system_prompt = (
        "You are a financial guru specializing in retirement planning. "
        "Based solely on the data provided, produce a response that follows this format:\n\n"
        "First paragraph: Confirm their retirement balance and annual income in retirement with specific dollar amounts.\n\n"
        "Second paragraph: State how long their retirement savings are projected to last, "
        "emphasizing that this is based on the assumptions provided and actual results may vary.\n\n"
        "Third paragraph: Provide a brief explanation of key factors that could affect this projection, "
        "such as investment returns, inflation, unexpected expenses, or changes in retirement income needs.\n\n"
        "Final paragraph: Use exactly the suggestion prompt provided in the data to ask about the next steps. "
        "Do not modify the suggestion prompt text.\n\n"
        "Keep your response informative, conversational, and under 200 words."
    )
    
    return await ask_llm(system_prompt, user_prompt)

async def get_retirement_income_options_prompt(retirement_balance: float, after_tax_income: float) -> str:
    """Generate a prompt explaining retirement income options with proper values"""
    asfa_standards = get_asfa_standards()

    # Ensure we have non-negative values
    retirement_balance = max(0, retirement_balance)
    after_tax_income = max(0, after_tax_income)
    
    # Format values for display
    formatted_balance = f"${retirement_balance:,.0f}"
    formatted_income = f"${after_tax_income:,.0f}"
    
    system_prompt = (
        "You are a friendly financial expert helping someone understand their retirement income options. "
        "Create a clear, conversational explanation that presents these options in a way that's easy to understand. "
        "Format the options as a numbered list, and explain that they can reply with their preference. "
        "Keep your tone warm and supportive, but make your explanation concise and to the point."
        "Avoid letter formats like 'Dear User' or "
        "'Best wishes'. Speak directly to the person in a conversational way."
    )
    
    user_prompt = (
        f"Please explain these retirement income options to the user with this specific introduction:\n\n"
        f"Your estimated balance at retirement is {formatted_balance}. To calculate how long this might last in providing you with an income, we need to know what income you would like to withdraw.\n\n"
        f"1. Same as current income after tax: Your current after-tax income is {formatted_income}. This is a good option if you're comfortable with your current lifestyle and want to maintain it during retirement.\n\n"
        f"2. ASFA Modest Single Standard: $32,000 per year - Basic activities and limited leisure\n\n"
        f"3. ASFA Modest Couple Standard: $46,000 per year - Basic needs and limited leisure for couples\n\n"
        f"4. ASFA Comfortable Single Standard: $52,000 per year - Good standard of living with private health insurance\n\n"
        f"5. ASFA Comfortable Couple Standard: $75,000 per year - Good standard of living for couples\n\n"
        f"6. Custom amount\n\n"
        f"The user should be able to reply with either the number or the name of their preferred option."
        f"Keep your response conversational and concise, avoiding formal letter formats."
    )
    
    return await ask_llm(system_prompt, user_prompt)

async def process_update_variable(context: dict) -> str:
    """Process update_variable intent by re-running the previous intent with updated values."""
    print(f"DEBUG process_update_variable: Received context: {context}")
    
    # Get the original intent to determine which process to run
    original_intent = context.get("original_intent")
    
    # If no original_intent, fall back to previous_intent
    if not original_intent:
        original_intent = context.get("previous_intent")
    
    # If still no valid intent, we can't proceed
    if not original_intent or original_intent == "unknown" or original_intent == "update_variable":
        return "I'm not sure which calculation you'd like to update. Could you please provide a complete query?"
    
    # Create a new context that combines the current updates with the preserved values
    updated_context = context.copy()
    
    # Get all fields from previous data except those that have been intentionally updated
    if context.get('previous_data'):
        for key, value in context['previous_data'].items():
            # For numeric fields, only copy if the current value is None or 0
            if isinstance(value, (int, float)) and (updated_context.get(key) is None or updated_context.get(key) == 0):
                updated_context[key] = value
            # For string fields, only copy if the current value is None or empty
            elif isinstance(value, str) and not updated_context.get(key):
                updated_context[key] = value
            # For other types (including None), only copy if not present in updated_context
            elif key not in updated_context:
                updated_context[key] = value
    
    # Set the intent to the original intent to re-run that calculation
    updated_context['intent'] = original_intent
    
    print(f"DEBUG process_update_variable: Original intent found: {original_intent}")
    print(f"DEBUG process_update_variable: Updated context: {updated_context}")
    
    # Run the appropriate process function with the updated context
    if original_intent == "project_balance":
        return await process_project_balance(updated_context)
    elif original_intent == "compare_fees_nominated":
        return await process_compare_fees_nominated(updated_context)
    elif original_intent == "compare_fees_all":
        return await process_compare_fees_all(updated_context)
    elif original_intent == "find_cheapest":
        return await process_find_cheapest(updated_context)
    elif original_intent == "compare_balance_projection":
        return await process_compare_balance_projection(updated_context)
    elif original_intent == "retirement_outcome":
        return await process_retirement_outcome(updated_context)
    else:
        return "I'm not sure which calculation you'd like to update. Could you please provide a complete query?"

async def process_default_comparison(context: dict) -> str:
    """Process default comparison when no specific intent is matched."""
    user_age = context["current_age"]
    user_balance = context["current_balance"]
    
    matched_rows = find_applicable_funds(df, user_age)
    print(f"DEBUG: matched_rows length={len(matched_rows)}")
    
    fee_summaries = []
    if matched_rows.empty:
        fee_summaries_str = "No applicable funds found based on your age."
    else:
        for idx, row in matched_rows.iterrows():
            breakdown = compute_fee_breakdown(row, user_balance)
            fee_summaries.append(
                f"{row['FundName']}: Investment Fee = ${breakdown['investment_fee']:,.2f}, "
                f"Admin Fee = ${breakdown['admin_fee']:,.2f}, Member Fee = ${breakdown['member_fee']:,.2f}, "
                f"Total = ${breakdown['total_fee']:,.2f}"
            )
        fee_summaries_str = "\n".join(fee_summaries)
    print("DEBUG: fee_summaries_str:\n", fee_summaries_str)
    
    system_prompt = (
        "You are a financial guru that calculates total superannuation fees for Australian consumers. "
        "Based solely on the fee information provided (do not reference performance data), "
        "compare the fees among the funds and explain which fee components contribute most to the differences, "
        "and conclude with a statement on the potential impact on retirement balance."
    )
    user_prompt = f"""
    User question: {context.get('user_query', '')}
    Fee breakdown for each fund:
    {fee_summaries_str}
    Instructions:
    1) Compare the total fee charged by the funds.
    2) Explain why there is a fee difference.
    3) Conclude with a statement on the potential impact on retirement balance.
    """
    return await ask_llm(system_prompt, user_prompt)

async def process_intent(intent: str, context: dict) -> str:
    print(f"DEBUG process_intent: Received intent: {intent}")
    print(f"DEBUG process_intent: Received context: {context}")
    
    try:
        response = ""
        
        # Check if we should use the intent from context instead
        context_intent = context.get("intent")
        if intent == "unknown" and context_intent and context_intent != "unknown":
            print(f"DEBUG process_intent: Overriding 'unknown' intent with context intent: {context_intent}")
            intent = context_intent

        if intent == "compare_fees_nominated":
            response = await process_compare_fees_nominated(context)
        elif intent == "compare_fees_all":
            response = await process_compare_fees_all(context)
        elif intent == "find_cheapest":
            response = await process_find_cheapest(context)
        elif intent == "project_balance":
            response = await process_project_balance(context)
        elif intent == "compare_balance_projection":
            response = await process_compare_balance_projection(context)
        elif intent == "retirement_outcome":
            response = await process_retirement_outcome(context)
        elif intent == "update_variable":
            response = await process_update_variable(context)
        else:
            response = await process_default_comparison(context)
        
        if not response:
            response = "I apologize, but I couldn't generate a response. Please try again."
            
        print(f"DEBUG process_intent: Generated response: {response}")
        return response
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"DEBUG process_intent: Error processing intent: {repr(e)}")
        print(f"DEBUG process_intent: Error traceback: {error_details}")
        return "I apologize, but I encountered an error while processing your request. Please try again."

async def process_query(user_query: str, previous_system_response: str = "", full_history: str = "", state: dict = None) -> str:
    print(f"DEBUG main.py: Entering process_query")
    print(f"DEBUG main.py: User query: {user_query}")
    print(f"DEBUG main.py: Previous response: {previous_system_response}")
    print(f"DEBUG main.py: Full history: {full_history}")
    print(f"DEBUG main.py: Initial state: {state}")
    
    # Ensure state is a dictionary.
    if state is None or not isinstance(state, dict):
        state = {"data": {}}

    # Check if we need to handle a transition to a suggested next intent
    if state.get("data", {}).get("suggested_next_intent") and user_query.strip():
        from backend.helper import handle_next_intent_transition, is_affirmative_response
        
        # Check if we should transition based on the user's response
        if is_affirmative_response(user_query):
            print(f"DEBUG main.py: Detected affirmative response to suggestion")
            updated_context = await handle_next_intent_transition(user_query, state.get("data", {}))
            
            if updated_context:
                print(f"DEBUG main.py: Transitioning to suggested next intent: {updated_context.get('intent')}")
                # Update the intent in the state
                state["data"]["intent"] = updated_context.get("intent")
                if updated_context.get("previous_intent"):
                    state["data"]["previous_intent"] = updated_context.get("previous_intent")
                
                # Clear the suggestion since we're acting on it
                if "suggested_next_intent" in state["data"]:
                    del state["data"]["suggested_next_intent"]
                    
                # For update_variable intent, make sure we have an original_intent to refer back to
                if state["data"]["intent"] == "update_variable" and not state["data"].get("original_intent"):
                    state["data"]["original_intent"] = state["data"].get("previous_intent")

    # If the user query is empty, don't override state values.
    if not user_query.strip():
        print("DEBUG main.py: Empty user query detected; using existing state values.")
        extracted = state.get("data", {})
    else:
        # Only run intent extraction if we're not collecting variables
        if not state.get("missing_var"):
            # Run initial extraction.
            extracted = await extract_intent_variables(user_query, previous_system_response)
            
            # Then adjust numeric fields if previous_system_response suggests so.
            if previous_system_response:
                prev_response_lower = previous_system_response.lower()
                if "current income" in prev_response_lower and re.search(r'[\d.]+[km]?$', user_query):
                    numeric_value = parse_numeric_with_suffix(user_query)
                    # Use update so we keep any other extracted values.
                    extracted.update({"intent": "unknown", "current_income": numeric_value})
                elif "retirement age" in prev_response_lower and re.search(r'\d+', user_query):
                    retirement_age_value = int(re.search(r'\d+', user_query).group())
                    extracted.update({"intent": "unknown", "retirement_age": retirement_age_value})
        else:
            # If we're collecting variables, don't extract intent or other variables
            # Instead, preserve the existing intent from the state
            extracted = {"intent": state["data"].get("intent", "unknown")}
            print(f"DEBUG main.py: Preserving existing intent while collecting variables: {extracted['intent']}")

    print(f"DEBUG main.py: LLM extracted variables: {extracted}")
    print(f"DEBUG main.py: Values right after extraction: super_included={extracted.get('super_included')}")
    
    # Handle intent and check if it's new
    intent = extracted.get("intent", "unknown")
    print("DEBUG process_query: Extracted intent:")
    print(intent)
    
    if intent == "unknown" and user_query.strip():
        # Check if this is an affirmative response to a previous suggestion
        print(f"DEBUG process_query: Unknown intent detected, checking for suggestion in state: {state.get('data', {}).get('suggested_next_intent')}")
        if state.get("data", {}).get("suggested_next_intent"):
            print(f"DEBUG process_query: Checking if '{user_query}' is an affirmative response")
            print(f"DEBUG process_query: is_affirmative_response result: {is_affirmative_response(user_query)}")
            if is_affirmative_response(user_query):
                next_intent = state["data"]["suggested_next_intent"]
                print(f"DEBUG process_query: Affirmative response detected, switching to suggested intent: {next_intent}")
                intent = next_intent
                # Save the previous intent for reference
                state["data"]["previous_intent"] = state["data"].get("intent", "unknown")
                # Remove the suggestion now that we're acting on it
                print(f"DEBUG process_query: Removing suggested_next_intent from state")
                state["data"].pop("suggested_next_intent", None)
            else:
                # If not affirmative, fall back to current intent
                print(f"DEBUG process_query: Not an affirmative response, using stored intent")
                intent = state["data"].get("intent", "unknown")
        elif state["data"].get("intent") and state["data"].get("intent") != "unknown":
            # No suggestion, just use current intent
            print(f"DEBUG process_query: Using stored intent")
            intent = state["data"]["intent"]
    
    if intent == "unknown" and state.get("data", {}).get("intent"):
        intent = state["data"]["intent"]
        print("DEBUG process_query: Using stored intent:")
        print(intent)
    
    print("DEBUG process_query: Final intent:")
    print(intent)
    
    # Save previous intent in state
    current_state_intent = state["data"].get("intent") if state and "data" in state else None
    if current_state_intent and current_state_intent != "unknown" and intent == "update_variable":
        state["data"]["previous_intent"] = current_state_intent

    print(f"DEBUG: LLM-determined intent: {intent}")

    # Check if this is a new intent
    current_state_intent = state["data"].get("intent") if state and "data" in state else None
    is_new_intent = intent != current_state_intent
    print(f"DEBUG: Current stored intent: {current_state_intent}, extracted intent: {intent}, is_new_intent: {is_new_intent}")
    print("DEBUG process_query: Current stored intent:")
    print(current_state_intent)
    print("DEBUG process_query: Is new intent:")
    print(is_new_intent)

    # Save previous intent in state
    if current_state_intent and current_state_intent != "unknown":
        state["data"]["previous_intent"] = current_state_intent

    # IMPORTANT: Save the intent in state.data immediately
    # This ensures the intent persists throughout variable collection
    state["data"]["intent"] = intent
    
    # Get acknowledgment if this is a new intent
    acknowledgment = ""
    if is_new_intent:
        acknowledgment = ""  # Setting to empty string instead of calling get_intent_acknowledgment
    
    # Get current values from state
    current_fund = state["data"].get("current_fund")
    nominated_fund = state["data"].get("nominated_fund")
    user_age = state["data"].get("current_age", 0)
    user_balance = state["data"].get("current_balance", 0)
    current_income = state["data"].get("current_income", 0)
    retirement_age = state["data"].get("retirement_age", 0)
    
    print("DEBUG main.py: Current state before update:", state)

    # Conditionally update state with new extraction only if user query is non-empty
    if user_query.strip():
        print("DEBUG main.py: Current state before update:", state)
        print("DEBUG main.py: Updating state with new extraction:", extracted)

        # Special handling for update_variable intent - preserve original values
        if extracted.get("intent") == "update_variable":
            # Only update the specific variables that were explicitly mentioned in the user query
            for key in ["retirement_age", "retirement_income", "current_fund"]:
                if key in extracted and extracted[key] is not None and extracted[key] != 0:
                    state["data"][key] = extracted[key]
                    print(f"DEBUG main.py: For update_variable, updating {key} to {extracted[key]}")
        else:
        # If we're in the middle of collecting variables, only update the specific variable we asked for
            if state.get("missing_var"):
                # Map the missing_var to the actual state key
                var_map = {
                    "age": "current_age",
                    "super balance": "current_balance",
                    "current income": "current_income",
                    "desired retirement age": "retirement_age",
                    "current fund": "current_fund",
                    "nominated fund": "nominated_fund",
                    "super_included": "super_included",
                    "income_net_of_super": "income_net_of_super",
                    "after_tax_income": "after_tax_income",
                    "retirement_balance": "retirement_balance",
                    "retirement_income": "retirement_income",
                    "retirement_drawdown_age": "retirement_drawdown_age"
                }           
                var_key = var_map.get(state["missing_var"], state["missing_var"])
                print(f"DEBUG main.py: Looking for extracted value for {var_key} (mapped from {state['missing_var']})")
                print(f"DEBUG main.py: Current state values: {state['data']}")
                
                # Extract the specific variable value from the user's response
                response_value = None
                if "retirement age" in state["missing_var"].lower():
                    match = re.search(r'\d+', user_query)
                    if match:
                        response_value = int(match.group())
                elif "income" in state["missing_var"].lower():
                    match = re.search(r'[\d.]+[km]?', user_query)
                    if match:
                        response_value = parse_numeric_with_suffix(match.group())
                elif "balance" in state["missing_var"].lower():
                    match = re.search(r'[\d.]+[km]?', user_query)
                    if match:
                        response_value = parse_numeric_with_suffix(match.group())
                elif "age" in state["missing_var"].lower():
                    match = re.search(r'\d+', user_query)
                    if match:
                        response_value = int(match.group())
                
                if response_value is not None:
                    print(f"DEBUG main.py: Extracted value {response_value} for {var_key}")
                    state["data"][var_key] = response_value
            else:
                # We're not collecting variables, so process initial extraction

                # Always handle fund names separately (they are strings) regardless of other state variables
                if extracted.get("current_fund"):
                    temp_fund = extracted["current_fund"]
                    matched_fund = match_fund_name(temp_fund, df)
                    print(f"DEBUG main.py: Processing extracted current_fund: {temp_fund}, matched to: {matched_fund}")
                    if matched_fund:
                        state["data"]["current_fund"] = matched_fund
                    else:
                        state["data"]["current_fund"] = temp_fund
                        
                if extracted.get("nominated_fund"):
                    temp_fund = extracted["nominated_fund"]
                    matched_fund = match_fund_name(temp_fund, df)
                    print(f"DEBUG main.py: Processing extracted nominated_fund: {temp_fund}, matched to: {matched_fund}")
                    if matched_fund:
                        state["data"]["nominated_fund"] = matched_fund
                    else:
                        state["data"]["nominated_fund"] = temp_fund
                print(f"DEBUG main.py: Before updating super_included, current value: {state['data'].get('super_included')}")
                if "super_included" in extracted and extracted["super_included"] is not None:
                    state["data"]["super_included"] = extracted["super_included"]
                    print(f"DEBUG main.py: Updated super_included to {extracted['super_included']}")

                # Add the new code here to capture retirement income
                if "retirement_income" in extracted and extracted["retirement_income"] is not None:
                    state["data"]["retirement_income"] = extracted["retirement_income"]
                    print(f"DEBUG main.py: Updated retirement_income to {extracted['retirement_income']}")
                
                # For numeric values, only update if we don't already have values from the variable collection process
                if not any(state["data"].get(key) for key in ["current_age", "current_balance", "current_income", "retirement_age"]):
                    for key in ["current_age", "current_balance", "current_income", "retirement_age"]:
                        if key in extracted and extracted[key] is not None:
                            if extracted[key] != state["data"].get(key):  # Only update if value is different
                                print(f"DEBUG main.py: Updating {key} from {state['data'].get(key)} to {extracted[key]}")
                                state["data"][key] = extracted[key]
                
            print("DEBUG main.py: Updated state after extraction:", state)
    
    # Update calculated values based on available data
    state = update_calculated_values(state)
    print("DEBUG main.py: State after updating calculated values:", state)
    
    # Build context dict for variable requests
    context = {
        "current_age": state["data"].get("current_age", 0) or None,
        "current_balance": state["data"].get("current_balance", 0) or None,
        "current_income": state["data"].get("current_income", 0) or None,
        "retirement_age": state["data"].get("retirement_age", 0) or None,
        "current_fund": state["data"].get("current_fund"), 
        "nominated_fund": state["data"].get("nominated_fund"), 
        "super_included": state["data"].get("super_included"), 
        "retirement_income_option": state["data"].get("retirement_income_option"), 
        "retirement_income": state["data"].get("retirement_income"), 
        "income_net_of_super": state["data"].get("income_net_of_super"), 
        "after_tax_income": state["data"].get("after_tax_income"), 
        "retirement_balance": state["data"].get("retirement_balance"),
        "retirement_drawdown_age": state["data"].get("retirement_drawdown_age"),
        "intent": intent,
        "previous_intent": state["data"].get("previous_intent"),
        "original_intent": state["data"].get("original_intent"),  
        "is_new_intent": is_new_intent,
        "previous_var": state["data"].get("last_var"),
        "user_query": user_query 
}
    
    # For update_variable intent, store the entire previous state data for reference
    if intent == "update_variable":
        context["previous_data"] = state.get("data", {})

    print(f"DEBUG main.py: retirement_income_option in state: {state['data'].get('retirement_income_option')}")
    print(f"DEBUG main.py: retirement_income_option in context: {context.get('retirement_income_option')}")
    print("DEBUG main.py: State data before context creation:", state["data"])
    print("DEBUG main.py: Created context:", context)

    # Determine missing variables based on the intent.
    print(f"DEBUG: Final values - user_age: {user_age}, user_balance: {user_balance}, intent: {intent}, current_fund: {current_fund}, nominated_fund: {nominated_fund}, current_income: {current_income}, retirement_age: {retirement_age}")
    missing_vars = []
    print("DEBUG main.py: Determining missing variables")
    print("DEBUG main.py: Current state:", state)
    
    # Only add to missing_vars if we don't already have a valid value
    if intent == "project_balance":
        print("DEBUG main.py: Checking missing variables for project_balance intent")
        if not state["data"].get("current_age"):
            missing_vars.append("age")
            print("DEBUG main.py: Missing variable: age")
        if not state["data"].get("current_fund"):
            missing_vars.append("current fund")
            print("DEBUG main.py: Missing variable: current fund")
        if not state["data"].get("current_balance"):
            missing_vars.append("super balance")
            print("DEBUG main.py: Missing variable: super balance")
        if not state["data"].get("retirement_age") or state["data"].get("retirement_age") <= state["data"].get("current_age", 0):
            missing_vars.append("desired retirement age")
            print("DEBUG main.py: Missing variable: desired retirement age")
        if not state["data"].get("current_income"):
            missing_vars.append("current income")
            print("DEBUG main.py: Missing variable: current income")
        if state["data"].get("current_income", 0) > 0 and state["data"].get("super_included") is None:
            missing_vars.append("super_included")
            print("DEBUG main.py: Missing variable: super_included")

    
    # For find_cheapest
    if intent == "find_cheapest":
        if not state["data"].get("current_age"):  # Changed from user_age check
            missing_vars.append("age")
        if not state["data"].get("current_balance"):  # Changed from user_balance check
            missing_vars.append("super balance")
    
    # For compare_fees_nominated
    if intent == "compare_fees_nominated":
        if not state["data"].get("current_age"):
            missing_vars.append("age")
        if not state["data"].get("current_fund"):
            missing_vars.append("current fund")
        if not state["data"].get("current_balance"):
            missing_vars.append("super balance")
        if not state["data"].get("nominated_fund"):
            missing_vars.append("nominated fund")
    
    # For compare_fees_all
    if intent == "compare_fees_all":
        if not state["data"].get("current_age"):
            missing_vars.append("age")
        if not state["data"].get("current_fund"):
            missing_vars.append("current fund")
        if not state["data"].get("current_balance"):
            missing_vars.append("super balance")

    # For compare_balance_projection
    if intent == "compare_balance_projection":
        if not state["data"].get("current_age"):
            missing_vars.append("age")
        if not state["data"].get("current_fund"):
            missing_vars.append("current fund")
        if not state["data"].get("nominated_fund"):
            missing_vars.append("nominated fund")
        if not state["data"].get("current_balance"):
            missing_vars.append("super balance")
        if not state["data"].get("retirement_age") or state["data"].get("retirement_age") <= state["data"].get("current_age", 0):
            missing_vars.append("desired retirement age")
        if not state["data"].get("current_income"):
            missing_vars.append("current income")
        if state["data"].get("current_income", 0) > 0 and state["data"].get("super_included") is None:
            missing_vars.append("super_included")
            print("DEBUG main.py: Missing variable: super_included")
    
    # For retirement_outcome
    if intent == "retirement_outcome":
        if not state["data"].get("current_age"):
            missing_vars.append("age")
        if not state["data"].get("retirement_age") or state["data"].get("retirement_age") <= state["data"].get("current_age", 0):
            missing_vars.append("desired retirement age")
        # Only need retirement balance OR (current balance + current fund + current income)
        if not state["data"].get("retirement_balance"):
            if not state["data"].get("current_balance"):
                missing_vars.append("super balance")
            if not state["data"].get("current_fund"):
                missing_vars.append("current fund")
            if not state["data"].get("current_income"):
                missing_vars.append("current income")
            if state["data"].get("current_income", 0) > 0 and state["data"].get("super_included") is None:
                missing_vars.append("super_included")
        if not state["data"].get("retirement_income_option") and not state["data"].get("retirement_income", 0) > 0:
            missing_vars.append("retirement_income_option")

    
    # If any variables are missing, generate a structured prompt using the LLM
    if missing_vars:
        first_missing = missing_vars[0]
        # Map ambiguous names to canonical keys.
        canonical = first_missing
        if first_missing == "age":
            canonical = "current_age"
        elif first_missing == "super balance":
            canonical = "current_balance"
        elif first_missing == "current income":
            canonical = "current_income"
        elif first_missing == "desired retirement age":
            canonical = "retirement_age"
        elif first_missing == "current fund":
            canonical = "current_fund"
        elif first_missing == "nominated fund":
            canonical = "nominated_fund"
            
        # Store the current variable before setting the next missing one
        if state.get("missing_var"):
            state["data"]["last_var"] = state["missing_var"]
            
        # Save the missing variable key in state
        state["missing_var"] = canonical
    
        context = {
            "current_age": user_age if user_age > 0 else None,
            "current_balance": user_balance if user_balance > 0 else None,
            "current_income": current_income if current_income > 0 else None,
            "retirement_age": retirement_age if retirement_age > 0 else None,
            "current_fund": state["data"].get("current_fund"),  # Fixed this line
            "nominated_fund": state["data"].get("nominated_fund"),
            "super_included": state["data"].get("super_included"),
            "retirement_income_option": state["data"].get("retirement_income_option"),
            "retirement_income": state["data"].get("retirement_income"),
            "income_net_of_super": state["data"].get("income_net_of_super"),
            "after_tax_income": state["data"].get("after_tax_income"),
            "retirement_balance": state["data"].get("retirement_balance"),
            "retirement_drawdown_age": state["data"].get("retirement_drawdown_age"),
            "intent": intent,
            "is_new_intent": is_new_intent,
            "previous_var": state.get("data", {}).get("last_var")
        }
        
        print("DEBUG main.py: Context before unified response:")
        print(f"DEBUG main.py: Intent = {intent}")
        print(f"DEBUG main.py: Context = {context}")
        
        unified_message = await get_unified_variable_response(canonical, state["data"].get(canonical, ""), context, missing_vars)
        print("DEBUG main.py: Unified message:", unified_message)
        state["data"]["last_clarification_prompt"] = unified_message
        if is_new_intent and acknowledgment:
            return f"{acknowledgment}\n\n{unified_message}"
        else:
            return unified_message


    # No missing variables - process the intent
    print(f"DEBUG main.py: Processing complete intent with values - user_age: {user_age}, user_balance: {user_balance}, "
          f"current_fund: {current_fund}, current_income: {current_income}, retirement_age: {retirement_age}")
    
    # Process the intent and generate response
    print("DEBUG main.py: State before processing intent:", state)
    response = await process_intent(intent, context)
    print("DEBUG main.py: State after processing intent:", state)
    
    # Include acknowledgment if it's a new intent
    if is_new_intent:
        return f"{acknowledgment}\n\n{response}"
    return response
    print(f"DEBUG: Current stored intent: {current_state_intent}, extracted intent: {intent}, is_new_intent: {is_new_intent}")

    # ----- Branch for compare_fees_nominated -----
    if intent == "compare_fees_nominated":
        if not current_fund or not nominated_fund:
            return ("For a nominated fund comparison, please specify both your current super fund "
                    "and the fund you wish to compare it against (e.g., 'I'm in ART super and want to compare it against Aware Super').")
        
        current_rows = find_applicable_funds(df[df["FundName"].str.contains(current_fund, case=False, na=False)], user_age)
        nominated_rows = find_applicable_funds(df[df["FundName"].str.contains(nominated_fund, case=False, na=False)], user_age)
        
        if current_rows.empty:
            return f"Could not find applicable fee data for your current fund: {current_fund}."
        if nominated_rows.empty:
            return f"Could not find applicable fee data for the nominated fund: {nominated_fund}."
        
        current_breakdown = compute_fee_breakdown(current_rows.iloc[0], user_balance)
        nominated_breakdown = compute_fee_breakdown(nominated_rows.iloc[0], user_balance)
        
        user_prompt = (
            f"Data: Your current fund ({current_fund}) has total annual fees of "
            f"${current_breakdown['total_fee']:,.2f} ({(current_breakdown['total_fee']/user_balance)*100:.2f}% of your balance). "
            f"The nominated fund ({nominated_fund}) has total annual fees of "
            f"${nominated_breakdown['total_fee']:,.2f} ({(nominated_breakdown['total_fee']/user_balance)*100:.2f}% of your balance)."
        )
        system_prompt = (
            "You are a financial guru that calculates total superannuation fees for Australian consumers. "
            "Based solely on the fee information provided (do not reference performance data), "
            "compare the fees between the user's current fund and the nominated fund. "
            "Explain which fee components (investment, admin, member) contribute most to any differences, "
            "and respond EXACTLY in the following format:\n\n"
            "Between your current fund and the nominated fund, [NOMINATED FUND] charges [X]% higher fees than [CURRENT FUND], "
            "primarily due to differences in [FEE COMPONENTS].\n\n"
            "Do not include any extra commentary."
        )
        llm_answer = clean_response(ask_llm(system_prompt, user_prompt))
        return llm_answer

    # ----- Branch for compare_fees_all -----
    if intent == "compare_fees_all":
        matched_rows = find_applicable_funds(df, user_age)
        if matched_rows.empty:
            return "No applicable funds found for your age."
        
        fees = []
        for idx, row in matched_rows.iterrows():
            breakdown = compute_fee_breakdown(row, user_balance)
            total_fee = float(breakdown["total_fee"])
            fees.append((row["FundName"], total_fee))
        fees.sort(key=lambda x: x[1])
        
        cheapest = fees[0]
        expensive = fees[-1]  # Last in sorted order (highest fee)
        num_funds = len(fees)
        
        current_rank = None
        if current_fund:
            for i, (fund_name, fee) in enumerate(fees, start=1):
                if current_fund.lower() in fund_name.lower():
                    current_rank = i
                    break
        if not current_rank:
            current_rank = "undetermined"
        
        cheapest_percentage = (cheapest[1] / user_balance) * 100 if user_balance > 0 else 0.0
        expensive_percentage = (expensive[1] / user_balance) * 100 if user_balance > 0 else 0.0
        current_percentage = None
        if current_rank != "undetermined":
            # Find the fee for the current fund.
            for fund_name, fee in fees:
                if current_fund.lower() in fund_name.lower():
                    current_percentage = (fee / user_balance) * 100
                    break
        if current_percentage is None:
            current_percentage = 0.0
        
        # Build the controlled response prompt.
        user_prompt = (
            f"Data:\n"
            f"Number of funds compared: {num_funds}\n"
            f"Cheapest fund: {cheapest[0]} with an annual fee of ${cheapest[1]:,.2f} "
            f"({cheapest_percentage:.2f}% of your balance)\n"
            f"Most expensive fund: {expensive[0]} with an annual fee of ${expensive[1]:,.2f} "
            f"({expensive_percentage:.2f}% of your balance)\n"
            f"Your current fund: {current_fund if current_fund else 'N/A'} which ranks {current_rank} "
            f"among the {num_funds} funds, representing {current_percentage:.2f}% of your balance.\n\n"
            "Please use the data above."
        )
        
        system_prompt = (
            "You are a financial guru specializing in superannuation fees. "
            "Using only the fee data provided below, produce a response EXACTLY in the following format with no additional commentary:\n\n"
            "Of the [n] funds compared, [cheapest fund name] is the cheapest, with an annual fee of $[total annual fee] "
            "which is [percentage of account balance]% of your current account balance.\n\n"
            "The most expensive is [expensive fund name], with an annual fee of $[total annual fee] which is "
            "[percentage of account balance]% of your current account balance.\n\n"
            "Your account with [current fund name] ranks [ranking] among the [n] funds assessed. This represents "
            "[percentage of account balance]% of your current account balance.\n\n"
            "Then, provide a single concise sentence describing the major cause of the fee difference between your current fund "
            "and the cheapest fund (for example, whether the difference is primarily due to a higher admin fee, investment fee, or member fee)."
        )

        # Get the text response from the LLM.
        llm_answer = clean_response(ask_llm(system_prompt, user_prompt))
        print("DEBUG main.py: llm_answer length:", len(llm_answer))
        
        # Generate the chart using the helper function.
        chart_md = generate_fee_bar_chart(fees)
        print("DEBUG main.py: chart markdown length:", len(chart_md))
        
        # Combine text and chart.
        final_response = f"{llm_answer}\n\n{chart_md}"
        return final_response


    # ----- Branch for find_cheapest -----
    if intent == "find_cheapest":
        matched_rows = find_applicable_funds(df, user_age)
        if matched_rows.empty:
            return "No applicable funds found for your age."
        
        fees = []
        for idx, row in matched_rows.iterrows():
            breakdown = compute_fee_breakdown(row, user_balance)
            fees.append((row["FundName"], breakdown["total_fee"]))
        fees.sort(key=lambda x: x[1])
        
        cheapest = fees[0]
        num_funds = len(fees)
        fee_percentage = (cheapest[1] / user_balance) * 100 if user_balance > 0 else 0.0
        
        user_prompt = (
            f"Data: {num_funds} funds compared; Cheapest fund: {cheapest[0]}; "
            f"Annual fee: ${cheapest[1]:,.2f}; Fee percentage: {fee_percentage:.2f}%."
        )
        system_prompt = (
            "You are a financial guru specializing in superannuation fees. "
            "Using only the fee data provided below, respond EXACTLY in the following format (replace placeholders with actual values):\n\n"
            "Of the {num_funds} funds compared, {cheapest_fund} is the cheapest, with an annual fee of ${total_fee} "
            "which is {fee_percentage}% of your current account balance.\n\n"
            "Do not include any extra commentary or reference any funds other than the one provided in the data."
        )
        llm_answer = clean_response(ask_llm(system_prompt, user_prompt))
        return llm_answer

    # ----- Branch for project_balance -----
    if intent == "project_balance":
        print(f"DEBUG main.py: Searching for fund: {current_fund}")
        # First use LLM to match the fund name
        matched_fund = match_fund_name(current_fund, df)
        if matched_fund is None:
            return f"Could not find applicable fee data for your current fund: {current_fund}."
        print(f"DEBUG main.py: Matched fund name: {matched_fund}")
        
        # Now get the row for the matched fund
        current_fund_rows = find_applicable_funds(
            df[df["FundName"] == matched_fund],
            user_age
        )
        if current_fund_rows.empty:
            return f"Could not find applicable fee data for your current fund: {current_fund}."
        current_fund_row = current_fund_rows.iloc[0]
        
        # Assumed inputs – these might be configurable.
        wage_growth = 3.0               # e.g., 3% wage growth per annum
        employer_contribution_rate = 12.0  # e.g., 10.5% employer contribution rate
        investment_return = 8.0         # e.g., 7% gross annual investment return
        inflation_rate = 2.5            # e.g., 2.5% annual inflation rate
        
        # Call the updated projection function that recalculates fees monthly.
        projected_balance = project_super_balance(
            int(user_age), 
            int(retirement_age), 
            float(user_balance), 
            float(current_income),
            wage_growth, 
            employer_contribution_rate, 
            investment_return, 
            inflation_rate,
            current_fund_row
        )
        
        user_prompt = (
            f"Data:\n"
            f"Current age: {user_age}\n"
            f"Current balance: ${user_balance:,.0f}\n"
            f"Current income: ${current_income:,.0f}\n"
            f"Desired retirement age: {retirement_age}\n"
            f"Assumptions: Wage growth = {wage_growth}%, Employer contribution rate = {employer_contribution_rate}%, "
            f"Gross investment return = {investment_return}%, Inflation rate = {inflation_rate}%.\n"
            f"Using your current fund's fee structure (which is recalculated monthly), the projected super balance at retirement is: "
            f"${projected_balance:,.0f}."
        )
        system_prompt = (
            "You are a financial guru specializing in superannuation projections. "
            "Based solely on the data provided, produce a response EXACTLY in the following format:\n\n"
            "At retirement, you will have approximately $[projected_balance] in superannuation.\n\n"
            "Then, in one concise sentence, explain the primary factors driving this projection, "
            "specifically highlighting the impact of your current fund's fees (which are recalculated monthly), investment performance, wage growth, and inflation."
        )
        response = ask_llm(system_prompt, user_prompt)
    
    # Add acknowledgment if this is a new intent
    if intent != current_state_intent:
        return f"{acknowledgment}\n\n{response}"
    return response

    # ----- Fallback: Original compare fees behavior -----
    matched_rows = find_applicable_funds(df, user_age)
    print(f"DEBUG: matched_rows length={len(matched_rows)}")
    fee_summaries = []
    if matched_rows.empty:
        fee_summaries_str = "No applicable funds found based on your age."
    else:
        for idx, row in matched_rows.iterrows():
            breakdown = compute_fee_breakdown(row, user_balance)
            fee_summaries.append(
                f"{row['FundName']}: Investment Fee = ${breakdown['investment_fee']:,.2f}, "
                f"Admin Fee = ${breakdown['admin_fee']:,.2f}, Member Fee = ${breakdown['member_fee']:,.2f}, "
                f"Total = ${breakdown['total_fee']:,.2f}"
            )
        fee_summaries_str = "\n".join(fee_summaries)
    print("DEBUG: fee_summaries_str:\n", fee_summaries_str)
    
    system_prompt = (
        "You are a financial guru that calculates total superannuation fees for Australian consumers. "
        "Based solely on the fee information provided (do not reference performance data), "
        "compare the fees among the funds and explain which fee components contribute most to the differences, "
        "and conclude with a statement on the potential impact on retirement balance."
    )
    user_prompt = f"""
User question: {user_query}
Fee breakdown for each fund:
{fee_summaries_str}
Instructions:
1) Compare the total fee charged by the funds.
2) Explain why there is a fee difference.
3) Conclude with a statement on the potential impact on retirement balance.
"""
    llm_answer = clean_response(ask_llm(system_prompt, user_prompt))
    return llm_answer
