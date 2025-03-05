import { supabase } from './supabase.js';

/**
 * Service for handling user operations with Supabase
 */
export class UserService {
  /**
   * Create a new user account
   * @param {Object} userData - User data
   * @returns {Promise<Object>} - New user data
   */
  async createUser(userData) {
    try {
      // First create the auth user
      const { data: authData, error: authError } = await supabase.auth.admin.createUser({
        email: userData.email,
        password: userData.password,
        email_confirm: true,
      });

      if (authError) throw authError;

      // Now use the stored procedure to create the user profile
      const { data, error } = await supabase.rpc('create_user_with_profile', {
        user_uuid: authData.user.id,
        user_email: userData.email,
        first_name: userData.firstName,
        last_name: userData.lastName,
        phone: userData.phone,
        privacy_version: userData.privacyVersion,
        terms_version: userData.termsVersion,
        current_age: userData.currentAge,
        current_balance: userData.currentBalance,
        current_income: userData.currentIncome,
        retirement_age: userData.retirementAge,
        current_fund: userData.currentFund
      });

      if (error) throw error;

      return { userId: data };
    } catch (error) {
      console.error('Error creating user:', error);
      throw error;
    }
  }

  /**
   * Get user profile data
   * @param {string} userId - User ID
   * @returns {Promise<Object>} - User profile data
   */
  async getUserProfile(userId) {
    try {
      const { data, error } = await supabase
        .from('user_profile_summary')
        .select('*')
        .eq('user_id', userId)
        .single();

      if (error) throw error;
      return data;
    } catch (error) {
      console.error('Error fetching user profile:', error);
      throw error;
    }
  }

  /**
   * Update user financial profile
   * @param {string} userId - User ID
   * @param {Object} profileData - Financial profile data
   * @returns {Promise<Object>} - Updated profile ID
   */
  async updateFinancialProfile(userId, profileData) {
    try {
      const { data, error } = await supabase.rpc('update_financial_profile', {
        p_user_id: userId,
        p_current_age: profileData.currentAge,
        p_current_balance: profileData.currentBalance,
        p_current_income: profileData.currentIncome,
        p_retirement_age: profileData.retirementAge,
        p_current_fund: profileData.currentFund,
        p_super_included: profileData.superIncluded,
        p_retirement_income_option: profileData.retirementIncomeOption,
        p_retirement_income: profileData.retirementIncome
      });

      if (error) throw error;
      return { profileId: data };
    } catch (error) {
      console.error('Error updating financial profile:', error);
      throw error;
    }
  }

  /**
   * Update user privacy consents
   * @param {string} userId - User ID
   * @param {Object} consentData - Consent data
   * @returns {Promise<Object>} - Success status
   */
  async updatePrivacyConsents(userId, consentData) {
    try {
      const { data, error } = await supabase
        .from('users')
        .update({
          privacy_version: consentData.privacyVersion,
          terms_version: consentData.termsVersion
        })
        .eq('id', userId);

      if (error) throw error;
      return { success: true };
    } catch (error) {
      console.error('Error updating privacy consents:', error);
      throw error;
    }
  }

  /**
   * Delete user account (marks as deleted per GDPR/privacy requirements)
   * @param {string} userId - User ID
   * @returns {Promise<Object>} - Success status
   */
  async deleteUserAccount(userId) {
    try {
      // This will trigger the handle_user_deletion() trigger
      // which preserves the record but marks it as deleted
      const { data, error } = await supabase
        .from('users')
        .delete()
        .eq('id', userId);

      if (error) throw error;

      // Disable auth user
      await supabase.auth.admin.updateUserById(userId, { 
        ban_duration: '87600h' // 10 years
      });

      return { success: true };
    } catch (error) {
      console.error('Error deleting user account:', error);
      throw error;
    }
  }
}