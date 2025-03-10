import os
from openai import AsyncOpenAI
import json
import time
import logging
from backend.cashflow import calculate_income_net_of_super, calculate_after_tax_income
from backend.constants import economic_assumptions
from backend.utils import project_super_balance, match_fund_name, filter_dataframe_by_fund_name, find_applicable_funds
import pandas as pd
import re

# Check for OpenAI API key
if not os.environ.get("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable is not set")

# Initialize the OpenAI client - new SDK style
openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
from tenacity import (
    retry,
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type,
    before_log,
    after_log
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@retry(
    wait=wait_exponential(multiplier=1, min=4, max=30),
    stop=stop_after_attempt(5),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.INFO)
)

async def ask_llm(system_prompt, user_prompt):
    print("DEBUG: Entering ask_llm()")
    print("DEBUG: system_prompt=", system_prompt)
    print("DEBUG: user_prompt=", user_prompt)
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=700,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API Error: {e}")
        return "I apologize, but I'm having trouble processing your request right now. Let's try again."

async def get_unified_variable_response(var_key: str, raw_value, context: dict, missing_vars: list) -> str:
    """
    Generate a unified response for variable collection that includes intent acknowledgment
    only when there's a new intent, and is more conversational and context-aware.
    """
    # Get the current intent and previous variable from context
    current_intent = context.get("intent", "unknown")
    is_new_intent = context.get("is_new_intent", False)
    previous_var = context.get("previous_var")
    
    print(f"DEBUG get_unified_variable_response: Processing var_key={var_key}, previous_var={previous_var}")
    
    # Special handling for retirement income option
    if var_key == "retirement_income_option":
        from backend.main import get_retirement_income_options_prompt
        
        # Get the pre-calculated values from context
        retirement_balance = context.get("retirement_balance", 0)
        after_tax_income = context.get("after_tax_income", 0)
        
        # Fall back to simpler calculations if they're not available
        if retirement_balance == 0 and context.get("current_balance"):
            retirement_balance = context.get("current_balance", 0)
            if context.get("current_age") and context.get("retirement_age"):
                retirement_growth_years = context.get("retirement_age") - context.get("current_age")
                retirement_balance = retirement_balance * (1.055 ** retirement_growth_years)
        
        if after_tax_income == 0 and context.get("current_income"):
            from backend.cashflow import calculate_after_tax_income
            retirement_age = context.get("retirement_age", 65)
            current_income = context.get("current_income")
            if current_income is not None and current_income > 0 and retirement_age is not None:
                after_tax_income = calculate_after_tax_income(current_income, retirement_age)
        
        return await get_retirement_income_options_prompt(retirement_balance, after_tax_income)

    # Define intent acknowledgments
    intent_messages = {
        "project_balance": "Happy to help you figure out how much super you'll have at retirement.",
        "compare_fees_nominated": "Ok. I will compare fees between your super fund and a comparison fund.",
        "compare_fees_all": "Sure. Let me analyze how your fund fees compare to others.",
        "find_cheapest": "No problems. I will help you find the super fund with the lowest fees.",
        "compare_balance_projection": "Of course. I will compare the projected retirement balances between two funds.",
        "retirement_outcome": "Happy to help you understand how long your retirement savings might last.",
        "unknown": "I can help you with your super query."
    }
    
    system_prompt = (
        "You are a financial expert helping Australian consumers build financial confidence. "
        "Keep responses extremely concise and direct. "
        "Never mention financial advice, plans, or strategies. "
        "Focus only on gathering the specific information needed."
    )
    
    # First-time request for a variable (no raw_value)
    if raw_value is None or raw_value == 0 or raw_value == "":
        if is_new_intent:
            # For new intents, include acknowledgment and transition
            acknowledgment = intent_messages.get(current_intent, intent_messages["unknown"])
            user_prompt = (
                f"Create a concise response that:\n"
                f"1. Starts with: '{acknowledgment}'\n"
                f"2. Adds: 'I'll just need to gather a bit more information.'\n"
                f"3. Asks for {get_variable_description(var_key)}\n"
                f"Keep it clear."
            )
        else:
            # For subsequent variables, use very concise acknowledgment
            if previous_var:
                user_prompt = (
                    f"Create a response using exactly this format:\n"
                    f"Thanks for that. Next, could you kindly tell me your {get_variable_description(var_key)}?"
                )
            else:
                user_prompt = f"Could you please tell me your {get_variable_description(var_key)}?"
        
        print(f"DEBUG get_unified_variable_response: Generated prompt: {user_prompt}")
        return await ask_llm(system_prompt, user_prompt)
    
    # For clarifications of invalid responses, return just the clarification request
    return await ask_llm(system_prompt, f"Ask for the user's {var_key} in a friendly way.")

