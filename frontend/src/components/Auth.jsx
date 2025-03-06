import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';

const Auth = () => {
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [message, setMessage] = useState('');
  const [authMode, setAuthMode] = useState('login');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  
  const { signInWithOTP, signInWithProvider } = useAuth();

  // Email authentication
  const handleEmailAuth = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      if (authMode === 'login') {
        // Send magic link
        const { error } = await signInWithOTP({
          email,
          options: {
            emailRedirectTo: window.location.origin,
          },
        });

        if (error) throw error;
        setMessage('Check your email for the login link!');
      } else {
        // Sign up flow
        const { error } = await signInWithOTP({
          email,
          options: {
            data: { 
              first_name: firstName,
              last_name: lastName
            },
            emailRedirectTo: window.location.origin,
          },
        });

        if (error) throw error;
        setMessage('Check your email for the confirmation link!');
      }
    } catch (error) {
      setMessage(error.error_description || error.message);
    } finally {
      setLoading(false);
    }
  };

  // Phone authentication
  const handlePhoneAuth = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const { error } = await signInWithOTP({
        phone,
      });

      if (error) throw error;
      setMessage('Check your phone for the verification code!');
    } catch (error) {
      setMessage(error.error_description || error.message);
    } finally {
      setLoading(false);
    }
  };

  // Social authentication
  const handleSocialAuth = async (provider) => {
    try {
      const { error } = await signInWithProvider(provider);
      
      if (error) throw error;
    } catch (error) {
      setMessage(error.error_description || error.message);
    }
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '500px', margin: '0 auto' }}>
      <h1 style={{ textAlign: 'center', color: '#3EA76F', marginBottom: '2rem' }}>Money Empowered</h1>
      
      <div style={{ backgroundColor: 'white', padding: '2rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }}>
        <h2 style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          {authMode === 'login' ? 'Log in to your account' : 
           authMode === 'signup' ? 'Create a new account' : 
           'Login with your phone'}
        </h2>

        {message && (
          <div style={{ padding: '1rem', backgroundColor: '#f0f9ff', borderRadius: '4px', marginBottom: '1rem', color: '#0369a1' }}>
            {message}
          </div>
        )}

        {authMode === 'phone' ? (
          <form onSubmit={handlePhoneAuth}>
            <div style={{ marginBottom: '1rem' }}>
              <label htmlFor="phone" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                Phone Number
              </label>
              <input
                id="phone"
                type="tel"
                placeholder="+61XXXXXXXXX"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                style={{ 
                  width: '100%', 
                  padding: '0.75rem',
                  border: '1px solid #d1d5db',
                  borderRadius: '4px'
                }}
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{ 
                width: '100%',
                padding: '0.75rem',
                backgroundColor: '#3EA76F',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                fontWeight: 500,
                cursor: 'pointer'
              }}
            >
              {loading ? 'Loading...' : 'Send Code'}
            </button>

            <div style={{ textAlign: 'center', marginTop: '1rem' }}>
              <button 
                type="button"
                onClick={() => setAuthMode('login')}
                style={{ 
                  background: 'none',
                  border: 'none',
                  color: '#3EA76F',
                  cursor: 'pointer' 
                }}
              >
                Use email instead
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleEmailAuth}>
            {authMode === 'signup' && (
              <>
                <div style={{ marginBottom: '1rem' }}>
                  <label htmlFor="firstName" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                    First Name
                  </label>
                  <input
                    id="firstName"
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    style={{ 
                      width: '100%', 
                      padding: '0.75rem',
                      border: '1px solid #d1d5db',
                      borderRadius: '4px'
                    }}
                    required
                  />
                </div>
                <div style={{ marginBottom: '1rem' }}>
                  <label htmlFor="lastName" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                    Last Name
                  </label>
                  <input
                    id="lastName"
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    style={{ 
                      width: '100%', 
                      padding: '0.75rem',
                      border: '1px solid #d1d5db',
                      borderRadius: '4px'
                    }}
                  />
                </div>
              </>
            )}
            
            <div style={{ marginBottom: '1rem' }}>
              <label htmlFor="email" style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                Email Address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{ 
                  width: '100%', 
                  padding: '0.75rem',
                  border: '1px solid #d1d5db',
                  borderRadius: '4px'
                }}
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{ 
                width: '100%',
                padding: '0.75rem',
                backgroundColor: '#3EA76F',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                fontWeight: 500,
                cursor: 'pointer'
              }}
            >
              {loading ? 'Loading...' : authMode === 'login' ? 'Log In' : 'Sign Up'}
            </button>

            <div style={{ textAlign: 'center', marginTop: '1rem' }}>
              <button 
                type="button"
                onClick={() => setAuthMode(authMode === 'login' ? 'signup' : 'login')}
                style={{ 
                  background: 'none',
                  border: 'none',
                  color: '#3EA76F',
                  cursor: 'pointer' 
                }}
              >
                {authMode === 'login' ? "Don't have an account? Sign up" : "Already have an account? Log in"}
              </button>
              <div style={{ marginTop: '0.5rem' }}>
                <button 
                  type="button"
                  onClick={() => setAuthMode('phone')}
                  style={{ 
                    background: 'none',
                    border: 'none',
                    color: '#3EA76F',
                    cursor: 'pointer' 
                  }}
                >
                  Login with phone instead
                </button>
              </div>
            </div>
          </form>
        )}

        <div style={{ textAlign: 'center', marginTop: '2rem', position: 'relative' }}>
          <div style={{ 
            borderTop: '1px solid #e5e7eb', 
            position: 'absolute', 
            top: '50%', 
            width: '100%' 
          }}></div>
          <span style={{ 
            backgroundColor: 'white', 
            padding: '0 0.75rem', 
            position: 'relative', 
            color: '#6b7280' 
          }}>Or continue with</span>
        </div>

        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: '1fr 1fr', 
          gap: '1rem', 
          marginTop: '1.5rem' 
        }}>
          <button
            type="button"
            onClick={() => handleSocialAuth('google')}
            style={{ 
              padding: '0.75rem',
              border: '1px solid #d1d5db',
              borderRadius: '4px',
              backgroundColor: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer'
            }}
          >
            <span>Google</span>
          </button>
          <button
            type="button"
            onClick={() => handleSocialAuth('apple')}
            style={{ 
              padding: '0.75rem',
              border: '1px solid #d1d5db',
              borderRadius: '4px',
              backgroundColor: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer'
            }}
          >
            <span>Apple</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default Auth;