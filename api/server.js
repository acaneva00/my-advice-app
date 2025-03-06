const express = require('express');
const cors = require('cors');
const axios = require('axios');
const { createClient } = require('@supabase/supabase-js');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json());

// Set up Supabase client
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_KEY;
const supabase = createClient(supabaseUrl, supabaseServiceKey);

// Middleware to verify JWT
const authenticateToken = async (req, res, next) => {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];
  
  if (!token) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  
  try {
    const { data, error } = await supabase.auth.getUser(token);
    
    if (error || !data.user) {
      return res.status(401).json({ error: 'Invalid token' });
    }
    
    req.user = data.user;
    next();
  } catch (error) {
    return res.status(500).json({ error: 'Authentication error' });
  }
};

// API endpoints
app.post('/api/chat/session', authenticateToken, async (req, res) => {
  try {
    // Call your Python backend to create or get a session
    const response = await axios.post(
      `${process.env.PYTHON_BACKEND_URL}/create_session`,
      {
        user_id: req.user.id,
        platform: req.body.platform || 'webchat'
      }
    );
    
    res.json(response.data);
  } catch (error) {
    console.error('Error creating session:', error);
    res.status(500).json({ error: 'Failed to create session' });
  }
});

app.get('/api/chat/history', authenticateToken, async (req, res) => {
  try {
    // Call your Python backend to get chat history
    const response = await axios.get(
      `${process.env.PYTHON_BACKEND_URL}/chat_history`,
      {
        params: {
          session_id: req.query.session_id
        }
      }
    );
    
    res.json(response.data);
  } catch (error) {
    console.error('Error fetching chat history:', error);
    res.status(500).json({ error: 'Failed to fetch chat history' });
  }
});

app.post('/api/chat/message', authenticateToken, async (req, res) => {
  try {
    // Call your Python backend to record a message
    const response = await axios.post(
      `${process.env.PYTHON_BACKEND_URL}/record_message`,
      {
        session_id: req.body.session_id,
        content: req.body.content,
        sender_type: req.body.sender_type
      }
    );
    
    res.json(response.data);
  } catch (error) {
    console.error('Error sending message:', error);
    res.status(500).json({ error: 'Failed to send message' });
  }
});

app.post('/api/chat/process', authenticateToken, async (req, res) => {
  try {
    // Call your Python backend to process a message
    const response = await axios.post(
      `${process.env.PYTHON_BACKEND_URL}/process_query`,
      {
        session_id: req.body.session_id,
        user_message: req.body.user_message,
        user_id: req.user.id
      }
    );
    
    res.json(response.data);
  } catch (error) {
    console.error('Error processing message:', error);
    res.status(500).json({ error: 'Failed to process message' });
  }
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`API server running on port ${PORT}`);
});