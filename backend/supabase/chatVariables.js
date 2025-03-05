import { UserService } from './userService.js';
import { ChatService } from './chatService.js';

const userService = new UserService();
const chatService = new ChatService();

/**
 * Helper class to integrate user state management with Supabase
 */
export class ChatVariablesManager {
  /**
   * Initialize state manager with user ID and session
   * @param {string} userId - User ID
   * @param {string} sessionId - Chat session ID
   * @param {string} platform - Platform identifier
   */
  constructor(userId, sessionId, platform) {
    this.userId = userId;
    this.sessionId = sessionId;
    this.platform = platform;
    this.state = {
      data: {}
    };
  }

  /**
   * Load user profile and previous state
   */
  async loadState() {
    try {
      // Load user profile
      const profile = await userService.getUserProfile(this.userId);
      
      // Initialize state with profile data
      this.state.data = {
        current_age: profile.current_age || 0,
        current_balance: profile.current_balance || 0,
        current_income: profile.current_income || 0,
        retirement_age: profile.retirement_age || 0,
        current_fund: profile.current_fund || null,
        super_included: profile.super_included,
        income_net_of_super: profile.income_net_of_super || 0,
        after_tax_income: profile.after_tax_income || 0,
        retirement_balance: profile.retirement_balance || 0,
        retirement_income: profile.retirement_income || 0,
        retirement_income_option: profile.retirement_income_option || null,
        retirement_drawdown_age: profile.retirement_drawdown_age || 0
      };
      
      // Try to find most recent intent to restore conversation state
      const { data: intents } = await chatService.getUserSessions(this.userId, 1);
      
      if (intents && intents.length > 0) {
        // Get the most recent intent
        const lastIntent = intents[0];
        if (lastIntent.intent_type) {
          this.state.data.intent = lastIntent.intent_type;
          this.state.data.previous_intent = lastIntent.intent_type;
        }
      }
      
      return this.state;
    } catch (error) {
      console.error('Error loading state:', error);
      throw error;
    }
  }

  /**
   * Save updated state with intent tracking
   * @param {Object} state - Updated state object
   * @param {string} userMessage - User message for context
   * @param {string} assistantResponse - Assistant response for context
   */
  async saveState(state, userMessage, assistantResponse) {
    try {
      this.state = state;
      
      // Extract main financial variables for profile update
      const profileData = {
        currentAge: state.data.current_age,
        currentBalance: state.data.current_balance,
        currentIncome: state.data.current_income,
        retirementAge: state.data.retirement_age,
        currentFund: state.data.current_fund,
        superIncluded: state.data.super_included,
        retirementIncomeOption: state.data.retirement_income_option,
        retirementIncome: state.data.retirement_income
      };
      
      // Update user financial profile
      await userService.updateFinancialProfile(this.userId, profileData);
      
      // Record intent if it exists and has changed
      if (state.data.intent && 
          state.data.intent !== 'unknown' && 
          state.data.intent !== state.data.previous_intent) {
        
        // Prepare intent data with all financial variables
        const intentData = {
          current_age: state.data.current_age,
          current_balance: state.data.current_balance,
          current_income: state.data.current_income,
          retirement_age: state.data.retirement_age,
          current_fund: state.data.current_fund,
          super_included: state.data.super_included,
          income_net_of_super: state.data.income_net_of_super,
          after_tax_income: state.data.after_tax_income,
          retirement_balance: state.data.retirement_balance,
          retirement_income: state.data.retirement_income,
          retirement_income_option: state.data.retirement_income_option,
          user_message: userMessage,
          assistant_response: assistantResponse
        };
        
        // Record the intent
        await chatService.recordIntent(
          this.userId, 
          this.sessionId, 
          state.data.intent, 
          intentData
        );
        
        // Update previous_intent in state
        state.data.previous_intent = state.data.intent;
      }
      
      return state;
    } catch (error) {
      console.error('Error saving state:', error);
      throw error;
    }
  }
  
  /**
   * Create or find chat session
   * @param {string} externalSessionId - Optional external session ID
   * @returns {Promise<string>} - Session ID
   */
  static async createSession(userId, platform, externalSessionId = null) {
    try {
      const result = await chatService.createOrFindSession(
        userId,
        platform,
        externalSessionId
      );
      
      return result.sessionId;
    } catch (error) {
      console.error('Error creating chat session:', error);
      throw error;
    }
  }
  
  /**
   * Record a message in the chat session
   * @param {string} content - Message content
   * @param {string} senderType - 'user' or 'assistant'
   * @param {Object} metadata - Optional metadata
   */
  async recordMessage(content, senderType, metadata = null) {
    try {
      await chatService.recordMessage(
        this.sessionId,
        senderType,
        content,
        metadata
      );
    } catch (error) {
      console.error('Error recording message:', error);
      // Continue even if recording fails - this is non-blocking
    }
  }
}