import gradio as gr
from backend.main import process_query, parse_numeric_with_suffix, validate_response, get_clarification_prompt, df
from backend.helper import ask_llm, get_unified_variable_response, update_calculated_values, extract_intent_variables
from backend.utils import match_fund_name
from backend.cashflow import calculate_income_net_of_super, calculate_after_tax_income
import json
import re
import os
import httpx
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Debug: Check available Supabase-related environment variables
print("Available environment variables:", [k for k in os.environ.keys() if "SUPABASE" in k])

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # Make sure this matches your .env file

# Check if variables are loaded properly
if not SUPABASE_URL or not SUPABASE_KEY:
    print("Warning: Supabase credentials not found in environment variables")
    print(f"SUPABASE_URL: {'Found' if SUPABASE_URL else 'Missing'}")
    print(f"SUPABASE_KEY: {'Found' if SUPABASE_KEY else 'Missing'}")
    # Set fallback values to prevent errors (won't actually connect to Supabase)
    SUPABASE_URL = SUPABASE_URL or "http://localhost"
    SUPABASE_KEY = SUPABASE_KEY or "dummy-key"

# Initialize HTTP client for Supabase
supabase_client = httpx.AsyncClient(
    base_url=SUPABASE_URL,
    headers={
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json"
    }
)

# User session management
active_sessions = {}

async def get_or_create_user(email, first_name=None, last_name=None):
    """
    Get existing user or create a new one in Supabase
    """
    try:
        # First check if user exists by email
        response = await supabase_client.get(
            f"/rest/v1/users?email=eq.{email}&select=*"
        )
        
        if response.status_code == 200 and len(response.json()) > 0:
            return response.json()[0]
        
        # User doesn't exist, create a new one
        # First create auth user
        auth_response = await supabase_client.post(
            "/auth/v1/signup",
            json={
                "email": email,
                "password": f"temp_{os.urandom(8).hex()}"  # Generate random password - user should reset
            }
        )
        
        if auth_response.status_code != 200:
            raise Exception(f"Failed to create auth user: {auth_response.text}")
        
        user_id = auth_response.json()["user"]["id"]
        
        # Create user record
        user_response = await supabase_client.post(
            "/rest/v1/rpc/create_user_with_profile",
            json={
                "user_uuid": user_id,
                "user_email": email,
                "first_name": first_name or "Anonymous",
                "last_name": last_name or "User",
                "phone": None,
                "privacy_version": "1.0",
                "terms_version": "1.0"
            }
        )
        
        if user_response.status_code != 200:
            raise Exception(f"Failed to create user profile: {user_response.text}")
        
        # Get the created user
        new_user_response = await supabase_client.get(
            f"/rest/v1/users?id=eq.{user_id}&select=*"
        )
        
        if new_user_response.status_code != 200:
            raise Exception("Failed to retrieve created user")
            
        return new_user_response.json()[0]
    
    except Exception as e:
        print(f"Error in get_or_create_user: {e}")
        # Return a default user object if we can't connect to Supabase
        return {"id": str(uuid.uuid4()), "email": email}

