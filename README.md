# Financial Advice Platform

## Overview

This platform is a multi-channel financial advice application built to provide Australian users with personalized insights about their superannuation and retirement planning. The system leverages AI to analyze user information, compare super funds, project retirement balances, and calculate retirement outcomes.

## Architecture

### Core Components

- **Python Backend**: Powers the financial analysis logic and chat processing
- **Supabase Database**: Stores user profiles, chat history, and financial data
- **Gradio Web UI**: Provides a simple, web-based chat interface
- **Multi-channel Integrations**: Support for various messaging platforms (WhatsApp, Instagram, Facebook)
- **Advisor Workstation**: Separate application for financial advisors to manage client relationships

### Data Flow

1. Users interact with the system via web chat or messaging platforms
2. The chat backend processes queries using OpenAI's GPT models
3. User data and interactions are stored in Supabase
4. Financial calculations are performed with the Python backend
5. Advisors can access client data through the advisor workstation

## Technical Stack

- **Backend**: Python 3.9
- **Database**: PostgreSQL (via Supabase)
- **Authentication**: Supabase Auth
- **AI/ML**: OpenAI GPT-4
- **Frontend**: Gradio for web interface
- **Deployment**: Render for hosting
- **Database Migrations**: Node.js scripts

## Key Files & Directories

- `app.py`: Main application entry point and Gradio UI setup
- `backend/`: Core backend functionality
  - `main.py`: Primary query processing logic
  - `helper.py`: Utility functions for OpenAI integration
  - `utils.py`: General utility functions for financial calculations
  - `cashflow.py`: Cashflow and tax calculations
  - `charts.py`: Visualization generation
  - `constants.py`: System-wide constants and economic assumptions
- `finance-advice-db-setup/`: Database migration and setup tools
  - `scripts/migrate.js`: Database migration runner
  - `migrations/`: SQL migration files
- `.devcontainer/`: Development container configuration
- `requirements.txt`: Python dependencies

## Database Schema

The Supabase database includes several key tables:

- `users`: Core user profiles with authentication links
- `user_financial_profiles`: Financial information for each user
- `chat_sessions`: Record of user chat sessions across platforms
- `chat_messages`: Individual messages within chat sessions
- `user_intents`: Captured user intents and analysis data
- `advisors`: Financial advisor profiles
- `advisor_client_relationships`: Links between advisors and clients
- `audit_logs`: Compliance and security audit trail
- `privacy_consents`: User privacy consent tracking

## Core Functionality

### Financial Analysis Capabilities

1. **Fund Comparison**: Compare fees between superannuation funds
2. **Balance Projection**: Estimate retirement balance based on current super, contributions, and investment returns
3. **Retirement Outcome**: Analyze how long savings might last based on drawdown strategy
4. **Fee Analysis**: Identify the lowest fee super fund for a user's situation

### User State Management

The system maintains conversational state to collect required information through natural dialogue:
- Current age
- Super balance
- Current income
- Super fund
- Retirement age
- Etc.

### Privacy & Compliance

- Built to comply with Australian Privacy Principles (APP)
- Includes comprehensive consent tracking
- Implements row-level security policies
- Records detailed audit logs for regulatory compliance
- Supports data anonymization and export

## Integration Patterns

### Supabase Integration

- Authentication using Supabase Auth
- Row-level security for data access control
- Database triggers for audit logging
- Stored procedures for common operations

### Multi-Platform Support

The system is designed to support multiple chat interfaces through the `platform` field in chat sessions, enabling:
- Web chat (via Gradio)
- WhatsApp
- Facebook Messenger
- Instagram Messenger
- Other messaging platforms

### Advisor Workstation

A separate application allows financial advisors to:
- View client profiles and financial data
- Analyze chat history and user intents
- Monitor client financial progression
- Provide personalized recommendations

## Deployment

The application is designed to be deployed on Render with the following configurations:
- Web service for the Python application
- Background workers for long-running tasks
- Supabase for database and authentication

## Security Features

- Environment variable management for secrets
- Row-level security policies in the database
- Audit logging for sensitive operations
- Privacy compliance functions
- Data anonymization capabilities

## Australian Financial Context

The system incorporates Australian-specific financial elements:
- Superannuation fund data and comparison
- Australian tax calculations
- ASFA retirement standards
- Compliance with Australian financial regulations
- APP (Australian Privacy Principles) compliance

## Development Setup

1. Clone the repository
2. Configure environment variables (OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY)
3. Install dependencies: `pip install -r requirements.txt`
4. Run database migrations
5. Start the application: `python app.py`

## Key Economic Assumptions

Default assumptions for financial calculations:
- Wage growth: 3.0%
- Employer contribution rate: 12.0%
- Investment return: 8.0%
- Inflation rate: 2.5%
- Retirement investment return: 6.0%

## License

Proprietary - All rights reserved

---

© 2025 Financial Advice Platform
