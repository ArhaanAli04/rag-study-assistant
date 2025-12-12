import { Menu, Moon, Settings, LogOut } from 'lucide-react';

export default function TopNav({ user, onLogout, onToggleSidebar }) {
  
  const handleSettings = () => {
    // TODO: Open settings modal
    console.log('Settings clicked');
  };

  const handleDarkMode = () => {
    // TODO: Toggle dark mode
    console.log('Dark mode toggle clicked');
  };

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
