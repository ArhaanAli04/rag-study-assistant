import { useState } from 'react';
import { HelpCircle } from 'lucide-react';

export default function HelpSupportModal({ onClose }) {
  const [activeTab, setActiveTab] = useState('guide');

  return (
    <div 
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-[10000]" 
      onClick={onClose}
    >
      <div 
        className="bg-[#1F2937] rounded-lg w-full max-w-3xl max-h-[85vh] overflow-hidden animate-fade-in" 
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-[#374151] flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <HelpCircle className="w-6 h-6" />
            Help & Support
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

        {/* Tabs */}
        <div className="flex border-b border-[#374151] px-6">
          <TabButton 
            active={activeTab === 'guide'} 
            onClick={() => setActiveTab('guide')}
          >
            Quick Start
          </TabButton>
          <TabButton 
            active={activeTab === 'features'} 
            onClick={() => setActiveTab('features')}
          >
            Features
          </TabButton>
          <TabButton 
            active={activeTab === 'shortcuts'} 
            onClick={() => setActiveTab('shortcuts')}
          >
            Shortcuts
          </TabButton>
          <TabButton 
            active={activeTab === 'faq'} 
            onClick={() => setActiveTab('faq')}
          >
            FAQ
          </TabButton>
          <TabButton 
            active={activeTab === 'contact'} 
            onClick={() => setActiveTab('contact')}
          >
            Contact
          </TabButton>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(85vh-140px)]">
          {activeTab === 'guide' && <QuickStartTab />}
          {activeTab === 'features' && <FeaturesTab />}
          {activeTab === 'shortcuts' && <ShortcutsTab />}
          {activeTab === 'faq' && <FAQTab />}
          {activeTab === 'contact' && <ContactTab />}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-[#374151] flex justify-between items-center">
          <div className="text-sm text-gray-400">
            Version 1.0.0
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-primary hover:bg-primary/90 rounded-lg transition-colors text-white"
          >
            Got it!
          </button>
        </div>
      </div>
    </div>
  );
}

// ===== Tab Button Component =====
function TabButton({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-3 text-sm font-medium transition-colors ${
        active 
          ? 'text-primary border-b-2 border-primary' 
          : 'text-gray-400 hover:text-white'
      }`}
    >
      {children}
    </button>
  );
}

// ===== Quick Start Tab =====
function QuickStartTab() {
  return (
    <div className="space-y-6 text-gray-300">
      <div>
        <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
          🚀 Getting Started
        </h3>
        <ol className="list-decimal ml-5 space-y-3">
          <li>
            <strong className="text-white">Upload Your Documents</strong>
            <p className="text-sm mt-1">Click the Documents icon (📄) in the navbar → Upload PDF, PPTX or DOCX, files</p>
          </li>
          <li>
            <strong className="text-white">Start a Chat Session</strong>
            <p className="text-sm mt-1">Click "New Chat" in the sidebar → Select a document to study</p>
          </li>
          <li>
            <strong className="text-white">Ask Questions</strong>
            <p className="text-sm mt-1">Type your question in the chat box → Get AI-powered answers from your documents</p>
          </li>
          <li>
            <strong className="text-white">Generate Quizzes</strong>
            <p className="text-sm mt-1">Click the Brain icon (🧠) → Select documents → Generate practice questions</p>
          </li>
        </ol>
      </div>

      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
        <p className="text-sm text-blue-300">
          💡 <strong>Pro Tip:</strong> You can enable web search in the sidebar to get information beyond your documents!
        </p>
      </div>
    </div>
  );
}

// ===== Features Tab =====
function FeaturesTab() {
  const features = [
    {
      icon: '🤖',
      title: 'RAG-Powered Chat',
      description: 'Ask questions and get accurate answers directly from your uploaded study materials using advanced AI retrieval.'
    },
    {
      icon: '🌐',
      title: 'Web Search',
      description: 'System uses web search to fetch real-time information from the internet when your documents are not uploaded or do not have the answer.'
    },
    {
      icon: '📝',
      title: 'Quiz Generation',
      description: 'Automatically generate practice questions from your study materials to test your knowledge.'
    },
    {
      icon: '💾',
      title: 'Session Management',
      description: 'Organize your study sessions by topic. All chat history is saved and searchable.'
    },
    {
      icon: '📊',
      title: 'Source Citations',
      description: 'Every answer includes source references so you can verify information and learn more.'
    }
  ];

  return (
    <div className="space-y-6 text-gray-300">
      <div>
        <h3 className="text-lg font-semibold text-white mb-3">✨ Key Features</h3>
        <div className="space-y-4">
          {features.map((feature, index) => (
            <div key={index} className="bg-[#374151]/30 rounded-lg p-4">
              <h4 className="font-semibold text-white mb-2">
                {feature.icon} {feature.title}
              </h4>
              <p className="text-sm">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ===== Shortcuts Tab =====
function ShortcutsTab() {
  const shortcuts = [
    { action: 'Send message', key: 'Enter' },
    { action: 'New line in message', key: 'Shift + Enter' },
    { action: 'Focus chat input', key: 'Ctrl + /' },
    { action: 'Toggle sidebar', key: 'Click ☰' },
    { action: 'Copy message', key: 'Click 📋' }
  ];

  return (
    <div className="space-y-6 text-gray-300">
      <div>
        <h3 className="text-lg font-semibold text-white mb-3">⌨️ Keyboard Shortcuts</h3>
        <div className="space-y-3">
          {shortcuts.map((shortcut, index) => (
            <div 
              key={index} 
              className="flex justify-between items-center py-2 border-b border-[#374151]"
            >
              <span>{shortcut.action}</span>
              <kbd className="px-3 py-1 bg-[#374151] rounded text-sm font-mono">
                {shortcut.key}
              </kbd>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ===== FAQ Tab =====
function FAQTab() {
  const faqs = [
    {
      question: 'What file types can I upload?',
      answer: 'You can upload PDF, PPTX and DOCX files. Maximum file size is 50MB per document.'
    },
    {
      question: 'How does the AI find answers?',
      answer: 'We use Retrieval Augmented Generation (RAG) technology along with Web search which searches top academic websites. Your documents are indexed, and relevant sections are retrieved to answer your questions accurately.'
    },
    {
      question: 'Is my data private?',
      answer: 'Yes! Your documents and chat history are private and only accessible to you. We don\'t share your data with third parties.'
    },
    {
      question: 'Can I delete uploaded documents?',
      answer: 'Yes, go to the Documents page and click the delete icon next to any document you want to remove.'
    },
    {
      question: 'How many documents can I upload?',
      answer: 'Free plan: Up to 10 documents. Upgrade for unlimited uploads.'
    },
    {
      question: 'What if the AI gives wrong answers?',
      answer: 'Use the thumbs down (👎) button to provide feedback. This helps us improve the system.'
    }
  ];

  return (
    <div className="space-y-6 text-gray-300">
      <div>
        <h3 className="text-lg font-semibold text-white mb-3">❓ Frequently Asked Questions</h3>
        <div className="space-y-4">
          {faqs.map((faq, index) => (
            <div key={index}>
              <h4 className="font-semibold text-white mb-2">{faq.question}</h4>
              <p className="text-sm">{faq.answer}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ===== Contact Tab =====
function ContactTab() {
  return (
    <div className="space-y-6 text-gray-300">
      <div>
        <h3 className="text-lg font-semibold text-white mb-3">📧 Contact & Support</h3>
        
        <div className="space-y-4">
          <div className="bg-[#374151]/30 rounded-lg p-4">
            <h4 className="font-semibold text-white mb-2">Email Support</h4>
            <p className="text-sm mb-2">For technical issues or questions:</p>
            <a 
              href="mailto:support@ragstudy.com" 
              className="text-primary hover:underline"
            >
              support@ragstudy.com
            </a>
          </div>

          <div className="bg-[#374151]/30 rounded-lg p-4">
            <h4 className="font-semibold text-white mb-2">Report a Bug</h4>
            <p className="text-sm mb-3">Found a bug? Help us improve by reporting it.</p>
            <a
              href="https://github.com/yourusername/rag-study-assistant/issues"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary/90 rounded-lg transition-colors text-white text-sm"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              Report on GitHub
            </a>
          </div>

          <div className="bg-[#374151]/30 rounded-lg p-4">
            <h4 className="font-semibold text-white mb-2">Feature Requests</h4>
            <p className="text-sm mb-3">Have an idea to make the app better?</p>
            <button
              onClick={() => window.open('https://forms.gle/your-form-link', '_blank')}
              className="inline-flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors text-white text-sm"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Submit Feature Request
            </button>
          </div>

          <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
            <p className="text-sm text-blue-300">
              💬 <strong>Average Response Time:</strong> We typically respond within 24-48 hours on weekdays.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
