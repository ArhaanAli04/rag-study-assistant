import { useState, useEffect } from 'react';
import { User, Mail, Calendar, Trash2, FileText } from 'lucide-react';
import { API_BASE_URL } from '../config/api';

export default function AccountSettingsModal({ user, onClose, onUpdate }) {
  const [formData, setFormData] = useState({
    name: '',
    email: user?.email || '',
  });
  const [userStats, setUserStats] = useState({
    member_since: null,
    plan: 'Free',
    documents_uploaded: 0,
    documents_limit: 10
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => {
    // Load user data and stats from backend
    fetchUserData();
  }, []);

  const fetchUserData = async () => {
    try {
      const token = localStorage.getItem('token');
      
      // Fetch profile data
      const profileResponse = await fetch(`${API_BASE_URL}/user/profile`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (profileResponse.ok) {
        const profileData = await profileResponse.json();
        setFormData({
          name: profileData.name || '',
          email: profileData.email || '',
        });
      }

      // Fetch user stats
      const statsResponse = await fetch(`${API_BASE_URL}/user/stats`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (statsResponse.ok) {
        const statsData = await statsResponse.json();
        setUserStats({
          member_since: statsData.member_since,
          plan: statsData.plan,
          documents_uploaded: statsData.documents_uploaded,
          documents_limit: statsData.documents_limit
        });
      }
    } catch (error) {
      console.error('Failed to fetch user data:', error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/user/profile`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: formData.name,
        }),
      });

      if (response.ok) {
        setSuccess('Profile updated successfully!');
        if (onUpdate) onUpdate(formData);
        setTimeout(() => setSuccess(''), 3000);
      } else {
        const data = await response.json();
        setError(data.detail || 'Failed to update profile');
      }
    } catch (error) {
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/user/delete`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        alert('Account deleted successfully');
        localStorage.removeItem('token');
        localStorage.removeItem('userEmail');
        window.location.href = '/login';
      } else {
        alert('Failed to delete account');
      }
    } catch (error) {
      alert('Error deleting account');
    }
  };

  // Format member since date
  const formatMemberSince = () => {
    if (!userStats.member_since) {
      return new Date().toLocaleDateString('en-US', { 
        month: 'short', 
        year: 'numeric' 
      });
    }
    
    const date = new Date(userStats.member_since);
    return date.toLocaleDateString('en-US', { 
      month: 'short', 
      year: 'numeric' 
    });
  };

  return (
    <div 
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-[10000]" 
      onClick={onClose}
    >
      <div 
        className="bg-[#1F2937] rounded-lg w-full max-w-md animate-fade-in" 
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-[#374151] flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <User className="w-6 h-6" />
            Account Settings
          </h2>
          <button 
            onClick={onClose}
            className="p-1 hover:bg-white/5 rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Success/Error Messages */}
          {success && (
            <div className="mb-4 p-3 bg-green-500/10 border border-green-500/50 rounded-lg text-green-400 text-sm">
              {success}
            </div>
          )}
          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Name Field */}
            <div>
              <label className="text-sm text-gray-400 block mb-1 flex items-center gap-2">
                <User className="w-4 h-4" />
                Full Name
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3 py-2 bg-[#374151] border border-[#4B5563] rounded-lg text-white focus:ring-2 focus:ring-primary focus:outline-none"
                placeholder="Enter your full name"
                disabled={loading}
              />
            </div>

            {/* Email Field (Read-only) */}
            <div>
              <label className="text-sm text-gray-400 block mb-1 flex items-center gap-2">
                <Mail className="w-4 h-4" />
                Email Address
              </label>
              <input
                type="email"
                value={formData.email}
                className="w-full px-3 py-2 bg-[#374151]/50 border border-[#4B5563] rounded-lg text-gray-400 cursor-not-allowed"
                disabled
              />
              <p className="text-xs text-gray-500 mt-1">
                Email cannot be changed. Contact support if needed.
              </p>
            </div>

            {/* Account Stats - NOW DYNAMIC */}
            <div className="bg-[#374151]/30 rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400 flex items-center gap-2">
                  <Calendar className="w-4 h-4" />
                  Member Since
                </span>
                <span className="text-white font-medium">
                  {formatMemberSince()}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">Plan</span>
                <span className="text-white font-medium">{userStats.plan}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400 flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Documents Uploaded
                </span>
                <span className="text-white font-medium">
                  {userStats.documents_uploaded} / {userStats.documents_limit}
                </span>
              </div>
            </div>

            {/* Update Button */}
            <button
              type="submit"
              className="w-full px-4 py-2 bg-primary hover:bg-primary/90 rounded-lg transition-colors text-white flex items-center justify-center gap-2"
              disabled={loading}
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Updating...</span>
                </>
              ) : (
                'Update Profile'
              )}
            </button>
          </form>

          {/* Danger Zone */}
          <div className="mt-6 pt-6 border-t border-[#374151]">
            <h3 className="text-sm font-semibold text-red-400 mb-3">Danger Zone</h3>
            
            {!showDeleteConfirm ? (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="w-full px-4 py-2 bg-red-500/10 hover:bg-red-500/20 border border-red-500/50 rounded-lg transition-colors text-red-400 flex items-center justify-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                Delete Account
              </button>
            ) : (
              <div className="space-y-3">
                <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-3">
                  <p className="text-sm text-red-300">
                    ⚠️ <strong>Warning:</strong> This action cannot be undone. All your data will be permanently deleted.
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowDeleteConfirm(false)}
                    className="flex-1 px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg transition-colors text-white"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDeleteAccount}
                    className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors text-white"
                  >
                    Confirm Delete
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
