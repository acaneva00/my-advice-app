import gradio as gr
from backend.main import process_query, parse_numeric_with_suffix, validate_response, get_clarification_prompt, df
from backend.helper import ask_llm, get_unified_variable_response
from backend.utils import match_fund_name
from backend.cashflow import calculate_income_net_of_super, calculate_after_tax_income
import json

def extract_variable_from_response(last_prompt: str, user_message: str, context: dict, missing_var: str) -> dict:
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
        "current_age": "current_age",
        "retirement_age": "retirement_age",
        "super_included": "super_included"
    }
    
    # Define which variables should be treated as numbers
    numeric_vars = {
        "current_age": "int",
        "current_balance": "float",
        "current_income": "float",
        "retirement_age": "int"
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

    response = ask_llm(system_prompt, combined_prompt)
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
                    interpretation = ask_llm("You are a boolean interpreter. Answer with ONLY 'included' or 'on top'.", interpret_prompt)
                    data['value'] = interpretation.lower().strip() == "included"
            elif isinstance(raw_value, bool):
                data['value'] = raw_value

        return data
    except json.JSONDecodeError as e:
        print("DEBUG extract_variable_from_response: Error parsing JSON:", e)
        return {}
    except Exception as e:
        print("DEBUG extract_variable_from_response: Unexpected error:", e)
        return {}
        
def chat_fn(user_message, history, state):
    print(f"\n\n==== NEW MESSAGE RECEIVED: {user_message} ====\n\n")
    print(f"DEBUG app.py: Entering chat_fn")
    print(f"DEBUG app.py: User message: {user_message}")
    print(f"DEBUG app.py: Current state: {state}")
    
    # Initialize state if needed
    if state is None or not isinstance(state, dict):
        state = {"data": {"super_included": None}, "missing_var": None}
    if history is None:
        history = []

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
        extraction = extract_variable_from_response(last_prompt, user_message, context, var_marker)
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
                unified_message = get_unified_variable_response(next_var, None, context, missing_vars)
                state["data"]["last_clarification_prompt"] = unified_message
                state["missing_var"] = next_var
                
                # Add the current conversation exchange to history in Gradio format
                history.append((user_message, unified_message))
            else:
                # All required variables collected, process the complete query
                previous_system_response = next((msg["content"] for msg in reversed(internal_history) if msg["role"] == "assistant"), "")
                full_history = " ".join(msg["content"] for msg in internal_history if msg["role"] == "user")
                
                print("DEBUG: Processing complete query after collecting all variables")
                
                answer = process_query(user_message, previous_system_response, full_history, state)
                
                print(f"DEBUG: Got answer: {answer}")

                if answer:
                    print("DEBUG: Adding final answer to history")
                    # Create a new list with the same content as history to avoid reference issues
                    new_history = [(msg1, msg2) for msg1, msg2 in history]
                    # Append the new exchange (ensure it's in tuple format)
                    new_history.append((user_message, answer))
                    # Replace history with new_history
                    history = new_history
                    print(f"DEBUG: Final history length: {len(history)}")
                else:
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
    
    answer = process_query(user_message, previous_system_response, full_history, state)
    
    # Always ensure we have a valid response and add to history in Gradio format
    if answer:
        history.append((user_message, answer))
    else:
        history.append((user_message, "I apologize, but I couldn't process that request. Could you please try again?"))
    
    return history, state, ""

# Modified Gradio initialization to ensure HTML rendering works
# Replace the Gradio UI section in app.py with this

with gr.Blocks() as demo:
    # Define your welcome message.
    initial_message = (
        "Hi there, I'm your friendly money mentor. "
        "My goal is to help you make informed, confident decisions about your money. "
        "You can start by asking me a question. " 
        "For example, would you like to know the cheapest superfund for you, or an estimate of your super balance at retirement? "
        "If there's something else on your mind, just let me know!"
    )
    
    # Pre-populate the chatbot with the welcome message.
    chatbot = gr.Chatbot(value=[("", initial_message)], render=True, height=600)
    state = gr.State(None)
    with gr.Row():
        txt = gr.Textbox(
            show_label=False, 
            placeholder="Enter your message and press enter",
            container=False
        )
    txt.submit(chat_fn, [txt, chatbot, state], [chatbot, state, txt], queue=True)

demo.queue()
print("\n\n==== APPLICATION STARTUP COMPLETE ====\n\n")
demo.launch(server_name="0.0.0.0", server_port=7860)