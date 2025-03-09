import gradio as gr
from backend.main import process_query, parse_numeric_with_suffix, validate_response, get_clarification_prompt, df
from backend.helper import ask_llm, get_unified_variable_response, update_calculated_values, extract_intent_variables
from backend.utils import match_fund_name, convert_variable_type, VARIABLE_TYPE_MAP, create_context_from_state, map_canonical_to_internal
from backend.cashflow import calculate_income_net_of_super, calculate_after_tax_income
from backend.supabase.chatService import ChatService
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import json
import re
import os
import httpx
import uuid
from dotenv import load_dotenv

# Initialize Flask app
flask_app = Flask(__name__)
CORS(flask_app)

# Initialize the chat service
chat_service = ChatService()

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
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
)

# User session management
active_sessions = {}

import asyncio

async def get_or_create_user(email, first_name=None, last_name=None):
    """
    Get existing user or create a new one in Supabase
    """
    try:
        # First check if user exists by email in our application users table
        response = await supabase_client.get(
            f"/rest/v1/users?email=eq.{email}&select=*"
        )
        
        if response.status_code == 200 and len(response.json()) > 0:
            print(f"Found existing application user with email {email}")
            return response.json()[0]
        
        # Check if auth user exists but application user doesn't
        auth_users_response = await supabase_client.get(
            "/auth/v1/admin/users",
            headers={"Authorization": f"Bearer {SUPABASE_KEY}"}
        )
        
        user_id = None
        if auth_users_response.status_code == 200:
            users = auth_users_response.json().get("users", [])
            for user in users:
                if user.get("email") == email:
                    user_id = user.get("id")
                    print(f"Found existing auth user with email {email} and ID {user_id}")
                    break
        
        # If no existing auth user found, create one
        if not user_id:
            auth_response = await supabase_client.post(
                "/auth/v1/signup",
                json={
                    "email": email,
                    "password": f"temp_{os.urandom(8).hex()}"  # Generate random password
                }
            )
            
            if auth_response.status_code != 200:
                raise Exception(f"Failed to create auth user: {auth_response.text}")
            
            auth_data = auth_response.json()
            user_id = auth_data.get("id") or auth_data.get("user", {}).get("id")
            
            if not user_id:
                print(f"Full auth response: {auth_data}")
                raise Exception("Could not extract user ID from authentication response")
            
            print(f"Successfully created auth user with ID: {user_id}")
            
            # Small delay to ensure auth user is fully propagated
            await asyncio.sleep(1)
        
        # Now create the application user record in the users table
        user_insert_response = await supabase_client.post(
            "/rest/v1/users",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Prefer": "return=representation"
            },
            json={
                "id": user_id,
                "email": email,
                "first_name": first_name or "Anonymous",
                "last_name": last_name or "User",
                "consent_timestamp": "now()",
                "privacy_version": "1.0",
                "terms_version": "1.0"
            }
        )
        
        if user_insert_response.status_code not in [200, 201]:
            # If direct insert fails, try using SQL with admin privileges
            print(f"Direct insert failed: {user_insert_response.text}. Trying SQL approach...")
            
            # Sanitize inputs to prevent SQL injection
            safe_email = email.replace("'", "''")
            safe_first_name = (first_name or "Anonymous").replace("'", "''")
            safe_last_name = (last_name or "User").replace("'", "''")
            
            sql_query = f"""
            INSERT INTO public.users (
                id, 
                email, 
                first_name, 
                last_name, 
                created_at, 
                updated_at, 
                consent_timestamp,
                privacy_version,
                terms_version
            ) 
            VALUES (
                '{user_id}', 
                '{safe_email}', 
                '{safe_first_name}', 
                '{safe_last_name}', 
                now(), 
                now(), 
                now(),
                '1.0',
                '1.0'
            )
            ON CONFLICT (id) DO NOTHING
            RETURNING *;
            """
            
            sql_response = await supabase_client.post(
                "/rest/v1/rpc/run_sql",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                },
                json={"sql": sql_query}
            )
            
            if sql_response.status_code != 200:
                print(f"SQL insertion failed: {sql_response.text}")
                raise Exception(f"Failed to create application user: {sql_response.text}")
            
            print("Successfully created application user via SQL")
        else:
            print("Successfully created application user via direct insert")
        
        # Now create the financial profile
        profile_response = await supabase_client.post(
            "/rest/v1/rpc/update_financial_profile",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            },
            json={
                "p_user_id": user_id,
                "p_current_age": None,
                "p_current_balance": None,
                "p_current_income": None,
                "p_retirement_age": None,
                "p_current_fund": None,
                "p_super_included": None,
                "p_retirement_income_option": None,
                "p_retirement_income": None,
                "p_income_net_of_super": None,
                "p_after_tax_income": None,
                "p_retirement_balance": None,
                "p_retirement_drawdown_age": None
            }
        )
        
        if profile_response.status_code != 200:
            print(f"Warning: Could not create financial profile: {profile_response.text}")
        else:
            print(f"Successfully created financial profile")
        
        # Get the created user
        new_user_response = await supabase_client.get(
            f"/rest/v1/users?id=eq.{user_id}&select=*",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"
            }
        )
        
        if new_user_response.status_code != 200 or not new_user_response.json():
            print(f"Warning: Could not retrieve user after creation: {new_user_response.text}")
            return {"id": user_id, "email": email}
        
        print(f"Successfully retrieved created user")
        return new_user_response.json()[0]
    
    except Exception as e:
        print(f"Error in get_or_create_user: {e}")
        print(f"Falling back to local user. Exception details: {str(e)}")
        return {"id": "local-user", "email": email}

