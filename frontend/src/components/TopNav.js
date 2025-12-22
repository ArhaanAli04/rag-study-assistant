import { Menu, Moon, Sun, Settings, LogOut, FileText, MessageSquare, Brain, User, Key, Download, Bell, HelpCircle, Network } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import HelpSupportModal from './HelpSupportModal';
import ChangePasswordModal from './ChangePasswordModal';
import AccountSettingsModal from './AccountSettingsModal';
import { API_BASE_URL } from '../config/api';

export default function TopNav({ user, onLogout, onToggleSidebar }) {
  const navigate = useNavigate();
  const location = useLocation();
  
  // State management
  
  const [showSettings, setShowSettings] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [showHelpModal, setShowHelpModal] = useState(false);
  const [showAccountModal, setShowAccountModal] = useState(false);
  const [userName, setUserName] = useState('');
  const [profilePicture, setProfilePicture] = useState('');
  const [isOAuthUser, setIsOAuthUser] = useState(false);
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

  // Fetch user profile data
  useEffect(() => {
    const fetchUserProfile = async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_BASE_URL}/user/profile`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });

        if (response.ok) {
          const data = await response.json();
          setUserName(data.name || '');
          setProfilePicture(data.profile_picture || '');
          setIsOAuthUser(data.oauth_provider === 'google');
        }
      } catch (error) {
        console.error('Failed to fetch user profile:', error);
      }
    };

    fetchUserProfile();
  }, []);
  // Get user initials from name or email
  const getUserInitials = () => {
    // If name exists, use name
    if (userName && userName.trim()) {
      const nameParts = userName.trim().split(' ');
      
      if (nameParts.length >= 2) {
        // First name + Last name initials (e.g., "John Doe" → "JD")
        return (nameParts[0][0] + nameParts[nameParts.length - 1][0]).toUpperCase();
      } else {
        // Single name - take first 2 characters (e.g., "John" → "JO")
        return userName.substring(0, 2).toUpperCase();
      }
    }
    
    // Fallback to email if no name
    if (user?.email) {
      const emailPart = user.email.split('@')[0];
      if (emailPart.length < 2) return emailPart.toUpperCase();
      return emailPart.substring(0, 2).toUpperCase();
    }
    
    // Default fallback
    return 'US';
  };


  // Check current page
  const isDocumentsPage = location.pathname === '/documents';
  const isQuizPage = location.pathname === '/quiz';
  const isConceptMapsPage = location.pathname === '/concept-maps';
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
        {/* ← NEW: Concept Maps Button */}
        {isConceptMapsPage ? (
        <button 
          onClick={() => navigate('/chat')}
          className="p-2 hover:bg-white/5 rounded-lg transition-all"
          title="Back to Chat"
        >
          <MessageSquare className="w-5 h-5 text-foreground" />
        </button>
      ) : (
        <button 
          onClick={() => navigate('/concept-maps')}
          className={`p-2 rounded-lg transition-all ${
            isConceptMapsPage ? 'bg-primary/10 text-primary' : 'hover:bg-white/5 text-foreground'
          }`}
          title="Concept Maps"
        >
          <Network className="w-5 h-5" />
        </button>
      )}

        {/* Quiz Button */}
        {isQuizPage ? (
        <button 
          onClick={() => navigate('/chat')}
          className="p-2 hover:bg-white/5 rounded-lg transition-all"
          title="Back to Chat"
        >
          <MessageSquare className="w-5 h-5 text-foreground" />
        </button>
      ) : (
        <button 
          onClick={() => navigate('/quiz')}
          className="p-2 hover:bg-white/5 rounded-lg transition-all"
          title="Quiz"
        >
          <Brain className="w-5 h-5" />
        </button>
      )}


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
        <div className="relative z-[10000]" ref={settingsRef}>
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
            <div className="absolute right-0 mt-2 w-64 bg-[#1F2937] border border-[#374151] rounded-lg shadow-xl z-[9999] py-2 animate-fade-in settings-dropdown">
              {/* User Info Section */}
              <div className="px-4 py-3 border-b border-[#374151]">
                <div className="text-sm font-medium text-white truncate">
                  {userName || user?.email || 'User'}
                </div>
                {userName && (
                  <div className="text-xs text-gray-400 mt-1 truncate">
                    {user?.email}
                  </div>
                )}
                <div className="text-xs text-gray-400 mt-1">Free Plan</div>
              </div>

              {/* Settings Items */}
              <div className="py-1">
                <button 
                  className="settings-item"
                  onClick={() => {
                    setShowSettings(false);
                    // Navigate to account settings page
                    setShowAccountModal(true);
                  }}
                >
                  <User className="w-4 h-4" />
                  <span>Account Settings</span>
                </button>
                {!isOAuthUser && (
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
                )}
                

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
                    setShowHelpModal(true);
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
          {/* User Avatar with Dynamic Initials or Profile Picture */}
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center text-sm font-semibold text-white hover:scale-105 transition-transform cursor-pointer overflow-hidden"
            title={userName || user?.email || 'User'}
          >
            {profilePicture ? (
              <img 
                src={profilePicture} 
                alt="Profile" 
                className="w-full h-full object-cover"
                crossOrigin="anonymous"
                referrerPolicy="no-referrer"
                onError={(e) => {
                  console.error('Image load failed:', profilePicture);
                  // Fallback to initials if image fails to load
                  e.target.style.display = 'none';
                  e.target.parentElement.innerText = getUserInitials();
                }}
                onLoad={() => console.log('TopNav profile image loaded')}
              />
            ) : (
              getUserInitials()
            )}
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
    {showHelpModal && (
      <HelpSupportModal 
        onClose={() => setShowHelpModal(false)}
      />
    )}
    {showAccountModal && (
      <AccountSettingsModal 
        user={user}
        onClose={() => setShowAccountModal(false)}
        onUpdate={(data) => {
          setUserName(data.name); // Update name immediately
          // Optional: update user in parent component
          console.log('Updated user data:', data);
        }}
      />
    )}
  </>
  );
}
