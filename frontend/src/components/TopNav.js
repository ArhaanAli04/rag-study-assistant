import { Menu, Moon, Settings, LogOut, FileText, MessageSquare, Brain } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';

export default function TopNav({ user, onLogout, onToggleSidebar }) {
  const navigate = useNavigate();
  const location = useLocation();
  
  const handleSettings = () => {
    console.log('Settings clicked');
  };

  const handleDarkMode = () => {
    console.log('Dark mode toggle clicked');
  };

  // Check if we're on documents page
  const isDocumentsPage = location.pathname === '/documents';
  const isQuizPage = location.pathname === '/quiz';

  return (
    <header
      className="glass border-b border-border/50 px-4 lg:px-6 h-16 flex items-center justify-between"
      style={{ background: "rgba(15, 15, 15, 0.8)" }}
    >
      <div className="flex items-center gap-3">
        <button 
          onClick={onToggleSidebar}
          className="p-2 hover:bg-white/5 rounded-lg transition-all"
        >
          <Menu className="w-5 h-5 text-foreground" />
        </button>
        <h1 className="text-xl font-semibold bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] bg-clip-text text-transparent">
          RAG Study Assistant
        </h1>
      </div>

      <div className="flex items-center gap-2">
        {/* ✅ ADD QUIZ BUTTON */}
        <button 
          onClick={() => navigate('/quiz')}
          className={`p-2 rounded-lg transition-all ${
            isQuizPage ? 'bg-primary/10 text-primary' : 'hover:bg-white/5 text-foreground'
          }`}
          title="Quiz"
        >
          <Brain className="w-5 h-5" />
        </button>
        {/* ✅ Show Chat or Documents button based on current page */}
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
        
        <button 
          onClick={handleDarkMode}
          className="p-2 hover:bg-white/5 rounded-lg transition-all"
        >
          <Moon className="w-5 h-5 text-foreground" />
        </button>
        <button 
          onClick={handleSettings}
          className="p-2 hover:bg-white/5 rounded-lg transition-all"
        >
          <Settings className="w-5 h-5 text-foreground" />
        </button>
        <div className="flex items-center gap-2 ml-2">
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-sm font-semibold text-white">
            {user?.email?.substring(0, 2).toUpperCase() || 'JD'}
          </div>
          <button 
            onClick={onLogout}
            className="p-2 hover:bg-white/5 rounded-lg transition-all"
          >
            <LogOut className="w-5 h-5 text-foreground" />
          </button>
        </div>
      </div>
    </header>
  );
}
