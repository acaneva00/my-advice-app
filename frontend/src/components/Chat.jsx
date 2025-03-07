import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';

const Chat = () => {
  const { user, signOut } = useAuth();
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [session, setSession] = useState(null);
  const messagesEndRef = useRef(null);
  
// Scroll to bottom of messages
const scrollToBottom = () => {
  if (messagesEndRef.current) {
    messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
  }
};

  
  // Load or create chat session on mount
  useEffect(() => {
    const loadOrCreateSession = async () => {
      try {
        // For demo purposes, create some sample messages
        setMessages([
          {
            id: '1',
            sender_type: 'assistant',
            content: 'Hello! I\'m your financial assistant. How can I help you today?',
            sent_at: new Date().toISOString()
          }
        ]);
        
        // In a real implementation, you would call your API here
        // const response = await fetch('/api/chat/session', {...});
        // const data = await response.json();
        // setSession(data.session_id);
        
      } catch (error) {
        console.error('Error setting up chat session:', error);
      }
    };
    
    if (user) {
      loadOrCreateSession();
    }
  }, [user]);
  
  // Scroll to bottom whenever messages update
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  // Send a message
  const sendMessage = async (e) => {
    e.preventDefault();
    if (!newMessage.trim()) return;
    
    // Optimistically add message to UI
    const userMessage = {
      id: Date.now().toString(),
      sender_type: 'user',
      content: newMessage,
      sent_at: new Date().toISOString()
    };
    
    setMessages(prev => [...prev, userMessage]);
    setNewMessage('');
    setLoading(true);
    
    try {
      // Get the previous system response (if any)
      const previousSystemResponse = messages.length > 0 
        ? messages.filter(m => m.sender_type === 'assistant').pop()?.content || ""
        : "";
      
      // Get the full chat history
      const fullHistory = messages.map(m => 
        `${m.sender_type === 'user' ? 'User' : 'Assistant'}: ${m.content}`
      ).join('\n');
      
      // Call the backend API
      const response = await fetch('/api/chat/process', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_query: newMessage,
          previous_system_response: previousSystemResponse,
          full_history: fullHistory,
          user_id: user?.id || 'anonymous'
        }),
      });
      
      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }
      
      const responseData = await response.json();
      
      // Add the assistant's response to the UI
      const assistantMessage = {
        id: Date.now().toString() + '1',
        sender_type: 'assistant',
        content: responseData.response || "I'm sorry, I couldn't process your request.",
        sent_at: new Date().toISOString()
      };
      
      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error sending/processing message:', error);
      setLoading(false);
      
      // Add error message
      const errorMessage = {
        id: Date.now().toString() + 'error',
        sender_type: 'system',
        content: 'There was an error processing your message. Please try again.',
        sent_at: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMessage]);
    }
  };

  // Define styles for the chat interface
  const containerStyle = {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    backgroundColor: '#F0F0F0'
  };

  const headerStyle = {
    backgroundColor: 'white',
    boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
    padding: '1rem'
  };

  const headerContainerStyle = {
    maxWidth: '7xl',
    margin: '0 auto',
    padding: '0 1rem',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  };

  const titleStyle = {
    fontSize: '1.25rem',
    fontWeight: 'bold',
    fontFamily: 'Montserrat, sans-serif',
    color: '#1F2937'
  };

  const buttonStyle = {
    padding: '0.5rem 1rem',
    border: 'none',
    borderRadius: '0.375rem',
    boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
    fontSize: '0.875rem',
    fontWeight: '500',
    color: 'white',
    backgroundColor: '#3EA76F',
    cursor: 'pointer'
  };

  const chatContainerStyle = {
    flexGrow: 1,
    display: 'flex',
    flexDirection: 'column',
    maxWidth: '48rem',
    margin: '0 auto',
    width: '100%',
    overflow: 'hidden'
  };

  const messagesContainerStyle = {
    flexGrow: 1,
    overflowY: 'auto',
    padding: '1rem'
  };

  const emptyStateStyle = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    textAlign: 'center'
  };

  const emptyStateContentStyle = {
    maxWidth: '24rem'
  };

  const emptyStateTitleStyle = {
    fontSize: '1.5rem',
    fontWeight: 'bold',
    color: '#1F2937',
    marginBottom: '0.5rem'
  };

  const emptyStateDescriptionStyle = {
    color: '#4B5563',
    marginBottom: '1rem'
  };

  const messageContainerStyle = (isUser) => ({
    marginBottom: '1rem',
    textAlign: isUser ? 'right' : 'left'
  });

  const messageBubbleStyle = (sender) => ({
    display: 'inline-block',
    padding: '0.5rem 1rem',
    borderRadius: '0.5rem',
    boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
    backgroundColor: sender === 'user' ? '#3EA76F' : sender === 'system' ? '#FEE2E2' : 'white',
    color: sender === 'user' ? 'white' : sender === 'system' ? '#991B1B' : '#1F2937',
    maxWidth: '24rem',
    wordBreak: 'break-word'
  });

  const timestampStyle = {
    fontSize: '0.75rem',
    color: '#6B7280',
    marginTop: '0.25rem'
  };

  const formStyle = {
    display: 'flex',
    padding: '1rem',
    backgroundColor: 'white',
    borderTop: '1px solid #E5E5E5'
  };

  const inputStyle = {
    flexGrow: 1,
    appearance: 'none',
    border: '1px solid #D1D5DB',
    borderRight: 'none',
    borderTopLeftRadius: '0.375rem',
    borderBottomLeftRadius: '0.375rem',
    padding: '0.5rem 1rem',
    backgroundColor: 'white',
    color: '#1F2937',
    outline: 'none'
  };

  const sendButtonStyle = {
    backgroundColor: '#3EA76F',
    color: 'white',
    borderTopRightRadius: '0.375rem',
    borderBottomRightRadius: '0.375rem',
    padding: '0 1rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    border: 'none'
  };

  return (
    <div style={containerStyle}>
      <header style={headerStyle}>
        <div style={headerContainerStyle}>
          <h1 style={titleStyle}>Money Empowered</h1>
          <button
            onClick={signOut}
            style={buttonStyle}
          >
            Logout
          </button>
        </div>
      </header>
      
      <div style={chatContainerStyle}>
        <div style={messagesContainerStyle}>
          {messages.length === 0 ? (
            <div style={emptyStateStyle}>
              <div style={emptyStateContentStyle}>
                <h2 style={emptyStateTitleStyle}>Welcome to Money Empowered</h2>
                <p style={emptyStateDescriptionStyle}>Ask me anything about your finances</p>
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <div 
                key={message.id} 
                style={messageContainerStyle(message.sender_type === 'user')}
              >
                <div style={messageBubbleStyle(message.sender_type)}>
                  <div dangerouslySetInnerHTML={{ __html: message.content }} />
                </div>
                <div style={timestampStyle}>
                  {new Date(message.sent_at).toLocaleTimeString()}
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
        
        <div style={formStyle}>
          <input
            type="text"
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            disabled={loading}
            placeholder="Type your message here..."
            style={inputStyle}
          />
          <button
            type="button"
            disabled={loading}
            onClick={sendMessage}
            style={sendButtonStyle}
          >
            {loading ? (
              <svg style={{
                animation: 'spin 1s linear infinite',
                height: '1.25rem',
                width: '1.25rem',
                color: 'white'
              }} viewBox="0 0 24 24">
                <circle style={{
                  opacity: 0.25
                }} cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path style={{
                  opacity: 0.75
                }} fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            ) : (
              <span>Send</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Chat;
