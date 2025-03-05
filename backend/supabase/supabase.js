import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';

dotenv.config();

// Initialize Supabase client
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_KEY; // Use service key for server operations

if (!supabaseUrl || !supabaseKey) {
  throw new Error('Supabase URL and key must be provided in environment variables');
}

const supabase = createClient(supabaseUrl, supabaseKey, {
  auth: {
    persistSession: false, // For server-side use
    autoRefreshToken: false,
  },
});

export { supabase };