async def create_chat_session(user_id):
    """
    Create a new chat session in Supabase
    """
    try:
        response = await supabase_client.post(
            "/rest/v1/rpc/find_or_create_chat_session",
            json={
                "p_user_id": user_id,
                "p_platform": "webchat"
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to create chat session: {response.text}")
            
        return response.json()
    
    except Exception as e:
        print(f"Error in create_chat_session: {e}")
        # Return a default session ID if we can't connect to Supabase
        return "local-session"

async def record_chat_message(session_id, sender_type, content):
    """
    Record a chat message in Supabase
    """
    try:
        response = await supabase_client.post(
            "/rest/v1/rpc/record_chat_message",
            json={
                "p_session_id": session_id,
                "p_sender_type": sender_type,
                "p_content": content
            }
        )
        
        if response.status_code != 200:
            print(f"Warning: Failed to record message: {response.text}")
    
    except Exception as e:
        print(f"Error in record_chat_message: {e}")
        # Non-blocking - continue even if we can't record the message

async def update_user_financial_profile(user_id, state_data):
    """
    Update the user's financial profile in Supabase
    """
    try:
        response = await supabase_client.post(
            "/rest/v1/rpc/update_financial_profile",
            json={
                "p_user_id": user_id,
                "p_current_age": state_data.get("current_age"),
                "p_current_balance": state_data.get("current_balance"),
                "p_current_income": state_data.get("current_income"),
                "p_retirement_age": state_data.get("retirement_age"),
                "p_current_fund": state_data.get("current_fund"),
                "p_super_included": state_data.get("super_included"),
                "p_retirement_income_option": state_data.get("retirement_income_option"),
                "p_retirement_income": state_data.get("retirement_income")
            }
        )
        
        if response.status_code != 200:
            print(f"Warning: Failed to update profile: {response.text}")
    
    except Exception as e:
        print(f"Error in update_user_financial_profile: {e}")
        # Non-blocking - continue even if we can't update the profile

async def record_user_intent(user_id, session_id, intent_type, state_data):
    """
    Record the user's intent in Supabase
    """
    try:
        if not intent_type or intent_type == "unknown":
            return
            
        # Prepare intent data
        intent_data = {
            "current_age": state_data.get("current_age"),
            "current_balance": state_data.get("current_balance"),
            "current_income": state_data.get("current_income"),
            "retirement_age": state_data.get("retirement_age"),
            "current_fund": state_data.get("current_fund"),
            "super_included": state_data.get("super_included"),
            "income_net_of_super": state_data.get("income_net_of_super"),
            "after_tax_income": state_data.get("after_tax_income"),
            "retirement_balance": state_data.get("retirement_balance"),
            "retirement_income": state_data.get("retirement_income"),
            "retirement_income_option": state_data.get("retirement_income_option"),
            "retirement_drawdown_age": state_data.get("retirement_drawdown_age")
        }
        
        response = await supabase_client.post(
            "/rest/v1/rpc/record_user_intent",
            json={
                "p_user_id": user_id,
                "p_session_id": session_id,
                "p_intent_type": intent_type,
                "p_intent_data": intent_data
            }
        )
        
        if response.status_code != 200:
            print(f"Warning: Failed to record intent: {response.text}")
    
    except Exception as e:
        print(f"Error in record_user_intent: {e}")
        # Non-blocking - continue even if we can't record the intent

async def extract_variable_from_response(last_prompt: str, user_message: str, context: dict, missing_var: str) -> dict:
    """
    Extract a specific variable from the user's response based on what was asked.
    Returns a dictionary with 'variable' and 'value' keys.
    """
    # Map canonical variables to expected LLM output
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
    
    # Define which variables should be treated as numbers
    numeric_vars = {
        "current_age": "int",
        "current_balance": "float",
        "current_income": "float",
        "retirement_age": "int",
        "income_net_of_super": "flaot",
        "after_tax_income": "float",	
        "retirement_balance": "float",
        "retirement_income": "float",
        "retirement_drawdown_age": "int"
    }
    
    # Define which variables should be treated as booleans
    boolean_vars = ["super_included"]

    expected_var = var_map.get(missing_var, missing_var)

    print("DEBUG extract_variable_from_response: Missing variable:")
    print(missing_var)
    print("DEBUG extract_variable_from_response: Expected variable:")
    print(expected_var)

    system_prompt = (
        "You are a friendly, professional financial expert. Based on the following context and user response, "
        "extract ONLY the value for the specific variable that was asked for in the last prompt. "
        f"The expected variable is: {expected_var}\n"
        "Return your answer as a JSON object with two keys: 'variable' (the expected variable name) "
        "and 'value' (the raw value as provided by the user)."
    )

    combined_prompt = (
        f"Last question asked: {last_prompt}\n"
        f"User's answer: {user_message}\n"
        f"Expected variable: {expected_var}\n"
        "Extract ONLY the value for this specific variable. "
        "Output as a JSON object with keys 'variable' and 'value'."
    )
        
    print("DEBUG extract_variable_from_response: Last prompt:")
    print(last_prompt)
    print("DEBUG extract_variable_from_response: User's answer:")
    print(user_message)

    response = await ask_llm(system_prompt, combined_prompt)
    print("DEBUG extract_variable_from_response: Raw LLM response:")
    print(response)

    try:
        data = json.loads(response)
        print("DEBUG extract_variable_from_response: Parsed LLM response:")
        print(data)
        
        # Ensure the extracted variable matches what we asked for
        if data.get('variable') != expected_var:
            print(f"DEBUG: Extracted variable {data.get('variable')} doesn't match expected {expected_var}")
            return {'variable': expected_var, 'value': None}
        
        # Convert values to appropriate type
        raw_value = data.get('value')
        if raw_value and expected_var in numeric_vars:
            try:
                if isinstance(raw_value, str):
                    # Remove any currency symbols and commas
                    clean_value = raw_value.replace('$', '').replace(',', '').strip().lower()
                    
                    # Handle suffixes for monetary values
                    if expected_var in ['current_balance', 'current_income']:
                        if clean_value.endswith('k'):
                            numeric_value = float(clean_value[:-1]) * 1000
                        elif clean_value.endswith('m'):
                            numeric_value = float(clean_value[:-1]) * 1000000
                        else:
                            numeric_value = float(clean_value)
                    else:
                        # For ages, just convert to integer
                        numeric_value = int(float(clean_value))
                    
                    # Convert to int if required
                    if numeric_vars[expected_var] == "int":
                        numeric_value = int(numeric_value)
                    
                    data['value'] = numeric_value
                    print(f"DEBUG: Converted {raw_value} to {numeric_value} for {expected_var}")
                    
            except ValueError:
                print(f"DEBUG: Could not convert value {raw_value} to number")
                return {'variable': expected_var, 'value': None}
        
        # Add handling for boolean responses
        if expected_var in boolean_vars:
            if isinstance(raw_value, str):
                raw_value = raw_value.lower().strip()
                if raw_value in ["yes", "true", "included", "includes", "part of", "package"]:
                    data['value'] = True
                elif raw_value in ["no", "false", "not included", "separate", "on top", "additional"]:
                    data['value'] = False
                else:
                    # Try to use LLM to interpret ambiguous responses
                    interpret_prompt = f"Does this response indicate that super is INCLUDED in the income amount or PAID ON TOP? Response: '{raw_value}'"
                    interpretation = await ask_llm("You are a boolean interpreter. Answer with ONLY 'included' or 'on top'.", interpret_prompt)
                    data['value'] = interpretation.lower().strip() == "included"
            elif isinstance(raw_value, bool):
                data['value'] = raw_value

        # Handle retirement income option
        if expected_var == "retirement_income_option":
            if isinstance(raw_value, str):
                raw_value = raw_value.lower().strip()
                # Check for numeric values like "$90k" directly in the response
                if "$" in raw_value or re.search(r'\d+k?', raw_value):
                    data['value'] = "custom"
                    amount_match = re.search(r'(\d[\d,.]*k?m?)', raw_value)
                    if amount_match:
                        from backend.main import parse_numeric_with_suffix
                        custom_amount = parse_numeric_with_suffix(amount_match.group(1))
                        print(f"DEBUG extract_variable_from_response: Extracted custom amount: {custom_amount}")
                        # Return both the option and the amount
                        return {'variable': expected_var, 'value': "custom", 'retirement_income': custom_amount}
                elif any(x in raw_value for x in ["same", "current", "as now", "as my current"]):
                    data['value'] = "same_as_current"
                elif "modest single" in raw_value or "option 2" in raw_value or "option2" in raw_value or raw_value == "2":
                    data['value'] = "modest_single"
                elif "modest couple" in raw_value or "option 3" in raw_value or "option3" in raw_value or raw_value == "3":
                    data['value'] = "modest_couple"
                elif "comfortable single" in raw_value or "option 4" in raw_value or "option4" in raw_value or raw_value == "4":
                    data['value'] = "comfortable_single"
                elif "comfortable couple" in raw_value or "option 5" in raw_value or "option5" in raw_value or raw_value == "5":
                    data['value'] = "comfortable_couple"
                elif any(x in raw_value for x in ["custom", "my own", "specific", "option 6", "option6"]) or raw_value == "6":
                    data['value'] = "custom"
                    # Try to extract a custom amount if provided
                    amount_match = re.search(r'(\d[\d,.]*k?m?)', user_message)
                    if amount_match:
                        from backend.main import parse_numeric_with_suffix
                        custom_amount = parse_numeric_with_suffix(amount_match.group(1))
                        print(f"DEBUG extract_variable_from_response: Extracted custom amount: {custom_amount}")
                        return {'variable': expected_var, 'value': "custom", 'retirement_income': custom_amount}
                else:
                    # Try to use LLM to interpret ambiguous responses
                    interpret_prompt = f"Which retirement income option does this response most closely match: 'same_as_current', 'modest_single', 'modest_couple', 'comfortable_single', 'comfortable_couple', or 'custom'? Response: '{raw_value}'"
                    interpretation = await ask_llm("You are an option interpreter. Answer with ONLY one of these options: 'same_as_current', 'modest_single', 'modest_couple', 'comfortable_single', 'comfortable_couple', or 'custom'.", interpret_prompt)
                    data['value'] = interpretation.lower().strip()

        return data
    except json.JSONDecodeError as e:
        print("DEBUG extract_variable_from_response: Error parsing JSON:", e)
        return {}
    except Exception as e:
        print("DEBUG extract_variable_from_response: Unexpected error:", e)
        return {}
        
# Modified chat function with Supabase integration
async def chat_fn(user_message, history, state, user_info=None):
    print(f"\n\n==== NEW MESSAGE RECEIVED: {user_message} ====\n\n")
    print(f"DEBUG app.py: Entering chat_fn")
    print(f"DEBUG app.py: User message: {user_message}")
    print(f"DEBUG app.py: Current state: {state}")
    
    # Initialize state if needed
    if state is None or not isinstance(state, dict):
        state = {"data": {"super_included": None}, "missing_var": None}
    if history is None:
        history = []
    
    # Get or create user if user_info is provided
    user_id = "local-user"
    session_id = "local-session"
    
    if user_info and "email" in user_info:
        user = await get_or_create_user(
            user_info["email"],
            user_info.get("first_name"),
            user_info.get("last_name")
        )
        user_id = user["id"]
        
        # Get the user's active session or create a new one
        if user_id not in active_sessions:
            session_id = await create_chat_session(user_id)
            active_sessions[user_id] = session_id
        else:
            session_id = active_sessions[user_id]

    # For Gradio 3.x, history must be a list of tuples (user_message, bot_response)
    # We'll convert our internal dictionary-based messages to this format when returning
    
    # Build internal history for processing in the expected dictionary format
    internal_history = []
    for user_msg, assistant_msg in history:
        if user_msg:
            internal_history.append({"role": "user", "content": user_msg})
        if assistant_msg:
            internal_history.append({"role": "assistant", "content": assistant_msg})
    
    # Add the current user message to our internal history
    internal_history.append({"role": "user", "content": user_message})
    
    # If we are waiting for a specific missing variable
    if state.get("missing_var"):
        var_marker = state.pop("missing_var")
        print(f"DEBUG app.py: Processing missing var: {var_marker}")

        var_map = {
            "age": "current_age",
            "super balance": "current_balance",
            "current income": "current_income",
            "desired retirement age": "retirement_age",
            "current fund": "current_fund",
            "nominated fund": "nominated_fund"
        }
    
        expected_var = var_map.get(var_marker, var_marker)
        print(f"DEBUG app.py: Mapped {var_marker} to {expected_var}")
        
        # Create context for extraction
        context = {
            "current_age": state["data"].get("current_age", 0),
            "current_balance": state["data"].get("current_balance", 0),
            "current_income": state["data"].get("current_income", 0),
            "retirement_age": state["data"].get("retirement_age", 0),
            "current_fund": state["data"].get("current_fund"),
            "intent": state["data"].get("intent"),
            "is_new_intent": False,  # Not a new intent when processing a variable
            "previous_var": state["data"].get("last_var")  # Include previous variable
        }
        
        last_prompt = state["data"].get("last_clarification_prompt", "")
        
        # Extract variable from response
        extraction = await extract_variable_from_response(last_prompt, user_message, context, var_marker)
        print(f"DEBUG app.py: LLM extraction result: {extraction}")
        
        if extraction.get("variable") and extraction.get("value") is not None:
            var_key = extraction["variable"]
            raw_value = extraction["value"]

            # Store the previous variable before updating with new one
            state["data"]["last_var"] = var_marker
            print(f"DEBUG app.py: Stored last_var: {var_marker}")

            # Handle fund name standardization
            if var_key in ["current_fund", "nominated_fund"]:
                standardized = match_fund_name(raw_value, df)
                if standardized:
                    raw_value = standardized

            # Update state with the raw value
            state["data"][var_key] = raw_value
            print(f"DEBUG app.py: Updated state with {var_key}: {raw_value}")

            # If we also extracted a retirement income amount, save that too
            if extraction.get("retirement_income") is not None:
                state["data"]["retirement_income"] = extraction["retirement_income"]
                print(f"DEBUG app.py: Also updated state with retirement_income: {extraction['retirement_income']}")

            # Update calculated values based on available data
            state = update_calculated_values(state)
            print(f"DEBUG app.py: Updated calculated values in state: {state}")
            
            # Format value for acknowledgment
            formatted_value = f"${raw_value:,.0f}" if var_key in ["current_balance", "current_income"] else raw_value

            # Check for remaining missing variables
            missing_vars = []
            if state["data"].get("current_age", 0) <= 0:
                missing_vars.append("age")
            if state["data"].get("current_balance", 0) <= 0:
                missing_vars.append("super balance")
            if state["data"].get("intent") not in ["find_cheapest"] and not state["data"].get("current_fund"):
                missing_vars.append("current fund")
            if state["data"].get("intent") == "compare_fees_nominated" and not state["data"].get("nominated_fund"):
                missing_vars.append("nominated fund")
            if state["data"].get("intent") in ["project_balance", "compare_balance_projection"]:
                if state["data"].get("retirement_age", 0) <= state["data"].get("current_age", 0):
                    missing_vars.append("desired retirement age")
                if state["data"].get("current_income", 0) <= 0:
                    missing_vars.append("current income")
            if state["data"].get("current_income", 0) > 0 and state["data"].get("super_included") is None:
                missing_vars.append("super_included")
            
            # If there are still missing variables, request the next one
            if missing_vars:
                next_var = missing_vars[0]
                # Update context with latest state
                context.update({
                    "current_age": state["data"].get("current_age", 0),
                    "current_balance": state["data"].get("current_balance", 0),
                    "current_income": state["data"].get("current_income", 0),
                    "retirement_age": state["data"].get("retirement_age", 0),
                    "current_fund": state["data"].get("current_fund"),
                    "nominated_fund": state["data"].get("nominated_fund"),
                    "intent": state["data"].get("intent"),
                    "previous_var": state["data"].get("last_var")
                })
                unified_message = await get_unified_variable_response(next_var, None, context, missing_vars)
                state["data"]["last_clarification_prompt"] = unified_message
                state["missing_var"] = next_var
                
                # Add the current conversation exchange to history in Gradio format
                history.append((user_message, unified_message))
            else:
                # All required variables collected, process the complete query
                previous_system_response = next((msg["content"] for msg in reversed(internal_history) if msg["role"] == "assistant"), "")
                full_history = " ".join(msg["content"] for msg in internal_history if msg["role"] == "user")
                
                print("DEBUG: Processing complete query after collecting all variables")
                
                answer = await process_query(user_message, previous_system_response, full_history, state)
                
                print(f"DEBUG: Got answer: {answer}")

                if answer:
                    # Record messages in Supabase
                    await record_chat_message(session_id, "user", user_message)
                    await record_chat_message(session_id, "assistant", answer)
                    
                    # Update user profile with collected data
                    if state.get("data"):
                        await update_user_financial_profile(user_id, state["data"])
                        
                        # Record intent if it exists and changed
                        if state["data"].get("intent") and state["data"].get("intent") != "unknown":
                            await record_user_intent(
                                user_id,
                                session_id,
                                state["data"]["intent"],
                                state["data"]
                            )
                    
                    print("DEBUG: Adding final answer to history")
                    # Create a new list with the same content as history to avoid reference issues
                    new_history = [(msg1, msg2) for msg1, msg2 in history]
                    # Append the new exchange (ensure it's in tuple format)
                    new_history.append((user_message, answer))
                    # Replace history with new_history
                    history = new_history
                    print(f"DEBUG: Final history length: {len(history)}")
                else:
                    # Handle error case
                    error_message = "I apologize, but I couldn't process that request. Could you please try again?"
                    await record_chat_message(session_id, "user", user_message)
                    await record_chat_message(session_id, "assistant", error_message)
                    
                    print("DEBUG: No answer received, adding error message")
                    new_history = [(msg1, msg2) for msg1, msg2 in history]
                    new_history.append((user_message, "I apologize, but I couldn't process that request. Could you please try again?"))
                    history = new_history
        else:
            # Handle invalid extraction
            error_message = "I'm sorry, I didn't understand that. Could you please repeat?"
            # Add the current conversation exchange to history in Gradio format
            history.append((user_message, error_message))
            state["missing_var"] = var_marker
        
        return history, state, ""

    # Process new query
    previous_system_response = next((msg["content"] for msg in reversed(internal_history) if msg["role"] == "assistant"), "")
    full_history = " ".join(msg["content"] for msg in internal_history if msg["role"] == "user")
    
    # If this is an update_variable intent, handle previous intent tracking
    extracted = await extract_intent_variables(user_message, previous_system_response)
    if extracted.get("intent") == "update_variable":
        # We need to store the ORIGINAL intent (not update_variable)
        # Only set previous_intent if it doesn't exist yet or isn't already update_variable
        if "previous_intent" not in state["data"] or state["data"].get("previous_intent") == "update_variable":
            if state["data"].get("intent") and state["data"].get("intent") != "update_variable":
                state["data"]["original_intent"] = state["data"].get("intent")
        else:
            # If previous_intent exists and isn't update_variable, preserve it as original_intent
            if state["data"].get("previous_intent") and state["data"].get("previous_intent") != "update_variable":
                state["data"]["original_intent"] = state["data"].get("previous_intent")

        # ONLY update the values that were explicitly mentioned (not 0 or None)
        for key, value in extracted.items():
            if key == "intent":
                state["data"][key] = value
            elif value is not None and (not isinstance(value, (int, float)) or value != 0):
                state["data"][key] = value
                print(f"DEBUG app.py: For update_variable, updating {key} to {value}")

    answer = await process_query(user_message, previous_system_response, full_history, state)
    
    # Always ensure we have a valid response and add to history in Gradio format
    if answer:
        await record_chat_message(session_id, "user", user_message)
        await record_chat_message(session_id, "assistant", answer)
        
        # Update user profile if we have data
        if state.get("data"):
            await update_user_financial_profile(user_id, state["data"])
            
            # Record intent if it exists
            if state["data"].get("intent") and state["data"].get("intent") != "unknown":
                await record_user_intent(
                    user_id,
                    session_id,
                    state["data"]["intent"],
                    state["data"]
                )
        
        history.append((user_message, answer))
    else:
        error_message = "I apologize, but I couldn't process that request. Could you please try again?"
        await record_chat_message(session_id, "user", user_message)
        await record_chat_message(session_id, "assistant", error_message)
        history.append((user_message, error_message))    
    return history, state, ""

# Add this new function for user login
def login(email, first_name, last_name):
    if not email or "@" not in email:
        return "Please enter a valid email address"
    
    # Create a simple user info object
    user_info = {
        "email": email,
        "first_name": first_name or "Anonymous",
        "last_name": last_name or "User"
    }
    
    # Store in a session cookie or similar mechanism
    # For now, we'll use a global variable for demonstration
    return f"Logged in as {email}", user_info

# Modified Gradio for user login
with gr.Blocks() as demo:
    # Define your welcome message
    initial_message = (
        "Hi there, I'm your friendly money mentor. "
        "My goal is to help you make informed, confident decisions about your money. "
        "Please log in to get started!"
    )
    
    # Store user info in Gradio state
    user_info_state = gr.State(None)
    
    # Create a login form
    with gr.Row():
        with gr.Column(scale=3):
            email_input = gr.Textbox(label="Email", placeholder="your.email@example.com")
            with gr.Row():
                first_name_input = gr.Textbox(label="First Name (optional)", placeholder="First Name")
                last_name_input = gr.Textbox(label="Last Name (optional)", placeholder="Last Name")
            login_button = gr.Button("Login")
            login_status = gr.Textbox(label="Status")
    
    # Chat interface (initially hidden)
    chat_interface = gr.Column(visible=False)
    with chat_interface:
        chatbot = gr.Chatbot(value=[("", initial_message)], render=True, height=600)
        state = gr.State(None)
        with gr.Row():
            txt = gr.Textbox(
                show_label=False, 
                placeholder="Enter your message and press enter",
                container=False
            )
    
    # Connect login button to the login function
    login_button.click(
        fn=login,
        inputs=[email_input, first_name_input, last_name_input],
        outputs=[login_status, user_info_state]
    ).then(
        fn=lambda user_info: (gr.update(visible=False), gr.update(visible=True)) if user_info else (gr.update(visible=True), gr.update(visible=False)),
        inputs=[user_info_state],
        outputs=[gr.Row(visible=True, elem_id="login_row"), chat_interface]
    )
    
    # Connect chat input to the chat function
    txt.submit(
        fn=chat_fn,
        inputs=[txt, chatbot, state, user_info_state],
        outputs=[chatbot, state, txt],
        queue=True
    )

demo.queue()
print("\n\n==== APPLICATION STARTUP COMPLETE ====\n\n")
demo.launch(server_name="0.0.0.0", server_port=7860)