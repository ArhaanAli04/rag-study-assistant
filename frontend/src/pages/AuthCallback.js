import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, XCircle } from 'lucide-react';

export default function AuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState('');

  useEffect(() => {
    const token = searchParams.get('token');
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setError('OAuth authentication failed. Please try again.');
      setTimeout(() => navigate('/login'), 3000);
      return;
    }

    if (token) {
      // Store token
      localStorage.setItem('token', token);
      
      // Decode token to get user info (optional)
      try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        console.log('OAuth successful for:', payload.sub);
      } catch (e) {
        console.error('Token decode error:', e);
      }

      // Redirect to chat
      navigate('/chat', { replace: true });
    } else {
      setError('No authentication token received');
      setTimeout(() => navigate('/login'), 3000);
    }
  }, [searchParams, navigate]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4" style={{ background: "#0F0F0F" }}>
        <div className="glass border border-destructive/50 rounded-2xl p-8 w-full max-w-md text-center">
          <XCircle className="w-16 h-16 text-destructive mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-foreground mb-2">Authentication Failed</h2>
          <p className="text-muted-foreground mb-4">{error}</p>
          <p className="text-sm text-muted-foreground">Redirecting to login...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: "#0F0F0F" }}>
      <div className="glass border border-border/50 rounded-2xl p-8 w-full max-w-md text-center">
        <Loader2 className="w-16 h-16 text-primary mx-auto mb-4 animate-spin" />
        <h2 className="text-xl font-semibold text-foreground mb-2">Completing Sign In</h2>
        <p className="text-muted-foreground">Please wait while we sign you in...</p>
      </div>
    </div>
  );
}
