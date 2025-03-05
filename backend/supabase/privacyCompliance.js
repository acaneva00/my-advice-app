import { supabase } from './supabase.js';
import crypto from 'crypto';

/**
 * Helper functions for APP (Australian Privacy Principles) compliance
 */
export class PrivacyCompliance {
  /**
   * Record a privacy consent event
   * @param {string} userId - User ID
   * @param {string} consentType - Type of consent ('privacy_policy', 'terms_of_service', 'data_sharing')
   * @param {string} version - Version of the document consented to
   * @param {Object} metadata - Additional metadata about the consent event
   * @returns {Promise<Object>} - Consent record
   */
  static async recordConsent(userId, consentType, version, metadata = {}) {
    try {
      const { data, error } = await supabase
        .from('privacy_consents')
        .insert({
          user_id: userId,
          consent_type: consentType,
          version: version,
          ip_address: metadata.ipAddress || 'unknown',
          user_agent: metadata.userAgent || 'unknown'
        })
        .select()
        .single();
      
      if (error) throw error;
      
      // Also update the user record
      if (consentType === 'privacy_policy' || consentType === 'terms_of_service') {
        const updates = {};
        if (consentType === 'privacy_policy') {
          updates.privacy_version = version;
        } else {
          updates.terms_version = version;
        }
        
        updates.consent_timestamp = new Date();
        
        await supabase
          .from('users')
          .update(updates)
          .eq('id', userId);
      }
      
      return data;
    } catch (error) {
      console.error(`Error recording ${consentType} consent:`, error);
      throw error;
    }
  }

  /**
   * Check if a user has given consent to a specific document version
   * @param {string} userId - User ID
   * @param {string} consentType - Type of consent to check
   * @param {string} version - Version to check against (optional)
   * @returns {Promise<boolean>} - True if consent is valid
   */
  static async hasValidConsent(userId, consentType, version = null) {
    try {
      let query = supabase
        .from('privacy_consents')
        .select('*')
        .eq('user_id', userId)
        .eq('consent_type', consentType);
      
      if (version) {
        query = query.eq('version', version);
      }
      
      const { data, error } = await query
        .order('consented_at', { ascending: false })
        .limit(1);
      
      if (error) throw error;
      
      return data && data.length > 0;
    } catch (error) {
      console.error(`Error checking ${consentType} consent:`, error);
      return false;
    }
  }

  /**
   * Generate data export for user (for data portability)
   * @param {string} userId - User ID
   * @returns {Promise<Object>} - User data export
   */
  static async generateDataExport(userId) {
    try {
      // Get user profile
      const { data: profile, error: profileError } = await supabase
        .from('user_profile_summary')
        .select('*')
        .eq('user_id', userId)
        .single();
      
      if (profileError) throw profileError;
      
      // Get chat sessions
      const { data: sessions, error: sessionsError } = await supabase
        .from('chat_sessions')
        .select(`
          id,
          platform,
          started_at,
          ended_at,
          chat_messages (
            sender_type,
            content,
            sent_at
          )
        `)
        .eq('user_id', userId)
        .order('started_at', { ascending: false });
      
      if (sessionsError) throw sessionsError;
      
      // Get intents
      const { data: intents, error: intentsError } = await supabase
        .from('user_intents')
        .select('*')
        .eq('user_id', userId)
        .order('created_at', { ascending: false });
      
      if (intentsError) throw intentsError;
      
      // Get privacy consents
      const { data: consents, error: consentsError } = await supabase
        .from('privacy_consents')
        .select('*')
        .eq('user_id', userId)
        .order('consented_at', { ascending: false });
      
      if (consentsError) throw consentsError;
      
      // Compile export
      return {
        profile,
        chat_history: sessions,
        intents,
        privacy_consents: consents,
        export_date: new Date().toISOString(),
        export_reason: 'User requested data export'
      };
    } catch (error) {
      console.error('Error generating data export:', error);
      throw error;
    }
  }

  /**
   * Anonymize or pseudonymize user data (while maintaining analytics value)
   * @param {string} userId - User ID
   * @returns {Promise<Object>} - Status of operation
   */
  static async anonymizeUserData(userId) {
    try {
      // Generate a pseudonym for the user
      const pseudonym = crypto.randomBytes(16).toString('hex');
      
      // Update user record 
      const { error: userError } = await supabase
        .from('users')
        .update({
          is_deleted: true,
          deletion_date: new Date(),
          email: `anonymized_${pseudonym}@deleted.example.com`,
          first_name: 'Anonymized',
          last_name: 'User',
          phone: null
        })
        .eq('id', userId);
      
      if (userError) throw userError;
      
      // Log the anonymization action
      await supabase
        .from('audit_logs')
        .insert({
          user_id: userId,
          action_type: 'anonymize',
          resource_type: 'user',
          resource_id: userId
        });
      
      return { success: true, pseudonym };
    } catch (error) {
      console.error('Error anonymizing user data:', error);
      throw error;
    }
  }

  /**
   * Handle data breach notification requirements
   * @param {Array} affectedUserIds - List of affected user IDs
   * @param {string} breachDescription - Description of the breach
   * @param {Date} breachDate - Date of the breach
   * @returns {Promise<Object>} - Status and notification IDs
   */
  static async handleDataBreachNotification(affectedUserIds, breachDescription, breachDate) {
    try {
      // Log the breach
      const { data: breachLog, error: breachError } = await supabase.rpc('log_data_breach', {
        p_description: breachDescription,
        p_breach_date: breachDate.toISOString(),
        p_affected_user_count: affectedUserIds.length
      });
      
      if (breachError) throw breachError;
      
      // Create notifications for affected users
      const notificationPromises = affectedUserIds.map(userId => 
        supabase
          .from('notifications')
          .insert({
            user_id: userId,
            title: 'Important: Data Security Notice',
            message: 'We are notifying you of a data security incident that may have affected your information. Please check your email for more details.',
            notification_type: 'system'
          })
      );
      
      await Promise.all(notificationPromises);
      
      return { 
        success: true, 
        breachLogId: breachLog.id, 
        notificationCount: affectedUserIds.length 
      };
    } catch (error) {
      console.error('Error handling data breach notification:', error);
      throw error;
    }
  }

  /**
   * Generate a compliance report for regulatory purposes
   * @param {Date} startDate - Start date for the report
   * @param {Date} endDate - End date for the report
   * @returns {Promise<Object>} - Compliance report data
   */
  static async generateComplianceReport(startDate, endDate) {
    try {
      const report = {
        report_period: {
          start: startDate.toISOString(),
          end: endDate.toISOString()
        },
        generated_at: new Date().toISOString()
      };
      
      // Get privacy consent statistics
      const { data: consentStats, error: consentError } = await supabase.rpc('get_consent_statistics', {
        p_start_date: startDate.toISOString(),
        p_end_date: endDate.toISOString()
      });
      
      if (consentError) throw consentError;
      report.consent_statistics = consentStats;
      
      // Get user statistics
      const { data: userStats, error: userError } = await supabase.rpc('get_user_statistics', {
        p_start_date: startDate.toISOString(),
        p_end_date: endDate.toISOString()
      });
      
      if (userError) throw userError;
      report.user_statistics = userStats;
      
      // Get data access statistics
      const { data: accessStats, error: accessError } = await supabase.rpc('get_data_access_statistics', {
        p_start_date: startDate.toISOString(),
        p_end_date: endDate.toISOString()
      });
      
      if (accessError) throw accessError;
      report.data_access_statistics = accessStats;
      
      return report;
    } catch (error) {
      console.error('Error generating compliance report:', error);
      throw error;
    }
  }
}