import uuid
from .supabase import supabase

class ChatService:
    """Service for handling chat operations with Supabase"""
    
    async def createOrFindSession(self, user_id, platform, external_session_id=None):
        """
        Create or retrieve an existing chat session
        """
        try:
            data = {
                "p_user_id": user_id,
                "p_platform": platform,
                "p_external_session_id": external_session_id
            }
            
            # Call the Supabase function
            result = await supabase.query(
                "/rest/v1/rpc/find_or_create_chat_session",
                method="POST",
                data=data
            )
            
            return {"sessionId": result}
        except Exception as e:
            print(f"Error creating/finding chat session: {e}")
            # Fallback: generate a local session ID
            return {"sessionId": str(uuid.uuid4())}
    
    async def endSession(self, session_id):
        """End a chat session"""
        try:
            data = {
                "is_active": False,
                "ended_at": "now()"
            }
            
            await supabase.query(
                f"/rest/v1/chat_sessions?id=eq.{session_id}",
                method="PATCH",
                data=data
            )
            
            return {"success": True}
        except Exception as e:
            print(f"Error ending chat session: {e}")
            return {"success": False, "error": str(e)}
    
    async def recordMessage(self, session_id, sender_type, content, metadata=None):
        """Record a chat message"""
        try:
            data = {
                "p_session_id": session_id,
                "p_sender_type": sender_type,
                "p_content": content,
                "p_metadata": metadata
            }
            
            # Call the Supabase function
            result = await supabase.query(
                "/rest/v1/rpc/record_chat_message",
                method="POST",
                data=data
            )
            
            return {"messageId": result}
        except Exception as e:
            print(f"Error recording chat message: {e}")
            # Fallback: return a generated ID
            return {"messageId": str(uuid.uuid4())}
    
    async def getChatHistory(self, session_id):
        """Get chat history for a session"""
        try:
            result = await supabase.query(
                f"/rest/v1/chat_messages?session_id=eq.{session_id}",
                method="GET"
            )
            
            return result
        except Exception as e:
            print(f"Error fetching chat history: {e}")
            return []
    
    async def recordIntent(self, user_id, session_id, intent_type, intent_data):
        """Record user intent"""
        try:
            data = {
                "p_user_id": user_id,
                "p_session_id": session_id,
                "p_intent_type": intent_type,
                "p_intent_data": intent_data
            }
            
            # Call the Supabase function
            result = await supabase.query(
                "/rest/v1/rpc/record_user_intent",
                method="POST",
                data=data
            )
            
            return {"intentId": result}
        except Exception as e:
            print(f"Error recording user intent: {e}")
            return {"intentId": str(uuid.uuid4())}