def get_variable_description(var_key: str) -> str:
    """Helper function to get friendly variable descriptions."""
    descriptions = {
        "current_age": "current age",
        "current_balance": "current superannuation balance",
        "current_fund": "superfund",
        "current_income": "current annual income",
        "retirement_age": "desired retirement age",
        "nominated_fund": "nominated fund",
        "super_included": "whether the income provided includes super contributions or if they are paid on top",
        "income_net_of_super": "income excluding super contributions",
        "retirement_balance": "expected balance at retirement",
        "retirement_income_option": "preferred income option in retirement",
        "retirement_income": "desired annual income in retirement",
        "relationship_status": "relationship status (single or couple)",
        "homeowner_status": "whether you own your home or rent",
        "cash_assets": "value of cash, savings accounts and term deposits",
        "share_investments": "value of shares and managed investments",
        "investment_properties": "value of investment properties",
        "non_financial_assets": "value of non-financial assets like vehicles, jewelry, boats, etc."
    }
    return descriptions.get(var_key, var_key)

async def extract_intent_variables(user_query: str, previous_system_response: str = "", in_variable_collection: bool = False) -> dict:
    """
    Uses the LLM to extract key variables from a user query and the most recent system response.
    Expected output is a JSON object with the following keys:
      - intent: one of "compare_fees_nominated", "compare_fees_all", "find_cheapest", "project_balance", "compare_balance_projection", "retirement_outcome", or "unknown"
      - current_fund: the name of the user's current super fund (if mentioned)
      - nominated_fund: the name of the fund the user wishes to compare against (if mentioned)
      - current_age: the user's age as an integer
      - current_balance: the user's super balance (in dollars) as a number
      - current_income: the user's annual income (in dollars) as a number
      - super_included: a boolean instructing whether or not the current_income includes or excludes employer super contributions.\n"
      - retirement_age: the user's retirement age as an integer
    For numeric values:
      - Convert k/K to thousands (e.g., 150k = 150000)
      - Convert m/M to millions (e.g., 1.5m = 1500000)
      - Remove dollar signs and commas
    If extraction fails, default values are returned.
    """
    try:
        # First, check if this is an affirmative response to a suggestion
        # If so, return a simple dictionary with just the intent
        if is_affirmative_response(user_query):
            # Check if the previous response contains our standard suggestion patterns
            suggestion_patterns = [
                "how long this super balance might last",
                "how these fee differences might affect",
                "which fund would be the cheapest",
                "compare the projected retirement balance",
                "how long your projected balance might last",
                "how different retirement income amounts might affect"
            ]
            
            if previous_system_response and any(pattern in previous_system_response.lower() for pattern in suggestion_patterns):
                # Special handling for retirement income suggestion
                retirement_income_pattern = "how different retirement income amounts might affect"
                if retirement_income_pattern in previous_system_response.lower():
                    print("DEBUG: Detected affirmative response to retirement income suggestion")
                    
                    # Check if the user already provided an income amount in their affirmative response
                    amount_match = re.search(r'(\d[\d,.]*k?m?)', user_query)
                    if amount_match:
                        from backend.main import parse_numeric_with_suffix
                        income_amount = parse_numeric_with_suffix(amount_match.group(1))
                        return {
                            "intent": "update_variable", 
                            "retirement_income": income_amount,
                            "retirement_income_option": "custom",
                            "requires_income_prompt": False
                        }
                    else:
                        # Set intent to update_variable with a special flag to request income
                        return {
                            "intent": "update_variable",
                            "requires_income_prompt": True  # Special flag to indicate we need to ask for income
                        }
                
                # For all other suggestion patterns, process as before
                for intent, connection in INTENT_CONNECTIONS.items():
                    if connection["prompt"] in previous_system_response:
                        # Return the suggested next intent
                        return {"intent": connection["primary_next"]}
                    
                # If we couldn't match a specific connection but it does look like a suggestion,
                # return a generic affirmative response
                return {"intent": "affirmative_response"}
        
        system_prompt = (
            "You are an expert intent extractor for queries regarding financial calculations and product comparisons in the Australian market. "
            "Given the user's query and the most recent system response (if any), extract the following variables and output them as a valid JSON object with no extra commentary:\n\n"
            "Required keys:\n"
            " - intent: one of the following (pay careful attention to the distinctions):\n"
            "     * \"project_balance\": when the user wants to know how much super they will have AT retirement\n"
            "     * \"retirement_outcome\": when the user asks how long their money will LAST DURING retirement, or how long it will provide income, or what income they can expect in retirement\n"
            "     * \"compare_fees_nominated\": when comparing specific named funds\n"
            "     * \"compare_fees_all\": when comparing current fund with all available funds\n"
            "     * \"find_cheapest\": when looking for the lowest fee fund\n"
            "     * \"compare_balance_projection\": when comparing projected balances between funds\n"
            "     * \"update_variable\": when the user wants to update a variable and re-run the previous calculation, like \"what if I retire at 67\" or \"what if my income was $75k\"\n"
            "     * \"calculate_age_pension\": when the user wants to estimate their age pension entitlement, or asks how much age pension they might get, or wants to understand if they qualify for age pension\n"
            "     * \"unknown\": if no other intent matches\n\n"            
            " - current_fund: the name of the user's current super fund, if mentioned\n"
            " - nominated_fund: the name of the fund the user wishes to compare against, if mentioned by the user or in the previous system response\n"
            " - current_age: the user's age as an integer\n"
            " - current_balance: the user's super balance (in dollars) as a number\n"
            " - current_income: the user's annual income (in dollars) as a number. Look for patterns like '$X income', 'income of $X', 'earning $X', etc.\n"
            " - retirement_age: the user's retirement age as an integer. Look for patterns like 'retiring at X', 'retirement age X', etc.\n"
            " - super_included: IMPORTANT - ONLY set this to true or false if the user EXPLICITLY states whether their income includes super or not. If not explicitly stated, do not update this variable.\n"
            " - income_net_of_super: the income excluding superannuation contributions\n"
            " - retirement_balance: their balance at retirement, if mentioned\n"
            " - retirement_income_option: one of \"same_as_current\", \"modest_single\", \"modest_couple\", \"comfortable_single\", \"comfortable_couple\", or \"custom\" if mentioned\n"
            " - retirement_income: a custom retirement income amount if specified\n"
            " - relationship_status: \"single\" or \"couple\" if mentioned\n"
            " - homeowner_status: true if they own their home, false if they rent or don't own\n"
            " - cash_assets: cash and term deposits\n"
            " - share_investments: value of shares and managed investments\n"
            " - investment_properties: value of investment real estate\n"
            " - non_financial_assets: a summary or total value representing the combined value of assets like vehicles, jewelry, boats, etc.)\n\n"
            "For numeric values:\n"            
            "- Convert k/K to thousands (e.g., 150k = 150000)\n"
            "- Convert m/M to millions (e.g., 1.5m = 1500000)\n"
            "- Remove dollar signs and commas\n\n"
            "Context Awareness Instructions:\n"
            "- BEFORE classifying intent, carefully examine the conversation flow:\n"
            "  1. Look at the previous system response: Was it asking a specific question?\n"
            "  2. Look at the user's current response: Is it a direct answer to that question?\n"
            "  3. If the user is clearly responding to a specific question about their status or information, maintain the current intent flow\n"
            "- For example, if the system asks 'Do you own your home or rent?' and the user responds 'I own my home', this is NOT an update_variable intent - it's simply answering the question within the current intent\n"
            "- Similarly, if the system asks about relationship status, age, or account balances, and the user provides that specific information, it's continuing the same conversation flow\n"
            "- Only classify as update_variable when the user is explicitly trying to change a previously established value, not when they're providing information for the first time\n"
            "Important instructions for resolving references:\n"
            "- If the user query contains references like 'this fund', 'that fund', or similar, look for fund names in the previous system response\n"
            "- If user mentions their fund (e.g., 'my fund', 'my super', 'my account', 'I am with') as one fund and references another fund from the previous response, properly assign current_fund and nominated_fund\n"
            "- If the user is comparing a fund mentioned in the previous response with their fund, extract both fund names correctly, properly assign current_fund and nominated_fund\n"
            "- If the user is responding to a question about retirement income options (modest_single, modest_couple, etc.) or selecting 'same_as_current', keep the intent as 'retirement_outcome'.\n"
            "- When retirement_income_option is 'custom', ALWAYS extract the numeric value mentioned in the user query (e.g., '$90k', '90000', '90k') and include it as retirement_income in your response.\n"
            "- CRITICAL: When the previous system response suggests a particular option or intent that the user might be interested in, ALWAYS:\n"
            "  1. Check the previous system response to determine and extract the new intent value\n"
            "  2. If the user response is in the affirmative, store the suggested query as a new intent\n"
            "- CRITICAL: When the previous system response asks if the user would like to change some of the inputs, like retirement age or income in retirement, ALWAYS:\n"
            "  1. If the user response is in the affirmative, and enquire as to which input they would like to change or update, then\n"
            "  2. Extract the new input and overwrite the previous value before rernning the existing intent\n"
            "- CRITICAL: When the user specifies a custom retirement income amount (e.g., 'what if I took $70k instead', 'what about $80,000 per year'), ALWAYS:\n"
            "  1. Extract the numeric value in 'retirement_income'\n"
            "  2. Set 'retirement_income_option' to \"custom\"\n"
            "- CRITICAL: When the user asks about delaying or postponing retirement (e.g., 'what if I delayed retirement by X years', 'what if I retired X years later'), ALWAYS:\n"
            "  1. The correct interpretation is to ADD the number of years to the current retirement age\n"
            "  2. Do NOT set retirement_age to be the raw number of years mentioned\n"
            "  3. For example, if current retirement age is 65 and user says 'delay by 2 years', set retirement_age to 67, not 2\n"
            "  4. NEVER set retirement_age to be younger than current_age\n"
            "CRITICAL: When responding to variable collection prompts (homeowner status, relationship status, etc.) during intent workflows, maintain the ORIGINAL intent and do not interpret as update_variable.\n"
            "CRITICAL: If the user is answering a direct question about their status or preferences as part of a collection flow, maintain the parent intent.\n"
            "CRITICAL: When the system's most recent response is asking for a specific piece of information (age, balance, etc.) and the user replies with just a value (like '20000' or '5000'), do NOT classify this as 'update_variable'.\n"
            "- If the user is asking a 'what if' question that changes a specific variable (e.g., 'what if I retire at 67', 'what if my income was $75k'), "
            "- set intent to 'update_variable' and extract the modified variable value, including updating 'retirement_income_option' to \"custom\" when appropriate, "
            "- and leave all other variables unchanged. \n\n"
            "Intent Classification Examples:\n"
            "- 'How much super will I have when I retire?' → intent: project_balance\n"
            "- 'What will my balance be at retirement?' → intent: project_balance\n"
            "- 'How long will my super last in retirement?' → intent: retirement_outcome\n"
            "- 'How many years will my super provide me income?' → intent: retirement_outcome\n"
            "- 'How long will my money last after I retire?' → intent: retirement_outcome\n"
            "- 'Will my super last until I'm 90?' → intent: retirement_outcome\n"
            "- 'What if I worked until I was 67' → intent: update_variable\n"
            "- 'Let's say I took $70k as income instead' → intent: update_variable, retirement_income: 70000, retirement_income_option: \"custom\"\n"
            "Context Response Examples:\n"
            "- System: 'Could you tell me your current age?' User: '68' → NOT update_variable (maintain current intent)\n"
            "- System: 'Are you single or in a relationship?' User: 'Single' → NOT update_variable (maintain current intent)\n"
            "- System: 'Do you own your home or rent?' User: 'I own my home' → NOT update_variable (maintain current intent)\n"
            "- System: 'Based on your super of $100,000, you'll have $500,000 at retirement' User: 'What if my super was $200,000?' → IS update_variable\n"
            "- System: 'Your retirement age is 67' User: 'Actually, I want to retire at 65' → IS update_variable\n"
            "Special Variable Collection Instructions:\n"
            "- For homeowner status questions, when the user responds with phrases like 'I own my home', 'own home', 'homeowner', etc., this is NEVER a new intent - it's answering the specific question about homeownership\n"
            "- The homeowner status is particularly important for calculating government benefits like Age Pension\n"
            "- When asking about homeowner status, the conversation is continuing the SAME intent flow (e.g., 'calculate_age_pension')\n"
            "- Similarly, when the system asks about relationship status and the user says 'single' or 'couple', this is continuing the same intent, not starting a new one\n"
            "- CRITICAL: If the previous system message asked 'do you own your home' or similar homeownership question, and the user responds with 'I own my home' or similar, NEVER classify this as 'retirement_outcome' or 'update_variable' - it should be 'unknown' to maintain the current intent\n"
            "Return a valid JSON object."
        )
        
        # If a previous system response exists, clearly separate it from the user query.
        if previous_system_response:
            user_prompt = f"User query: {user_query}\n\nPrevious system response: {previous_system_response}"
        else:
            user_prompt = f"User query: {user_query}"
        
        print("DEBUG intent_extractor.py: Attempting API call to OpenAI with context:")
        print("DEBUG intent_extractor.py: user_prompt =", user_prompt)
        print("DEBUG intent_extractor.py: Full prompt for variable extraction:")
        print(user_prompt)
        
        response = await openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=250,
            temperature=0
        )
        print("DEBUG intent_extractor.py: Successfully received API response")
        
        answer = response.choices[0].message.content.strip()
        print("DEBUG intent_extractor.py: Raw answer from API:", answer)
        try:
            data = json.loads(answer)
            # Provide default values for any missing keys.
            default_data = {
                "intent": "unknown",
                "current_fund": None,
                "nominated_fund": None,
                "current_age": 0,
                "current_balance": 0,
                "current_income": 0,
                "retirement_age": 0,
                "super_included": None,
                "income_net_of_super": 0
            }
            default_data.update(data)
            
            # Add the check for direct responses to questions
            if default_data.get("intent") == "update_variable" and previous_system_response:
                # Check if this looks like a response to a variable collection prompt
                prompt_lower = previous_system_response.lower()
                is_collection_prompt = any(phrase in prompt_lower for phrase in 
                                        ["could you tell me", "please provide", "what is your", 
                                        "let me know", "are you single", "do you own", "relationship status"])
                
                if is_collection_prompt:
                    direct_response = False
                    
                    # Call the async function if it's a complex response that needs LLM analysis
                    if len(user_query.split()) > 3:  # For longer responses, use LLM
                        direct_response = await is_direct_response_to_question(user_query, previous_system_response)
                    else:  # For shorter responses, use heuristics
                        # Check for simple yes/no or direct answers
                        simple_answers = ["yes", "no", "own", "rent", "single", "couple", "married"]
                        direct_response = any(answer.lower() in user_query.lower() for answer in simple_answers)
                    
                    if direct_response or is_collection_prompt:
                        print("DEBUG intent_extractor.py: Detected direct response to collection question. Not treating as update_variable.")
                        default_data["intent"] = "unknown"  # Don't change the current intent flow
            
            print(f"DEBUG helper.py: Final extracted data before returning: {default_data}")
            return default_data
        except Exception as e:
            print("DEBUG intent_extractor.py: Error parsing JSON:", e)
            return {
                "intent": "unknown",
                "current_fund": None,
                "nominated_fund": None,
                "current_age": 0,
                "current_balance": 0,
                "current_income": 0,
                "retirement_age": 0
            }
    except Exception as e:
        print(f"DEBUG intent_extractor.py: Unexpected error: {e}")
        raise

