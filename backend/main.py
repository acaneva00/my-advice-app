import os
import re
import openai
import pandas as pd
from backend.charts import generate_fee_bar_chart
from backend.utils import (
    parse_age_from_query,
    parse_balance_from_query,
    compute_fee_breakdown,
    find_applicable_funds,
    retrieve_relevant_context,
    determine_intent,
    find_cheapest_superfund,
    project_super_balance,
    match_fund_name
)
from backend.helper import extract_intent_variables, get_unified_variable_response, ask_llm

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

def validate_response(var_name: str, user_message: str, context: dict) -> tuple[bool, float | str | None]:
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

def get_clarification_prompt(var_name: str, user_message: str, context: dict) -> str:
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
    result = ask_llm(system_prompt, user_prompt)
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

def process_compare_fees_nominated(context: dict) -> str:
    """Process compare_fees_nominated intent with the given context."""
    current_fund = context["current_fund"]
    nominated_fund = context["nominated_fund"]
    user_age = context["current_age"]
    user_balance = context["current_balance"]

    # First use the fund matcher to get exact names
    current_fund_match = match_fund_name(current_fund, df)
    nominated_fund_match = match_fund_name(nominated_fund, df)
    
    if not current_fund_match or not nominated_fund_match:
        return f"Could not find one or both funds: {current_fund}, {nominated_fund}"
        
    # Find applicable funds
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
        "'Between your current fund and the nominated fund, [NOMINATED FUND] charges [X]% higher fees than [CURRENT FUND], "
        "primarily due to differences in [FEE COMPONENTS].'\n\n"
        "Do not include any extra commentary."
    )
    return ask_llm(system_prompt, user_prompt)

def process_compare_fees_all(context: dict) -> str:
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
    
    return ask_llm(system_prompt, user_prompt)

def process_find_cheapest(context: dict) -> str:
    """Process find_cheapest intent with the given context."""
    user_age = context["current_age"]
    user_balance = context["current_balance"]
    
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
        "'Of the {num_funds} funds compared, {cheapest_fund} is the cheapest, with an annual fee of ${total_fee} "
        "which is {fee_percentage}% of your current account balance.'\n\n"
        "Do not include any extra commentary or reference any funds other than the one provided in the data."
    )
    return ask_llm(system_prompt, user_prompt)

def process_project_balance(context: dict) -> str:
    """Process project_balance intent with the given context."""
    user_age = context["current_age"]
    current_fund = context["current_fund"]
    retirement_age = context["retirement_age"]
    user_balance = context["current_balance"]
    current_income = context["current_income"]
    
    print(f"DEBUG main.py: Searching for fund: {current_fund}")
    matched_fund = match_fund_name(current_fund, df)
    if matched_fund is None:
        return f"Could not find applicable fee data for your current fund: {current_fund}."
    print(f"DEBUG main.py: Matched fund name: {matched_fund}")
    
    current_fund_rows = find_applicable_funds(
        df[df["FundName"] == matched_fund],
        user_age
    )
    if current_fund_rows.empty:
        return f"Could not find applicable fee data for your current fund: {current_fund}."
    current_fund_row = current_fund_rows.iloc[0]
    
    wage_growth = 3.0
    employer_contribution_rate = 12.0
    investment_return = 8.0
    inflation_rate = 2.5
    
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
    return ask_llm(system_prompt, user_prompt)

def process_default_comparison(context: dict) -> str:
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
    return ask_llm(system_prompt, user_prompt)

def process_intent(intent: str, context: dict) -> str:
    print(f"DEBUG process_intent: Received intent: {intent}")
    print(f"DEBUG process_intent: Received context: {context}")
    
    try:
        response = ""
        
        if intent == "compare_fees_nominated":
            response = process_compare_fees_nominated(context)
        elif intent == "compare_fees_all":
            response = process_compare_fees_all(context)
        elif intent == "find_cheapest":
            response = process_find_cheapest(context)
        elif intent == "project_balance":
            response = process_project_balance(context)
        else:
            response = process_default_comparison(context)
        
        if not response:
            response = "I apologize, but I couldn't generate a response. Please try again."
            
        print(f"DEBUG process_intent: Generated response: {response}")
        return response
        
    except Exception as e:
        print(f"DEBUG process_intent: Error processing intent: {e}")
        return "I apologize, but I encountered an error while processing your request. Please try again."

