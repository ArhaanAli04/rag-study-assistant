import { useState } from "react";
import { Link } from "react-router-dom";
import { Mail, Lock, Sparkles, AlertCircle, UserPlus, CheckCircle } from "lucide-react";

export default function RegisterForm({ onSubmit, error }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [passwordError, setPasswordError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validate password match
    if (password !== confirmPassword) {
      setPasswordError("Passwords do not match");
      return;
    }
    
    // Validate password length
    if (password.length < 6) {
      setPasswordError("Password must be at least 6 characters");
      return;
    }
    
    setPasswordError("");
    setIsLoading(true);
    try {
      await onSubmit(email, password);
    } finally {
      setIsLoading(false);
    }
  };

  // Password strength indicator
  const getPasswordStrength = () => {
    if (password.length === 0) return { label: "", color: "" };
    if (password.length < 6) return { label: "Weak", color: "text-destructive" };
    if (password.length < 10) return { label: "Medium", color: "text-yellow-500" };
    return { label: "Strong", color: "text-green-500" };
  };

  const strength = getPasswordStrength();

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: "#0F0F0F" }}>
      {/* Background gradient effect */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div 
          className="absolute top-1/4 right-1/4 w-96 h-96 bg-primary/10 rounded-full blur-3xl"
          style={{ background: "radial-gradient(circle, rgba(124, 58, 237, 0.15) 0%, transparent 70%)" }}
        />
        <div 
          className="absolute bottom-1/4 left-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl"
          style={{ background: "radial-gradient(circle, rgba(59, 130, 246, 0.15) 0%, transparent 70%)" }}
        />
      </div>

      {/* Register Card */}
      <div 
        className="glass border border-border/50 rounded-2xl p-8 w-full max-w-md relative z-10"
        style={{ background: "rgba(20, 20, 20, 0.8)" }}
      >
        {/* Logo/Title */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-[#7C3AED] to-[#3B82F6] mb-4">
            <UserPlus className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] bg-clip-text text-transparent mb-2">
            Create Account
          </h1>
          <p className="text-muted-foreground text-sm">Join RAG Study Assistant today</p>
        </div>

        {/* Error Messages */}
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
            <p className="text-sm text-destructive">{error}</p>
          </div>
        )}

        {passwordError && (
          <div className="mb-6 p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
            <p className="text-sm text-destructive">{passwordError}</p>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Email Input */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Email
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full pl-11 pr-4 py-3 bg-white/5 border border-border/50 rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all"
              />
            </div>
          </div>

          {/* Password Input */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full pl-11 pr-4 py-3 bg-white/5 border border-border/50 rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all"
              />
            </div>
            {/* Password Strength Indicator */}
            {password.length > 0 && (
              <div className="mt-2 flex items-center gap-2">
                <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                  <div 
                    className={`h-full transition-all duration-300 ${
                      password.length < 6 ? 'bg-destructive w-1/3' :
                      password.length < 10 ? 'bg-yellow-500 w-2/3' :
                      'bg-green-500 w-full'
                    }`}
                  />
                </div>
                <span className={`text-xs font-medium ${strength.color}`}>
                  {strength.label}
                </span>
              </div>
            )}
          </div>

          {/* Confirm Password Input */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Confirm Password
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full pl-11 pr-4 py-3 bg-white/5 border border-border/50 rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all"
              />
              {/* Match Indicator */}
              {confirmPassword.length > 0 && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  {password === confirmPassword ? (
                    <CheckCircle className="w-5 h-5 text-green-500" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-destructive" />
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Register Button */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg font-medium hover:opacity-90 transition-all shadow-lg shadow-primary/20 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        {/* Login Link */}
        <div className="mt-6 text-center">
          <p className="text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link 
              to="/login" 
              className="text-primary font-medium hover:underline"
            >
              Sign in
            </Link>
          </p>
        </div>

        {/* Privacy Notice */}
        <p className="mt-6 text-xs text-center text-muted-foreground">
          By creating an account, you agree to our Terms of Service and Privacy Policy
        </p>
      </div>
    </div>
  );
}
