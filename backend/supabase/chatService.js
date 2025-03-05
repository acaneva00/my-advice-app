import { supabase } from './supabase.js';

/**
 * Service for handling chat operations with Supabase
 */
export class ChatService {
  /**
   * Create or retrieve an existing chat session
   * @param {string} userId - User ID
   * @param {string} platform - Platform identifier (webchat, whatsapp, etc.)
   * @param {string} externalSessionId - External platform session ID (optional)
   * @returns {Promise<Object>} - Session data
   */
  async createOrFindSession(userId, platform, externalSessionId = null) {
    try {
      const { data, error } = await supabase.rpc('find_or_create_chat_session', {
        p_user_id: userId,
        p_platform: platform,
        p_external_session_id: externalSessionId
      });

      if (error) throw error;
      return { sessionId: data };
    } catch (error) {
      console.error('Error creating/finding chat session:', error);
      throw error;
    }
  }

  /**
   * End a chat session
   * @param {string} sessionId - Session ID
   * @returns {Promise<Object>} - Success status
   */
  async endSession(sessionId) {
    try {
      const { data, error } = await supabase
        .from('chat_sessions')
        .update({
          is_active: false,
          ended_at: new Date()
        })
        .eq('id', sessionId);

      if (error) throw error;
      return { success: true };
    } catch (error) {
      console.error('Error ending chat session:', error);
      throw error;
    }
  }

  /**
   * Record a chat message
   * @param {string} sessionId - Session ID
   * @param {string} senderType - 'user' or 'assistant'
   * @param {string} content - Message content
   * @param {Object} metadata - Additional metadata (optional)
   * @returns {Promise<Object>} - Message data
   */
  async recordMessage(sessionId, senderType, content, metadata = null) {
    try {
      const { data, error } = await supabase.rpc('record_chat_message', {
        p_session_id: sessionId,
        p_sender_type: senderType,
        p_content: content,
        p_metadata: metadata
      });

      if (error) throw error;
      return { messageId: data };
    } catch (error) {
      console.error('Error recording chat message:', error);
      throw error;
    }
  }

  /**
   * Get chat history for a session
   * @param {string} sessionId - Session ID
   * @returns {Promise<Array>} - Chat messages
   */
  async getChatHistory(sessionId) {
    try {
      const { data, error } = await supabase
        .from('chat_messages')
        .select('*')
        .eq('session_id', sessionId)
        .order('sent_at', { ascending: true });

      if (error) throw error;
      return data;
    } catch (error) {
      console.error('Error fetching chat history:', error);
      throw error;
    }
  }

  /**
   * Record user intent
   * @param {string} userId - User ID
   * @param {string} sessionId - Session ID
   * @param {string} intentType - Intent type (e.g., 'compare_fees', 'project_balance')
   * @param {Object} intentData - Intent-specific data
   * @returns {Promise<Object>} - Intent record
   */
  async recordIntent(userId, sessionId, intentType, intentData) {
    try {
      const { data, error } = await supabase.rpc('record_user_intent', {
        p_user_id: userId,
        p_session_id: sessionId,
        p_intent_type: intentType,
        p_intent_data: intentData
      });

      if (error) throw error;
      return { intentId: data };
    } catch (error) {
      console.error('Error recording user intent:', error);
      throw error;
    }
  }

  /**
   * Get recent sessions for a user
   * @param {string} userId - User ID
   * @param {number} limit - Maximum number of sessions to retrieve
   * @returns {Promise<Array>} - Session data
   */
  async getUserSessions(userId, limit = 10) {
    try {
      const { data, error } = await supabase
        .from('chat_sessions')
        .select('*, chat_messages(count)')
        .eq('user_id', userId)
        .order('started_at', { ascending: false })
        .limit(limit);

      if (error) throw error;
      return data;
    } catch (error) {
      console.error('Error fetching user sessions:', error);
      throw error;
    }
  }
}