def process_query(user_query: str, previous_system_response: str = "", full_history: str = "", state: dict = None) -> str:
    print(f"DEBUG main.py: Entering process_query")
    print(f"DEBUG main.py: User query: {user_query}")
    print(f"DEBUG main.py: Previous response: {previous_system_response}")
    print(f"DEBUG main.py: Full history: {full_history}")
    print(f"DEBUG main.py: Initial state: {state}")
    
    # Ensure state is a dictionary.
    if state is None or not isinstance(state, dict):
        state = {"data": {}}

    # If the user query is empty, don't override state values.
    if not user_query.strip():
        print("DEBUG main.py: Empty user query detected; using existing state values.")
        extracted = state.get("data", {})
    else:
        # Only run intent extraction if we're not collecting variables
        if not state.get("missing_var"):
            # Run initial extraction.
            extracted = extract_intent_variables(user_query, previous_system_response)
            
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
            # If we're collecting variables, only extract for the specific variable
            extracted = {}
    
    print(f"DEBUG main.py: LLM extracted variables: {extracted}")

    
    # Handle intent and check if it's new
    intent = extracted.get("intent", "unknown")
    print("DEBUG process_query: Extracted intent:")
    print(intent)
    
    if intent == "unknown" and state.get("data", {}).get("intent"):
        intent = state["data"]["intent"]
        print("DEBUG process_query: Using stored intent:")
        print(intent)
    
    print("DEBUG process_query: Final intent:")
    print(intent)
    
    print(f"DEBUG: LLM-determined intent: {intent}")

    # Check if this is a new intent
    current_state_intent = state["data"].get("intent") if state and "data" in state else None
    is_new_intent = intent != current_state_intent
    print(f"DEBUG: Current stored intent: {current_state_intent}, extracted intent: {intent}, is_new_intent: {is_new_intent}")
    print("DEBUG process_query: Current stored intent:")
    print(current_state_intent)
    print("DEBUG process_query: Is new intent:")
    print(is_new_intent)

    
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

        # If we're in the middle of collecting variables, only update the specific variable we asked for
        if state.get("missing_var"):
            # Map the missing_var to the actual state key
            var_map = {
                "age": "current_age",
                "super balance": "current_balance",
                "current income": "current_income",
                "desired retirement age": "retirement_age",
                "current fund": "current_fund",
                "nominated fund": "nominated_fund"
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
            # We're not collecting variables, only process initial extraction
            # but NEVER update existing values that were collected through the variable collection process
            if not any(state["data"].get(key) for key in ["current_age", "current_balance", "current_income", "retirement_age"]):
                # Handle fund names separately (they are strings)
                if extracted.get("current_fund"):
                    temp_fund = extracted["current_fund"]
                    matched_fund = match_fund_name(temp_fund, df)
                    if matched_fund:
                        state["data"]["current_fund"] = matched_fund
                    else:
                        state["data"]["current_fund"] = temp_fund
                if extracted.get("nominated_fund"):
                    state["data"]["nominated_fund"] = extracted["nominated_fund"]
                
                # For numeric values, only update if they were explicitly extracted from this response
                for key in ["current_age", "current_balance", "current_income", "retirement_age"]:
                    if key in extracted and extracted[key] is not None:
                        if extracted[key] != state["data"].get(key):  # Only update if value is different
                            print(f"DEBUG main.py: Updating {key} from {state['data'].get(key)} to {extracted[key]}")
                            state["data"][key] = extracted[key]
            
        print("DEBUG main.py: Updated state after extraction:", state)
        
    # Instead of performing a final update that overwrites all the values,
    # simply update the intent in the state:
    state["data"]["intent"] = intent
    print("DEBUG main.py: Final state:", state)

    
    # Build context dict for variable requests
    context = {
        "current_age": state["data"].get("current_age", 0) or None,
        "current_balance": state["data"].get("current_balance", 0) or None,
        "current_income": state["data"].get("current_income", 0) or None,
        "retirement_age": state["data"].get("retirement_age", 0) or None,
        "current_fund": current_fund,
        "nominated_fund": nominated_fund,
        "intent": intent,
        "is_new_intent": is_new_intent,
        "previous_var": state["data"].get("last_var")  # Get the last variable we processed
    }
    
    print("DEBUG main.py: State data before context creation:", state["data"])
    print("DEBUG main.py: Created context:", context)

    # Determine missing variables based on the intent.
    print(f"DEBUG: Final values - user_age: {user_age}, user_balance: {user_balance}, intent: {intent}, current_fund: {current_fund}, nominated_fund: {nominated_fund}, current_income: {current_income}, retirement_age: {retirement_age}")
    missing_vars = []
    print("DEBUG main.py: Determining missing variables")
    print("DEBUG main.py: Current state:", state)

    # Only add to missing_vars if we don't already have a valid value
    if intent == "project_balance":
        if not state["data"].get("current_age"):
            missing_vars.append("age")
        if not state["data"].get("current_fund"):
            missing_vars.append("current fund")
        if not state["data"].get("current_balance"):
            missing_vars.append("super balance")
        if not state["data"].get("current_income"):
            missing_vars.append("current income")
        if not state["data"].get("retirement_age") or state["data"].get("retirement_age") <= state["data"].get("current_age", 0):
            missing_vars.append("desired retirement age")
    
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
            "current_fund": current_fund,
            "nominated_fund": nominated_fund,
            "intent": intent,
            "is_new_intent": is_new_intent,
            "previous_var": state.get("data", {}).get("last_var")  # Changed to get last_var from state data
        }
        
        print("DEBUG main.py: Context before unified response:")
        print(f"DEBUG main.py: Intent = {intent}")
        print(f"DEBUG main.py: Context = {context}")
        
        unified_message = get_unified_variable_response(canonical, state["data"].get(canonical, ""), context, missing_vars)
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
    response = process_intent(intent, context)
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
            "‘Between your current fund and the nominated fund, [NOMINATED FUND] charges [X]% higher fees than [CURRENT FUND], "
            "primarily due to differences in [FEE COMPONENTS].’\n\n"
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
            "‘Of the {num_funds} funds compared, {cheapest_fund} is the cheapest, with an annual fee of ${total_fee} "
            "which is {fee_percentage}% of your current account balance.’\n\n"
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
