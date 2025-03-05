import { supabase } from './supabase.js';

/**
 * Middleware to verify JWT and authenticate user
 * @param {Object} req - Express request object
 * @param {Object} res - Express response object
 * @param {Function} next - Express next function
 */
export const authenticateUser = async (req, res, next) => {
  try {
    // Get JWT from Authorization header
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ error: 'No authentication token provided' });
    }

    const token = authHeader.split(' ')[1];
    
    // Verify token with Supabase
    const { data, error } = await supabase.auth.getUser(token);
    
    if (error || !data.user) {
      return res.status(401).json({ error: 'Invalid or expired token' });
    }
    
    // Check if user is deleted in our database
    const { data: userData, error: userError } = await supabase
      .from('users')
      .select('is_deleted')
      .eq('id', data.user.id)
      .single();
      
    if (userError) {
      return res.status(401).json({ error: 'User not found' });
    }
    
    if (userData.is_deleted) {
      return res.status(403).json({ error: 'Account has been deleted' });
    }
    
    // Attach user to request object
    req.user = data.user;
    next();
  } catch (error) {
    console.error('Authentication error:', error);
    res.status(500).json({ error: 'Authentication error' });
  }
};

/**
 * Middleware to verify user has advisor role
 * @param {Object} req - Express request object
 * @param {Object} res - Express response object
 * @param {Function} next - Express next function
 */
export const requireAdvisorRole = async (req, res, next) => {
  try {
    // Check if user is authenticated
    if (!req.user) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    
    // Check for advisor role in metadata
    const hasAdvisorRole = req.user.app_metadata?.role === 'advisor';
    
    // Double-check in advisors table
    const { data, error } = await supabase
      .from('advisors')
      .select('is_active')
      .eq('auth_id', req.user.id)
      .single();
    
    if (error || !data || !data.is_active || !hasAdvisorRole) {
      return res.status(403).json({ error: 'Advisor access required' });
    }
    
    // Get advisor ID and attach to request
    const { data: advisorData } = await supabase
      .from('advisors')
      .select('id')
      .eq('auth_id', req.user.id)
      .single();
      
    req.advisorId = advisorData.id;
    next();
  } catch (error) {
    console.error('Advisor role verification error:', error);
    res.status(500).json({ error: 'Authorization error' });
  }
};

/**
 * Middleware to log API access for audit
 * @param {Object} req - Express request object
 * @param {Object} res - Express response object
 * @param {Function} next - Express next function
 */
export const auditApiAccess = async (req, res, next) => {
  try {
    if (req.user) {
      // Log API access to audit_logs table
      const { error } = await supabase
        .from('audit_logs')
        .insert({
          user_id: req.user.id,
          advisor_id: req.advisorId, // Will be null if not an advisor
          action_type: 'api_access',
          resource_type: 'api',
          resource_id: req.user.id, // Using user ID as resource ID for API access
          ip_address: req.ip,
          user_agent: req.headers['user-agent']
        });
        
      if (error) {
        console.error('Error logging API access:', error);
      }
    }
    
    next();
  } catch (error) {
    console.error('Audit logging error:', error);
    next(); // Continue even if audit logging fails
  }
};

/**
 * Middleware to check if privacy policies are accepted
 * @param {Object} req - Express request object
 * @param {Object} res - Express response object
 * @param {Function} next - Express next function
 */
export const requirePrivacyConsent = async (req, res, next) => {
  try {
    if (!req.user) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    
    // Skip for advisor role - they should have separate consent flow
    if (req.user.app_metadata?.role === 'advisor') {
      return next();
    }
    
    // Get latest privacy consents
    const { data, error } = await supabase
      .from('privacy_consents')
      .select('consent_type, version')
      .eq('user_id', req.user.id)
      .order('consented_at', { ascending: false });
      
    if (error) {
      console.error('Error checking privacy consent:', error);
      return res.status(500).json({ error: 'Error checking privacy consent' });
    }
    
    // Check if user has accepted latest privacy policy and terms
    const currentPrivacyVersion = process.env.PRIVACY_POLICY_VERSION || '1.0';
    const currentTermsVersion = process.env.TERMS_VERSION || '1.0';
    
    const hasPrivacy = data.some(c => 
      c.consent_type === 'privacy_policy' && c.version === currentPrivacyVersion);
      
    const hasTerms = data.some(c => 
      c.consent_type === 'terms_of_service' && c.version === currentTermsVersion);
    
    if (!hasPrivacy || !hasTerms) {
      return res.status(403).json({ 
        error: 'Privacy policy or terms not accepted',
        needsPrivacyConsent: !hasPrivacy,
        needsTermsConsent: !hasTerms,
        currentPrivacyVersion,
        currentTermsVersion
      });
    }
    
    next();
  } catch (error) {
    console.error('Privacy consent check error:', error);
    res.status(500).json({ error: 'Privacy consent check error' });
  }
};