async def create_chat_session(user_id):
    """
    Create a new chat session in Supabase
    """
    try:
        # Skip for local users
        if user_id == "local-user":
            print("Using local session for local user")
            return "local-session"
        
        response = await supabase_client.post(
            "/rest/v1/rpc/find_or_create_chat_session",
            json={
                "p_user_id": user_id,
                "p_platform": "webchat"
            }
        )
        
        if response.status_code != 200:
            print(f"Failed to create chat session: {response.text}")
            return "local-session"
            
        return response.json()
    
    except Exception as e:
        print(f"Error in create_chat_session: {e}")
        return "local-session"
    
async def record_chat_message(session_id, sender_type, content):
    """
    Record a chat message in Supabase
    """
    try:
        # Skip for local sessions
        if session_id == "local-session":
            print("Skipping message recording for local session")
            return
        
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

async def update_user_financial_profile(user_id, state_data):
    """
    Update the user's financial profile in Supabase
    """
    try:
        # Skip for local users
        if user_id == "local-user":
            print("Skipping database update for local user")
            return
        
        # Convert all values to proper types before sending to database
        converted_data = {}
        for key, value in state_data.items():
            if key in VARIABLE_TYPE_MAP:
                converted_data[key] = convert_variable_type(key, value)
            else:
                converted_data[key] = value

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
                "p_retirement_income": state_data.get("retirement_income"),
                "p_income_net_of_super": state_data.get("income_net_of_super"),
                "p_after_tax_income": state_data.get("after_tax_income"),
                "p_retirement_balance": state_data.get("retirement_balance"),
                "p_retirement_drawdown_age": state_data.get("retirement_drawdown_age"),
                "p_relationship_status": state_data.get("relationship_status"),
                "p_homeowner_status": state_data.get("homeowner_status"),
                "p_cash_assets": state_data.get("cash_assets"),
                "p_share_investments": state_data.get("share_investments"),
                "p_investment_properties": state_data.get("investment_properties"),
                "p_non_financial_assets": state_data.get("non_financial_assets")
            }
        )
        
        if response.status_code != 200:
            print(f"Warning: Failed to update profile: {response.text}")
    
    except Exception as e:
        print(f"Error in update_user_financial_profile: {e}")

