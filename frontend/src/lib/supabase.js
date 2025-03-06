import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL;
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY;

console.log("Initializing Supabase client with:");
console.log("URL:", supabaseUrl ? "Found" : "Missing");
console.log("Key:", supabaseAnonKey ? "Found" : "Missing");

if (!supabaseUrl || !supabaseAnonKey) {
  console.error('Supabase credentials missing!');
}

export const supabase = createClient(
  supabaseUrl,
  supabaseAnonKey
);