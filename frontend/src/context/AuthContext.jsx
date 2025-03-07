import React, { createContext, useState, useEffect, useContext } from 'react';
import { supabase } from '../lib/supabase';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check for access token in URL hash (from magic link)
    const handleHashParams = async () => {
      // If we have a hash in the URL, it might be from a magic link
      if (window.location.hash) {
        try {
          console.log('Found hash in URL, processing...');
          
          // Check if it's a mock auth hash (for development)
          if (window.location.hash.includes('mock_auth=true')) {
            console.log('Processing mock auth hash');
            const params = new URLSearchParams(window.location.hash.substring(1));
            const email = params.get('email');
            
            if (email) {
              console.log('Mock auth with email:', email);
              localStorage.setItem('mockAuthEmail', email);
            }
            
            // Clear the hash
            window.history.replaceState(null, null, window.location.pathname);
          } else {
            // Let Supabase handle the hash params
            const { data, error } = await supabase.auth.getSession();
            
            if (error) {
              console.error('Error processing authentication hash:', error);
            } else if (data?.session) {
              console.log('Successfully authenticated via magic link');
              // Clear the hash from the URL without reloading the page
              window.history.replaceState(null, null, window.location.pathname);
            }
          }
        } catch (err) {
          console.error('Failed to process hash params:', err);
        }
      }
    };

    // Check if user is already logged in
    const getCurrentUser = async () => {
      try {
        await handleHashParams(); // Process hash params first
        const { data: { user } } = await supabase.auth.getUser();
        console.log('Current user:', user);
        setUser(user);
      } catch (error) {
        console.error('Error getting current user:', error);
      } finally {
        setLoading(false);
      }
    };

    getCurrentUser();

    // Set up auth listener
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setUser(session?.user || null);
        setLoading(false);
      }
    );

    return () => {
      if (subscription) {
        subscription.unsubscribe();
      }
    };
  }, []);

  const value = {
    signUp: (data) => supabase.auth.signUp(data),
    signIn: (data) => supabase.auth.signInWithPassword(data),
    signInWithOTP: (data) => supabase.auth.signInWithOtp(data),
    signInWithProvider: (provider) => 
      supabase.auth.signInWithOAuth({ provider, options: { redirectTo: window.location.origin } }),
    signOut: () => supabase.auth.signOut(),
    user,
    loading,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  return useContext(AuthContext);
};