async def record_user_intent(user_id, session_id, intent_type, state_data):
    """
    Record the user's intent in Supabase
    """
    try:
        # Skip for local users/sessions or unknown intents
        if user_id == "local-user" or session_id == "local-session" or not intent_type or intent_type == "unknown":
            print("Skipping intent recording for local user/session or unknown intent")
            return
        
        # Convert all data to proper types before recording intent
        converted_data = {}
        for key, value in state_data.items():
            if key in VARIABLE_TYPE_MAP:
                converted_data[key] = convert_variable_type(key, value)
            else:
                converted_data[key] = value
        
        # Prepare intent data with converted values
        intent_data = {
            "current_age": converted_data.get("current_age"),
            "current_balance": converted_data.get("current_balance"),
            "current_income": converted_data.get("current_income"),
            "retirement_age": converted_data.get("retirement_age"),
            "current_fund": converted_data.get("current_fund"),
            "super_included": converted_data.get("super_included"),
            "income_net_of_super": converted_data.get("income_net_of_super"),
            "after_tax_income": converted_data.get("after_tax_income"),
            "retirement_balance": converted_data.get("retirement_balance"),
            "retirement_income": converted_data.get("retirement_income"),
            "retirement_income_option": converted_data.get("retirement_income_option"),
            "retirement_drawdown_age": converted_data.get("retirement_drawdown_age")
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

async def extract_variable_from_response(last_prompt: str, user_message: str, context: dict, missing_var: str) -> dict:
    """
    Extract a specific variable from the user's response based on what was asked.
    Returns a dictionary with 'variable' and 'value' keys.
    """
    
    # Use the centralized mapping from utils.py instead of defining locally
    from backend.utils import VARIABLE_TYPE_MAP, convert_variable_type
    
    expected_var = map_canonical_to_internal(missing_var)

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
        
        # Replace all the type conversion logic with the centralized function
        raw_value = data.get('value')
        if raw_value is not None:
            # Convert the value using our central conversion utility
            converted_value = convert_variable_type(expected_var, raw_value)
            
            # If conversion failed (returned None) but we had a value, try LLM interpretation for booleans
            if converted_value is None and VARIABLE_TYPE_MAP.get(expected_var) == "boolean":
                try:
                    if expected_var == "homeowner_status":
                        interpret_prompt = f"Based on this response, does the user own their home or rent? Response: '{raw_value}'"
                        interpretation = await ask_llm("Answer with ONLY 'own' or 'rent'.", interpret_prompt)
                        converted_value = interpretation.lower().strip() == "own"
                    elif expected_var == "super_included":
                        interpret_prompt = f"Does this response indicate that super is INCLUDED in the income amount or PAID ON TOP? Response: '{raw_value}'"
                        interpretation = await ask_llm("You are a boolean interpreter. Answer with ONLY 'included' or 'on top'.", interpret_prompt)
                        converted_value = interpretation.lower().strip() == "included"
                except Exception as e:
                    print(f"DEBUG: Error using LLM to interpret ambiguous value: {e}")
                    
            # Handle fund name standardization separately since it's a special case
            if expected_var in ["current_fund", "nominated_fund"] and isinstance(converted_value, str):
                standardized = match_fund_name(converted_value, df)
                if standardized:
                    converted_value = standardized
                    
            # Update the value in our data
            data['value'] = converted_value
            print(f"DEBUG: Converted {raw_value} to {converted_value} for {expected_var}")
            
            # If conversion completely failed, return None
            if converted_value is None:
                print(f"DEBUG: Could not convert value {raw_value} for {expected_var}")
                return {'variable': expected_var, 'value': None}

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
        # Flag to indicate we're in variable collection mode
        state["data"]["in_variable_collection"] = True
        var_marker = state.pop("missing_var")
        print(f"DEBUG app.py: Processing missing var: {var_marker}")

        expected_var = map_canonical_to_internal(var_marker)

        print(f"DEBUG app.py: Mapped {var_marker} to {expected_var}")
        
        # Create context for extraction
        context = create_context_from_state(state, include_intent_info=True)
        context["is_new_intent"] = False  # Override for this specific use case
        
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

            # Convert to appropriate type
            converted_value = convert_variable_type(var_key, raw_value)
            
            # Update state with the converted value
            state["data"][var_key] = converted_value
            print(f"DEBUG app.py: Updated state with {var_key}: {converted_value} (converted from {raw_value})")

            # If we also extracted a retirement income amount, save that too
            if extraction.get("retirement_income") is not None:
                state["data"]["retirement_income"] = extraction["retirement_income"]
                print(f"DEBUG app.py: Also updated state with retirement_income: {extraction['retirement_income']}")

            # Update calculated values based on available data
            state = update_calculated_values(state)
            print(f"DEBUG app.py: Updated calculated values in state: {state}")
            
            # After extracting the variable, get the next missing variables from main.py
            previous_system_response = next((msg["content"] for msg in reversed(internal_history) if msg["role"] == "assistant"), "")
            full_history = " ".join(msg["content"] for msg in internal_history if msg["role"] == "user")
            
            # Call process_query to determine if there are more missing variables
            # This will return either a response (if all variables are collected) or a prompt for the next variable
            answer = await process_query(user_message, previous_system_response, full_history, state)
            
            # If state.missing_var exists, that means process_query identified more variables needed
            if state.get("missing_var"):
                # Just add the current message exchange to history
                history.append((user_message, answer))
            else:
                # All required variables collected, we have a complete answer
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
                    history.append((user_message, answer))
                else:
                    # Handle error case
                    error_message = "I apologize, but I couldn't process that request. Could you please try again?"
                    await record_chat_message(session_id, "user", user_message)
                    await record_chat_message(session_id, "assistant", error_message)
                    
                    history.append((user_message, error_message))
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

# Flask routes
@flask_app.route('/create_session', methods=['POST'])
def create_session():
    data = request.json
    user_id = data.get('user_id')
    platform = data.get('platform', 'webchat')
    
    try:
        result = chat_service.createOrFindSession(user_id, platform)
        return jsonify({'session_id': result.get('sessionId')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/chat_history', methods=['GET'])
def chat_history():
    session_id = request.args.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Session ID is required'}), 400
    
    try:
        messages = chat_service.getChatHistory(session_id)
        return jsonify({'messages': messages})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/record_message', methods=['POST'])
def record_message():
    data = request.json
    session_id = data.get('session_id')
    content = data.get('content')
    sender_type = data.get('sender_type')
    
    if not all([session_id, content, sender_type]):
        return jsonify({'error': 'Session ID, content, and sender type are required'}), 400
    
    try:
        result = chat_service.recordMessage(session_id, sender_type, content)
        return jsonify({'message_id': result.get('messageId')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/process_query', methods=['POST'])
def process_query_endpoint():
    data = request.json
    session_id = data.get('session_id')
    user_message = data.get('user_message')
    user_id = data.get('user_id')
    
    if not all([session_id, user_message]):
        return jsonify({'error': 'Session ID and user message are required'}), 400
    
    try:
        # Retrieve chat history
        history = chat_service.getChatHistory(session_id)
        
        # Build history context
        previous_messages = []
        for msg in history:
            previous_messages.append(msg)
        
        # Get the previous system response if available
        previous_system_response = ""
        for msg in reversed(previous_messages):
            if msg['sender_type'] == 'assistant':
                previous_system_response = msg['content']
                break
        
        # Get full history as a single string
        full_history = " ".join([msg['content'] for msg in previous_messages if msg['sender_type'] == 'user'])
        
        # Get or initialize state
        state = {
            "data": {
                "intent": "unknown",
                "super_included": None
            }
        }
        
        # Process the query
        response = process_query(user_message, previous_system_response, full_history, state)
        
        # Record the assistant's response
        result = chat_service.recordMessage(session_id, 'assistant', response)
        
        # Update user financial profile if we have useful data
        if state.get("data"):
            from backend.supabase.userService import UserService
            user_service = UserService()
            profile_data = {
                "currentAge": state["data"].get("current_age"),
                "currentBalance": state["data"].get("current_balance"),
                "currentIncome": state["data"].get("current_income"),
                "retirementAge": state["data"].get("retirement_age"),
                "currentFund": state["data"].get("current_fund"),
                "superIncluded": state["data"].get("super_included"),
                "retirementIncomeOption": state["data"].get("retirement_income_option"),
                "retirementIncome": state["data"].get("retirement_income")
            }
            user_service.updateFinancialProfile(user_id, profile_data)
            
            # Record intent if it exists and is not unknown
            if state["data"].get("intent") and state["data"].get("intent") != "unknown":
                chat_service.recordIntent(
                    user_id,
                    session_id,
                    state["data"]["intent"],
                    state["data"]
                )
        
        return jsonify({
            'message_id': result.get('messageId'),
            'content': response,
            'state': state
        })
    except Exception as e:
        print(f"Error processing query: {e}")
        return jsonify({'error': str(e)}), 500

# Modified Gradio for user login
with gr.Blocks() as demo:
    # Define your welcome message
    initial_message = (
        "Hi there, I'm your friendly money mentor. "
        "My goal is to help you make informed, confident decisions about your money. "
        "You can start by asking me a question. " 
        "For example, would you like to know the cheapest superfund for you, or an estimate of your super balance at retirement? "
        "If there's something else on your mind, just let me know!"
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

# Start Flask in a separate thread
flask_thread = threading.Thread(target=lambda: flask_app.run(host='0.0.0.0', port=7861))
flask_thread.daemon = True
flask_thread.start()
print("\n\n==== FLASK API STARTED ON PORT 7861 ====\n\n")

demo.queue()
print("\n\n==== APPLICATION STARTUP COMPLETE ====\n\n")
demo.launch(server_name="0.0.0.0", server_port=7860)