async def is_direct_response_to_question(user_query: str, previous_response: str) -> bool:
    """Determines if the user query is directly answering a question in the previous response."""
    if not previous_response:
        return False
        
    system_prompt = (
        "You are analyzing conversation flow. Given a previous system message and user response, "
        "determine if the user is directly answering a question that was asked in the previous message. "
        "Answer with ONLY 'yes' or 'no'."
    )
    
    user_prompt = (
        f"Previous system message: \"{previous_response}\"\n"
        f"User response: \"{user_query}\"\n\n"
        f"Is the user directly answering a specific question posed in the previous message? "
        f"Consider if the previous message was asking for specific information like age, "
        f"relationship status, homeowner status, account balances, etc."
    )
    
    result = await ask_llm(system_prompt, user_prompt)
    return result.lower().strip() == 'yes'

# Define the connections between intents as a global constant
INTENT_CONNECTIONS = {
    "project_balance": {
        "primary_next": "retirement_outcome",
        "prompt": "Would you like to know how long this super balance might last in retirement? Or is there something else I can help you with?"
    },
    "compare_fees_nominated": {
        "primary_next": "compare_balance_projection",
        "prompt": "Would you like to see how these fee differences might affect your retirement balance over time? Or is there something else I can help you with?"
    },
    "compare_fees_all": {
        "primary_next": "find_cheapest",
        "prompt": "Would you like to know which fund would be the cheapest for your specific situation? Or is there something else I can help you with?"
    },
    "find_cheapest": {
        "primary_next": "compare_fees_nominated",
        "prompt": "Would you like to compare fees between this fund and your current fund? Or is there something else I can help you with?"
    },
    "compare_balance_projection": {
        "primary_next": "retirement_outcome",
        "prompt": "Would you like to know how long your projected balance might last in retirement? Or is there something else I can help you with?"
    },
    "retirement_outcome": {
        "primary_next": "update_variable",
        "prompt": "Would you like to see how different retirement income amounts might affect how long your super lasts? Or is there something else I can help you with?"
    },
}

