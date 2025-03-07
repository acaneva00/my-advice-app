// Mock authentication service for development/testing
const MOCK_USER = {
  id: 'mock-user-id',
  email: 'test@example.com',
  user_metadata: {
    first_name: 'Test',
    last_name: 'User'
  }
};

// Simulates a delay to mimic network requests
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export const mockSupabase = {
  auth: {
    // Mock sign in with OTP (magic link)
    signInWithOtp: async ({ email }) => {
      console.log('MOCK: Sending magic link to', email);
      await delay(1000); // Simulate network delay
      
      // Store the email for later use
      localStorage.setItem('mockAuthEmail', email);
      
      return { 
        data: {}, 
        error: null 
      };
    },
    
    // Mock get user
    getUser: async () => {
      console.log('MOCK: Getting user');
      await delay(500);
      
      const email = localStorage.getItem('mockAuthEmail');
      if (email) {
        return {
          data: {
            user: {
              ...MOCK_USER,
              email
            }
          },
          error: null
        };
      }
      
      return {
        data: { user: null },
        error: null
      };
    },
    
    // Mock get session
    getSession: async () => {
      console.log('MOCK: Getting session');
      await delay(500);
      
      const email = localStorage.getItem('mockAuthEmail');
      if (email) {
        return {
          data: {
            session: {
              user: {
                ...MOCK_USER,
                email
              }
            }
          },
          error: null
        };
      }
      
      return {
        data: { session: null },
        error: null
      };
    },
    
    // Mock sign out
    signOut: async () => {
      console.log('MOCK: Signing out');
      await delay(500);
      localStorage.removeItem('mockAuthEmail');
      return { error: null };
    },
    
    // Mock auth state change listener
    onAuthStateChange: (callback) => {
      console.log('MOCK: Setting up auth state change listener');
      
      // Return a mock subscription
      return {
        data: {
          subscription: {
            unsubscribe: () => console.log('MOCK: Unsubscribed from auth state changes')
          }
        }
      };
    },
    
    // Mock sign in with OAuth
    signInWithOAuth: async ({ provider }) => {
      console.log(`MOCK: Signing in with ${provider}`);
      await delay(1000);
      
      // For testing, we'll just set a mock user
      localStorage.setItem('mockAuthEmail', 'oauth@example.com');
      
      return { error: null };
    }
  }
};
