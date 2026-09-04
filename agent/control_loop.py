import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from db.models import get_db_connection, immediate_transaction
from skills.preferences import get_all_preferences
from agent.harness import get_groq_client, SYSTEM_PROMPT, TOOLS_SCHEMA, TOOL_DISPATCH, MODEL_NAME

logger = logging.getLogger(__name__)

# Global in-memory conversation state keyed by chat_id
CONVERSATION_HISTORY: Dict[int, List[Dict[str, Any]]] = {}

def clear_conversation(chat_id: int):
    """Clear in-memory chat session history (used by /new command). Preferences persist in DB!"""
    CONVERSATION_HISTORY[chat_id] = []

def run_agent_turn(
    user_message: str,
    chat_id: int,
    owner_id: str,
    update_id: Optional[str] = None
) -> Tuple[str, List[str]]:
    """
    Executes a multi-turn agent control loop for an incoming user message.
    Returns a tuple of: (final_reply_text, list_of_generated_file_paths)
    """
    # 1. Idempotency Check
    conn = get_db_connection()
    try:
        if update_id:
            cur = conn.execute("SELECT * FROM idempotency_log WHERE update_id = ?", (str(update_id),))
            if cur.fetchone():
                logger.info(f"Duplicate update_id {update_id} skipped due to idempotency log.")
                return ("This update has already been processed.", [])
    finally:
        conn.close()

    # 2. Fetch persistent standing preferences
    prefs = get_all_preferences(owner_id)
    pref_str = "\n".join([f"- {k}: {v}" for k, v in prefs.items()]) if prefs else "None set yet."
    
    dynamic_system_prompt = f"{SYSTEM_PROMPT}\n\nSTANDING OWNER PREFERENCES (Persisted in DB across chats):\n{pref_str}\n"

    # 3. Initialize or fetch conversation history
    if chat_id not in CONVERSATION_HISTORY:
        CONVERSATION_HISTORY[chat_id] = []
        
    messages = CONVERSATION_HISTORY[chat_id]
    
    # Prepend dynamic system message if not present
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": dynamic_system_prompt})
    else:
        messages[0] = {"role": "system", "content": dynamic_system_prompt}

    # Append user input
    messages.append({"role": "user", "content": user_message})

    client = get_groq_client()
    generated_files: List[str] = []
    max_steps = 10
    step_count = 0

    # 4. Multi-step Agent Loop
    while step_count < max_steps:
        step_count += 1
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
        except Exception as e:
            logger.error(f"Error calling Groq API: {e}")
            return (f"Apologies, an error occurred while processing your request with the AI engine: {str(e)}", [])

        assistant_msg = response.choices[0].message
        
        # Format message object to append to messages history
        msg_dict = {"role": "assistant"}
        if assistant_msg.content:
            msg_dict["content"] = assistant_msg.content
        if assistant_msg.tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                } for tc in assistant_msg.tool_calls
            ]
            
        messages.append(msg_dict)

        # If no tool calls requested, we have the final model response!
        if not assistant_msg.tool_calls:
            final_text = assistant_msg.content or "Done."
            
            # Log update_id to idempotency_log
            if update_id:
                c = get_db_connection()
                try:
                    with immediate_transaction(c):
                        c.execute("INSERT OR IGNORE INTO idempotency_log (update_id) VALUES (?)", (str(update_id),))
                finally:
                    c.close()
                    
            return (final_text, generated_files)

        # 5. Handle Tool Execution
        for tc in assistant_msg.tool_calls:
            func_name = tc.function.name
            func_args_str = tc.function.arguments
            
            try:
                func_args = json.loads(func_args_str) if func_args_str else {}
            except Exception:
                func_args = {}

            # Inject owner_id or idempotency_key where applicable
            if func_name in ["set_preference", "get_preference"]:
                func_args["owner_id"] = str(owner_id)
            if func_name == "finalize_bill" and update_id:
                func_args["idempotency_key"] = str(update_id)

            logger.info(f"Executing Tool Call: {func_name} with args: {func_args}")

            if func_name in TOOL_DISPATCH:
                try:
                    tool_result = TOOL_DISPATCH[func_name](**func_args)
                    
                    # Track file generation output if applicable
                    if isinstance(tool_result, dict) and "file_path" in tool_result:
                        generated_files.append(tool_result["file_path"])
                        
                    result_content = json.dumps(tool_result, default=str)
                except Exception as err:
                    result_content = json.dumps({"status": "error", "message": str(err)})
            else:
                result_content = json.dumps({"status": "error", "message": f"Tool '{func_name}' not recognized."})

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_content
            })

    return ("Completed maximum processing iterations.", generated_files)