def get_next_intent_info(current_intent):
    """
    Get the next intent and prompt for a given intent.
    Returns a tuple of (next_intent, suggestion_prompt).
    """
    connection = INTENT_CONNECTIONS.get(current_intent)
    if not connection:
        # Default suggestion if no specific connection exists
        return ("unknown", "Is there anything else I can help you with regarding your superannuation?")
    
    return (connection["primary_next"], connection["prompt"])
def get_suggestion_prompt(current_intent):
    """
    Get just the suggestion prompt for a given intent.
    """
    _, prompt = get_next_intent_info(current_intent)
    return prompt

def is_affirmative_response(user_message):
    """
    Check if the user's message is an affirmative response
    to proceed with the suggested next intent.
    """
    affirmative_phrases = [
        "yes", "yeah", "yep", "sure", "ok", "okay", "proceed", 
        "go ahead", "let's do it", "let's go", "sounds good", 
        "please do", "that would be good", "i'd like that",
        "tell me", "show me", "continue"
    ]
    
    # Clean up the message: lowercase and remove punctuation
    cleaned_message = user_message.lower().strip()
    for char in ".,!?":
        cleaned_message = cleaned_message.replace(char, "")
    
    # Check if any affirmative phrase is in the cleaned message
    for phrase in affirmative_phrases:
        if phrase in cleaned_message or cleaned_message == phrase:
            return True
    
    return False

