// test-connection.js
import { createClient } from '@supabase/supabase-js';
import dotenv from 'dotenv';

dotenv.config();

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error('Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in your environment');
  process.exit(1);
}

console.log('URL:', supabaseUrl ? 'Found (value hidden)' : 'Missing');
console.log('Key:', supabaseKey ? 'Found (value hidden)' : 'Missing');

const supabase = createClient(supabaseUrl, supabaseKey);

async function testConnection() {
  try {
    // Try to query the information_schema instead
    const { data, error } = await supabase
      .from('information_schema.tables')
      .select('table_name')
      .eq('table_schema', 'public')
      .limit(10);
    
    if (error) {
      console.error('Database query error:', error);
      
      // If that fails, let's try a simpler approach
      console.log('Trying an alternate approach...');
      
      // Create a test table
      const { error: createError } = await supabase.rpc('run_sql', {
        sql: 'CREATE TABLE IF NOT EXISTS test_connection (id serial primary key, test_date timestamp default now())'
      });
      
      if (createError) {
        console.error('Error creating test table:', createError);
        return;
      }
      
      console.log('Successfully created a test table. Connection is working!');
    } else {
      console.log('Connection successful!');
      console.log('Tables in your database:');
      if (data.length === 0) {
        console.log('No tables found in the public schema.');
      } else {
        data.forEach(table => {
          console.log(`- ${table.table_name}`);
        });
      }
    }
  } catch (error) {
    console.error('Unexpected error:', error);
  }
}

testConnection();