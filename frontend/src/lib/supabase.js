import { createClient } from '@supabase/supabase-js';
import { mockSupabase } from './mockAuth';

// Check if we're in development mode
const isDevelopment = process.env.NODE_ENV === 'development';

// Check if we should use mock authentication (for development/testing)
const useMockAuth = isDevelopment && (process.env.REACT_APP_USE_MOCK_AUTH === 'true' || true);

let supabase;

if (useMockAuth) {
  console.log('🔧 Using mock authentication service for development');
  supabase = mockSupabase;
} else {
  const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
  const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY;

  console.log("Initializing Supabase client with:");
  console.log("URL:", supabaseUrl || "Missing");
  console.log("Key:", supabaseAnonKey ? "Found (length: " + supabaseAnonKey.length + ")" : "Missing");

  if (!supabaseUrl || !supabaseAnonKey) {
    console.error('Supabase credentials missing!');
  }

  // Create the Supabase client with additional options
  supabase = createClient(
    supabaseUrl,
    supabaseAnonKey,
    {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true
      },
      global: {
        fetch: (...args) => {
          console.log('Supabase fetch request:', args[0]);
          return fetch(...args);
        }
      }
    }
  );

  console.log('Supabase client initialized successfully');

  // Test network connectivity to Supabase
  const testConnection = async () => {
    try {
      const response = await fetch(`${supabaseUrl}/auth/v1/health`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'apikey': supabaseAnonKey
        }
      });
      
      if (response.ok) {
        console.log('Successfully connected to Supabase API');
      } else {
        console.error('Failed to connect to Supabase API:', response.status, response.statusText);
      }
    } catch (error) {
      console.error('Network error when testing Supabase connection:', error);
    }
  };

  // Test the connection
  testConnection();
}

export { supabase };