async def handle_next_intent_transition(user_message, context):
    """
    Handle the transition to the next intent if the user's response is affirmative.
    Returns updated context with the new intent or None if no transition should occur.
    """
    # Check if context has a suggested next intent
    if not context.get("suggested_next_intent"):
        return None
    
    # Check if the user's response is affirmative
    if not is_affirmative_response(user_message):
        return None
    
    # Prepare for transition to the suggested next intent
    next_intent = context["suggested_next_intent"]
    
    # Create updated context with new intent
    updated_context = context.copy()
    
    # Store the original intent for reference
    if context.get("intent") and context.get("intent") != "unknown":
        updated_context["previous_intent"] = context["intent"]
        
    # Set the new intent
    updated_context["intent"] = next_intent
    
    # Special handling for retirement income modeling
    if context.get("intent") == "retirement_outcome" and next_intent == "update_variable":
        updated_context["needs_retirement_income_prompt"] = True
        updated_context["original_intent"] = "retirement_outcome"

    # Remove the suggestion now that we're acting on it
    if "suggested_next_intent" in updated_context:
        del updated_context["suggested_next_intent"]
    
    return updated_context

def update_calculated_values(state):
    """Calculate and update derived values based on available data in state"""
    data = state.get("data", {})
    
    # Calculate income_net_of_super if prerequisites are met
    if data.get("current_income") and data.get("super_included") is not None:
        employer_rate = economic_assumptions["EMPLOYER_CONTRIBUTION_RATE"]
        data["income_net_of_super"] = calculate_income_net_of_super(
            data["current_income"], data["super_included"], employer_rate)
    
    # Calculate after_tax_income if prerequisites are met
    if data.get("current_income") and data.get("current_age"):
        data["after_tax_income"] = calculate_after_tax_income(
            data["current_income"], data["current_age"])
    
    # Calculate retirement_balance if prerequisites are met
    if (data.get("current_age") and data.get("retirement_age") and 
        data.get("current_balance") and data.get("income_net_of_super") and 
        data.get("current_fund")):
    
        # Get economic assumptions
        wage_growth = economic_assumptions["WAGE_GROWTH"]
        employer_rate = economic_assumptions["EMPLOYER_CONTRIBUTION_RATE"]
        investment_return = economic_assumptions["INVESTMENT_RETURN"]
        inflation_rate = economic_assumptions["INFLATION_RATE"]
        
        # Get fund data
        df = pd.read_csv("superfunds.csv")
        matched_fund = match_fund_name(data["current_fund"], df)
        if matched_fund:
            # Get the fund row
            current_fund_rows = find_applicable_funds(
                filter_dataframe_by_fund_name(df, matched_fund, exact_match=True),
                data["current_age"]
            )
            if not current_fund_rows.empty:
                # Calculate projected retirement balance
                projected_balance = project_super_balance(
                    int(data["current_age"]),
                    int(data["retirement_age"]),
                    float(data["current_balance"]),
                    float(data["income_net_of_super"]),
                    wage_growth,
                    employer_rate,
                    investment_return,
                    inflation_rate,
                    current_fund_rows.iloc[0]
                )
                data["retirement_balance"] = projected_balance
            else:
                # Simple fallback if fund row not found
                net_annual_return = investment_return - inflation_rate
                annual_growth_factor = 1 + (net_annual_return / 100)
                retirement_growth_years = data["retirement_age"] - data["current_age"]
                data["retirement_balance"] = data["current_balance"] * (annual_growth_factor ** retirement_growth_years)
        else:
            # Simple fallback if fund not matched
            net_annual_return = investment_return - inflation_rate
            annual_growth_factor = 1 + (net_annual_return / 100)
            retirement_growth_years = data["retirement_age"] - data["current_age"]
            data["retirement_balance"] = data["current_balance"] * (annual_growth_factor ** retirement_growth_years)
    
    # Calculate retirement_drawdown_age if prerequisites are met  
    if (data.get("retirement_balance") and data.get("retirement_age") and 
        (data.get("retirement_income_option") or data.get("retirement_income"))):
    
        # Get retirement standards and economic assumptions
        from backend.utils import get_asfa_standards, calculate_retirement_drawdown
        asfa_standards = get_asfa_standards()
        retirement_investment_return = economic_assumptions["RETIREMENT_INVESTMENT_RETURN"]
        inflation_rate = economic_assumptions["INFLATION_RATE"]
        
        # Determine annual income based on retirement_income_option
        annual_retirement_income = 0
        retirement_income_option = data.get("retirement_income_option")
        
        if retirement_income_option == "same_as_current" and data.get("after_tax_income"):
            annual_retirement_income = data["after_tax_income"]
        elif retirement_income_option in ["modest_single", "modest_couple", "comfortable_single", "comfortable_couple"]:
            annual_retirement_income = asfa_standards[retirement_income_option]["annual_amount"]
        elif data.get("retirement_income") and data["retirement_income"] > 0:
            annual_retirement_income = data["retirement_income"]
        
        # Only calculate if we have a valid income amount
        if annual_retirement_income > 0:
            depletion_age = calculate_retirement_drawdown(
                float(data["retirement_balance"]),
                int(data["retirement_age"]),
                float(annual_retirement_income),
                retirement_investment_return,
                inflation_rate
            )
            data["retirement_drawdown_age"] = depletion_age
    
    # Update the state with calculated values
    state["data"] = data
    return state

async def generate_income_update_request():
    """Generate a request for the user to specify a retirement income amount"""
    system_prompt = (
        "You are a friendly financial expert helping with retirement planning. "
        "Create a brief, clear request asking what retirement income amount the user would like to model. "
        "Keep it concise and conversational."
    )
    
    user_prompt = (
        "Generate a simple question asking what retirement income amount the user would like to model. "
        "For example: 'What annual retirement income amount would you like to model?'"
    )
    
    return await ask_llm(system_prompt, user_prompt)