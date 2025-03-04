import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import { createClient } from '@supabase/supabase-js';

dotenv.config();

// Initialize Supabase client
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error('Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be provided in environment variables');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey, {
  auth: { persistSession: false }
});

// Migration scripts
const MIGRATIONS_DIR = path.join(process.cwd(), 'migrations');

async function runMigrations() {
  console.log('Starting database migrations...');
  
  try {
    // Create migrations table if it doesn't exist
    const { error: tableError } = await supabase.rpc('create_migrations_table_if_not_exists');
    if (tableError) {
      throw tableError;
    }
    
    // Get list of migration files
    const files = fs.readdirSync(MIGRATIONS_DIR)
      .filter(file => file.endsWith('.sql'))
      .sort(); // Sort to ensure migrations run in order
    
    // Get already applied migrations
    const { data: appliedMigrations, error: fetchError } = await supabase
      .from('migrations')
      .select('name');
    
    if (fetchError) {
      throw fetchError;
    }
    
    const appliedMigrationNames = appliedMigrations.map(m => m.name);
    
    // Run pending migrations
    for (const file of files) {
      if (!appliedMigrationNames.includes(file)) {
        console.log(`Running migration: ${file}`);
        
        const sql = fs.readFileSync(path.join(MIGRATIONS_DIR, file), 'utf8');
        const { error: migrationError } = await supabase.rpc('run_sql', { sql });
        
        if (migrationError) {
          console.error(`Error running migration ${file}:`, migrationError);
          throw migrationError;
        }
        
        // Record the migration
        const { error: insertError } = await supabase
          .from('migrations')
          .insert({ name: file, applied_at: new Date() });
        
        if (insertError) {
          console.error(`Error recording migration ${file}:`, insertError);
          throw insertError;
        }
        
        console.log(`Completed migration: ${file}`);
      } else {
        console.log(`Skipping already applied migration: ${file}`);
      }
    }
    
    console.log('All migrations completed successfully!');
  } catch (error) {
    console.error('Migration error:', error);
    process.exit(1);
  }
}

// Create a stored procedure to create migrations table
async function setupMigrationsProcedure() {
  try {
    const { error } = await supabase.rpc('run_sql', {
      sql: `
        CREATE OR REPLACE FUNCTION create_migrations_table_if_not_exists()
        RETURNS void AS $$
        BEGIN
          CREATE TABLE IF NOT EXISTS migrations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            applied_at TIMESTAMP WITH TIME ZONE NOT NULL
          );
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
        
        CREATE OR REPLACE FUNCTION run_sql(sql TEXT)
        RETURNS void AS $$
        BEGIN
          EXECUTE sql;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
      `
    });
    
    if (error) {
      console.error('Error setting up migrations procedures:', error);
      process.exit(1);
    }
    
    console.log('Migration procedures created successfully');
  } catch (error) {
    console.error('Error setting up migrations procedures:', error);
    process.exit(1);
  }
}

// Create migrations directory if it doesn't exist
if (!fs.existsSync(MIGRATIONS_DIR)) {
  fs.mkdirSync(MIGRATIONS_DIR, { recursive: true });
}

// Create sample migration files
function createSampleMigrations() {
  // Create the initial schema migration
  const initialSchema = fs.readFileSync(path.join(process.cwd(), 'schema.sql'), 'utf8');
  fs.writeFileSync(
    path.join(MIGRATIONS_DIR, '001_initial_schema.sql'),
    initialSchema
  );
  
  // Create RLS policies migration
  const rlsPolicies = fs.readFileSync(path.join(process.cwd(), 'rls_policies.sql'), 'utf8');
  fs.writeFileSync(
    path.join(MIGRATIONS_DIR, '002_rls_policies.sql'),
    rlsPolicies
  );
  
  // Create triggers migration
  const triggers = fs.readFileSync(path.join(process.cwd(), 'triggers.sql'), 'utf8');
  fs.writeFileSync(
    path.join(MIGRATIONS_DIR, '003_triggers.sql'),
    triggers
  );
  
  // Create stored procedures migration
  const procedures = fs.readFileSync(path.join(process.cwd(), 'procedures.sql'), 'utf8');
  fs.writeFileSync(
    path.join(MIGRATIONS_DIR, '004_procedures.sql'),
    procedures
  );
  
  // Create indexes migration
  const indexes = fs.readFileSync(path.join(process.cwd(), 'indexes.sql'), 'utf8');
  fs.writeFileSync(
    path.join(MIGRATIONS_DIR, '005_indexes.sql'),
    indexes
  );
  
  // Create views migration
  const views = fs.readFileSync(path.join(process.cwd(), 'views.sql'), 'utf8');
  fs.writeFileSync(
    path.join(MIGRATIONS_DIR, '006_views.sql'),
    views
  );
  
  console.log('Sample migrations created successfully');
}

// Run the script
async function main() {
  if (process.argv.includes('--setup')) {
    await setupMigrationsProcedure();
  } else if (process.argv.includes('--create-samples')) {
    createSampleMigrations();
  } else {
    await setupMigrationsProcedure();
    await runMigrations();
  }
}

main().catch(console.error);