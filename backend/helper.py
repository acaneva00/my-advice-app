import os
from openai import OpenAI
import json
import time
import logging

# Check for OpenAI API key
if not os.environ.get("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY environment variable is not set")

# Initialize the OpenAI client - new SDK style
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
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

def ask_llm(system_prompt, user_prompt):
    print("DEBUG: Entering ask_llm()")
    print("DEBUG: system_prompt=", system_prompt)
    print("DEBUG: user_prompt=", user_prompt)
    try:
        response = openai_client.chat.completions.create(
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

def get_unified_variable_response(var_key: str, raw_value, context: dict, missing_vars: list) -> str:
    """
    Generate a unified response for variable collection that includes intent acknowledgment
    only when there's a new intent, and is more conversational and context-aware.
    """
    # Get the current intent and previous variable from context
    current_intent = context.get("intent", "unknown")
    is_new_intent = context.get("is_new_intent", False)
    previous_var = context.get("previous_var")
    
    print(f"DEBUG get_unified_variable_response: Processing var_key={var_key}, previous_var={previous_var}")
    
    # Define intent acknowledgments
    intent_messages = {
        "project_balance": "Happy to help you figure out how much super you'll have at retirement.",
        "compare_fees_nominated": "I'll help you compare the fees between your super fund and a comparison fund.",
        "compare_fees_all": "I'll analyze how your fund's fees compare to others.",
        "find_cheapest": "I'll help you find the super fund with the lowest fees.",
        "retirement_income": "I'll help you understand your retirement income options.",
        "unknown": "I'll help you with your super query."
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
        return ask_llm(system_prompt, user_prompt)
    
    # For clarifications of invalid responses, return just the clarification request
    return ask_llm(system_prompt, f"Ask for the user's {var_key} in a friendly way.")

def get_variable_description(var_key: str) -> str:
    """Helper function to get friendly variable descriptions."""
    descriptions = {
        "current_age": "current age",
        "current_balance": "current superannuation balance",
        "current_fund": "superfund",
        "current_income": "current annual income",
        "retirement_age": "desired retirement age",
        "nominated_fund": "nominated fund"
    }
    return descriptions.get(var_key, var_key)

def extract_intent_variables(user_query: str, previous_system_response: str = "") -> dict:
    """
    Uses the LLM to extract key variables from a user query and the most recent system response.
    Expected output is a JSON object with the following keys:
      - intent: one of "compare_fees_nominated", "compare_fees_all", "find_cheapest", "project_balance", "retirement_income", or "unknown"
      - current_fund: the name of the user's current super fund (if mentioned)
      - nominated_fund: the name of the fund the user wishes to compare against (if mentioned)
      - current_age: the user's age as an integer
      - current_balance: the user's super balance (in dollars) as a number
      - current_income: the user's annual income (in dollars) as a number
      - retirement_age: the user's retirement age as an integer
    For numeric values:
      - Convert k/K to thousands (e.g., 150k = 150000)
      - Convert m/M to millions (e.g., 1.5m = 1500000)
      - Remove dollar signs and commas
    If extraction fails, default values are returned.
    """
    try:
        system_prompt = (
            "You are an expert intent extractor for superannuation fee queries. "
            "Given the user's query and the most recent system response (if any), extract the following variables and output them as a valid JSON object with no extra commentary:\n\n"
            "Required keys:\n"
            " - intent: one of \"compare_fees_nominated\", \"compare_fees_all\", \"find_cheapest\", \"project_balance\", \"retirement_income\", or \"unknown\"\n"
            " - current_fund: the name of the user's current super fund, if mentioned\n"
            " - nominated_fund: the name of the fund the user wishes to compare against, if mentioned by the user or in the previous system response\n"
            " - current_age: the user's age as an integer\n"
            " - current_balance: the user's super balance (in dollars) as a number\n"
            " - current_income: the user's annual income (in dollars) as a number. Look for patterns like '$X income', 'income of $X', 'earning $X', etc.\n"
            " - retirement_age: the user's retirement age as an integer. Look for patterns like 'retiring at X', 'retirement age X', etc.\n\n"
            "For numeric values:\n"
            "- Convert k/K to thousands (e.g., 150k = 150000)\n"
            "- Convert m/M to millions (e.g., 1.5m = 1500000)\n"
            "- Remove dollar signs and commas\n\n"
            "Important instructions for resolving references:\n"
            "- If the user query contains references like 'this fund', 'that fund', or similar, look for fund names in the previous system response\n"
            "- If user mentions their fund (e.g., 'my fund', 'my super', 'my account', 'I am with') as one fund and references another fund from the previous response, properly assign current_fund and nominated_fund\n"
            "- If the user is comparing a fund mentioned in the previous response with their fund, extract both fund names correctly, properly assign current_fund and nominated_fund\n\n"
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
        
        response = openai_client.chat.completions.create(
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
                "retirement_age": 0
            }
            default_data.update(data)
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

