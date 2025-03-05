import { supabase } from './supabase.js';

/**
 * Service for handling advisor operations with Supabase
 */
export class AdvisorService {
  /**
   * Create a new advisor account
   * @param {Object} advisorData - Advisor data
   * @returns {Promise<Object>} - New advisor data
   */
  async createAdvisor(advisorData) {
    try {
      // First create the auth user with advisor role
      const { data: authData, error: authError } = await supabase.auth.admin.createUser({
        email: advisorData.email,
        password: advisorData.password,
        email_confirm: true,
        app_metadata: { role: 'advisor' }
      });

      if (authError) throw authError;

      // Create the advisor record
      const { data, error } = await supabase
        .from('advisors')
        .insert({
          auth_id: authData.user.id,
          email: advisorData.email,
          first_name: advisorData.firstName,
          last_name: advisorData.lastName,
          phone: advisorData.phone,
          afsl_number: advisorData.afslNumber
        })
        .select()
        .single();

      if (error) throw error;

      return data;
    } catch (error) {
      console.error('Error creating advisor:', error);
      throw error;
    }
  }

  /**
   * Get advisor details
   * @param {string} advisorId - Advisor ID
   * @returns {Promise<Object>} - Advisor data
   */
  async getAdvisorDetails(advisorId) {
    try {
      const { data, error } = await supabase
        .from('advisors')
        .select('*')
        .eq('id', advisorId)
        .single();

      if (error) throw error;
      return data;
    } catch (error) {
      console.error('Error fetching advisor details:', error);
      throw error;
    }
  }

  /**
   * Create advisor-client relationship
   * @param {string} advisorId - Advisor ID
   * @param {string} clientId - Client ID
   * @param {string} status - Relationship status (default: 'pending')
   * @returns {Promise<Object>} - Relationship data
   */
  async createClientRelationship(advisorId, clientId, status = 'pending') {
    try {
      const { data, error } = await supabase.rpc('create_advisor_client_relationship', {
        p_advisor_id: advisorId,
        p_client_id: clientId,
        p_status: status
      });

      if (error) throw error;
      return { relationshipId: data };
    } catch (error) {
      console.error('Error creating client relationship:', error);
      throw error;
    }
  }

  /**
   * Update advisor-client relationship status
   * @param {string} relationshipId - Relationship ID
   * @param {string} status - New status ('active', 'rejected', 'terminated')
   * @returns {Promise<Object>} - Updated relationship data
   */
  async updateRelationshipStatus(relationshipId, status) {
    try {
      const updates = {
        status: status
      };
      
      // If terminating, set end date
      if (status === 'terminated') {
        updates.relationship_end = new Date();
      }

      const { data, error } = await supabase
        .from('advisor_client_relationships')
        .update(updates)
        .eq('id', relationshipId)
        .select()
        .single();

      if (error) throw error;
      return data;
    } catch (error) {
      console.error('Error updating relationship status:', error);
      throw error;
    }
  }

  /**
   * Get client data for advisor
   * @param {string} advisorId - Advisor ID
   * @param {string} clientId - Client ID
   * @returns {Promise<Object>} - Client data
   */
  async getClientData(advisorId, clientId) {
    try {
      const { data, error } = await supabase.rpc('get_client_data_for_advisor', {
        p_advisor_id: advisorId,
        p_client_id: clientId
      });

      if (error) throw error;
      return data;
    } catch (error) {
      console.error('Error fetching client data:', error);
      throw error;
    }
  }

  /**
   * Get all clients for an advisor
   * @param {string} advisorId - Advisor ID
   * @returns {Promise<Array>} - Client list
   */
  async getAdvisorClients(advisorId) {
    try {
      const { data, error } = await supabase
        .from('advisor_client_dashboard')
        .select('*')
        .eq('advisor_id', advisorId)
        .eq('relationship_status', 'active');

      if (error) throw error;
      return data;
    } catch (error) {
      console.error('Error fetching advisor clients:', error);
      throw error;
    }
  }

  /**
   * Get client chat history
   * @param {string} advisorId - Advisor ID
   * @param {string} clientId - Client ID
   * @returns {Promise<Array>} - Chat history
   */
  async getClientChatHistory(advisorId, clientId) {
    try {
      // First verify relationship exists
      const { data: relationship, error: relError } = await supabase
        .from('advisor_client_relationships')
        .select('*')
        .eq('advisor_id', advisorId)
        .eq('client_id', clientId)
        .eq('status', 'active')
        .single();

      if (relError) throw relError;
      
      // If relationship exists, get chat history
      const { data, error } = await supabase
        .from('chat_history_with_intents')
        .select('*')
        .eq('user_id', clientId)
        .order('started_at', { ascending: false })
        .order('sent_at', { ascending: true });

      if (error) throw error;
      return data;
    } catch (error) {
      console.error('Error fetching client chat history:', error);
      throw error;
    }
  }
}