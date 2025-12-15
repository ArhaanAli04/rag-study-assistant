import { Menu, Moon, Sun, Settings, LogOut, FileText, MessageSquare, Brain, User, Key, Download, Bell, HelpCircle } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';

export default function TopNav({ user, onLogout, onToggleSidebar }) {
  const navigate = useNavigate();
  const location = useLocation();
  
  // State management
  
  const [showSettings, setShowSettings] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const settingsRef = useRef(null);


  // Close settings dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (settingsRef.current && !settingsRef.current.contains(event.target)) {
        setShowSettings(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);


  // Get user initials from email
  const getUserInitials = () => {
    if (!user?.email) return 'US';
    
    const emailPart = user.email.split('@')[0];
    if (emailPart.length < 2) return emailPart.toUpperCase();
    
    return emailPart.substring(0, 2).toUpperCase();
  };

  // Check current page
  const isDocumentsPage = location.pathname === '/documents';
  const isQuizPage = location.pathname === '/quiz';

  return (
    <>
    <header
      className="glass border-b border-border/50 px-4 lg:px-6 h-16 flex items-center justify-between"
      style={{ background: "rgba(15, 15, 15, 0.8)" }}
    >
      {/* Left Section */}
      <div className="flex items-center gap-3">
        <button 
          onClick={onToggleSidebar}
          className="p-2 hover:bg-white/5 rounded-lg transition-all"
          title="Toggle Sidebar"
        >
          <Menu className="w-5 h-5 text-foreground" />
        </button>
        <h1 className="text-xl font-semibold bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] bg-clip-text text-transparent">
          RAG Study Assistant
        </h1>
      </div>

      {/* Right Section */}
      <div className="flex items-center gap-2">
        {/* Quiz Button */}
        <button 
          onClick={() => navigate('/quiz')}
          className={`p-2 rounded-lg transition-all ${
            isQuizPage ? 'bg-primary/10 text-primary' : 'hover:bg-white/5 text-foreground'
          }`}
          title="Quiz"
        >
          <Brain className="w-5 h-5" />
        </button>

        {/* Documents/Chat Toggle */}
        {isDocumentsPage ? (
          <button 
            onClick={() => navigate('/chat')}
            className="p-2 hover:bg-white/5 rounded-lg transition-all"
            title="Back to Chat"
          >
            <MessageSquare className="w-5 h-5 text-foreground" />
          </button>
        ) : (
          <button 
            onClick={() => navigate('/documents')}
            className="p-2 hover:bg-white/5 rounded-lg transition-all"
            title="Documents"
          >
            <FileText className="w-5 h-5 text-foreground" />
          </button>
        )}


        {/* Settings Dropdown */}
        <div className="relative" ref={settingsRef}>
          <button 
            onClick={() => setShowSettings(!showSettings)}
            className={`p-2 rounded-lg transition-all ${
              showSettings ? 'bg-white/10' : 'hover:bg-white/5'
            }`}
            title="Settings"
          >
            <Settings className="w-5 h-5 text-foreground" />
          </button>

          {/* Dropdown Menu */}
          {showSettings && (
            <div className="absolute right-0 mt-2 w-64 bg-[#1F2937] border border-[#374151] rounded-lg shadow-xl z-[9999] py-2 animate-fade-in">
              {/* User Info Section */}
              <div className="px-4 py-3 border-b border-[#374151]">
                <div className="text-sm font-medium text-white truncate">
                  {user?.email || 'user@example.com'}
                </div>
                <div className="text-xs text-gray-400 mt-1">Free Plan</div>
              </div>

              {/* Settings Items */}
              <div className="py-1">
                <button 
                  className="settings-item"
                  onClick={() => {
                    setShowSettings(false);
                    // Navigate to account settings page
                    console.log('Account Settings');
                  }}
                >
                  <User className="w-4 h-4" />
                  <span>Account Settings</span>
                </button>
                
                <button 
                  className="settings-item"
                  onClick={() => {
                    setShowSettings(false);
                    setShowPasswordModal(true);
                    
                  }}
                >
                  <Key className="w-4 h-4" />
                  <span>Change Password</span>
                </button>

                <button 
                  className="settings-item"
                  onClick={() => {
                    setShowSettings(false);
                    console.log('Notifications');
                  }}
                >
                  <Bell className="w-4 h-4" />
                  <span>Notifications</span>
                </button>

                <button 
                  className="settings-item"
                  onClick={() => {
                    setShowSettings(false);
                    console.log('Export Data');
                  }}
                >
                  <Download className="w-4 h-4" />
                  <span>Export Data</span>
                </button>
              </div>

              {/* Help & Logout Section */}
              <div className="border-t border-[#374151] py-1">
                <button 
                  className="settings-item"
                  onClick={() => {
                    setShowSettings(false);
                    console.log('Help & Support');
                  }}
                >
                  <HelpCircle className="w-4 h-4" />
                  <span>Help & Support</span>
                </button>

                <button 
                  onClick={() => {
                    setShowSettings(false);
                    onLogout();
                  }}
                  className="settings-item text-red-400 hover:bg-red-500/10"
                >
                  <LogOut className="w-4 h-4" />
                  <span>Logout</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* User Avatar & Logout */}
        <div className="flex items-center gap-2 ml-2">
          {/* User Avatar with Dynamic Initials */}
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center text-sm font-semibold text-white hover:scale-105 transition-transform cursor-pointer"
            title={user?.email || 'User'}
          >
            {getUserInitials()}
          </button>

          {/* Logout Button */}
          <button 
            onClick={onLogout}
            className="p-2 hover:bg-white/5 rounded-lg transition-all"
            title="Logout"
          >
            <LogOut className="w-5 h-5 text-foreground" />
          </button>
        </div>
      </div>
    </header>
    {/* Modal */}
    {showPasswordModal && (
      <ChangePasswordModal 
        onClose={() => setShowPasswordModal(false)}
      />
    )}
  </>
  );
}

// Change Password Modal Component
function ChangePasswordModal({ onClose }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    // Validation
    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters long');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('New passwords do not match');
      return;
    }

    if (currentPassword === newPassword) {
      setError('New password must be different from current password');
      return;
    }

    setLoading(true);

    try {
      const token = localStorage.getItem('token');
      
      const response = await fetch('http://localhost:8000/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        alert('✅ Password changed successfully!');
        onClose();
      } else {
        setError(data.detail || 'Failed to change password');
      }
    } catch (error) {
      console.error('Error:', error);
      setError('Network error. Please check your connection and try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div 
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" 
      onClick={onClose}
    >
      <div 
        className="bg-[#1F2937] rounded-lg p-6 w-full max-w-md animate-fade-in" 
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl font-semibold mb-4 text-white">Change Password</h2>
        
        {/* Error Message */}
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Current Password */}
          <div>
            <label className="text-sm text-gray-400 block mb-1">
              Current Password
            </label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full px-3 py-2 bg-[#374151] border border-[#4B5563] rounded-lg text-white focus:ring-2 focus:ring-primary focus:outline-none"
              placeholder="Enter current password"
              required
              disabled={loading}
            />
          </div>

          {/* New Password */}
          <div>
            <label className="text-sm text-gray-400 block mb-1">
              New Password
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full px-3 py-2 bg-[#374151] border border-[#4B5563] rounded-lg text-white focus:ring-2 focus:ring-primary focus:outline-none"
              placeholder="Enter new password (min 8 characters)"
              required
              minLength={8}
              disabled={loading}
            />
            <p className="text-xs text-gray-500 mt-1">
              Must be at least 8 characters long
            </p>
          </div>

          {/* Confirm New Password */}
          <div>
            <label className="text-sm text-gray-400 block mb-1">
              Confirm New Password
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-3 py-2 bg-[#374151] border border-[#4B5563] rounded-lg text-white focus:ring-2 focus:ring-primary focus:outline-none"
              placeholder="Re-enter new password"
              required
              disabled={loading}
            />
          </div>

          {/* Buttons */}
          <div className="flex justify-end gap-2 mt-6">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg transition-colors text-white"
              disabled={loading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-primary hover:bg-primary/90 rounded-lg transition-colors text-white flex items-center gap-2"
              disabled={loading}
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Changing...</span>
                </>
              ) : (
                'Change Password'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
