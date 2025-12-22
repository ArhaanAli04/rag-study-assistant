import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import TopNav from "../components/TopNav";
import QuizGenerator from "../components/QuizGenerator";
import QuizDisplay from "../components/QuizDisplay";
import { Brain, ArrowLeft } from "lucide-react";
import { API_BASE_URL } from '../config/api';

export default function QuizPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  
  const [quiz, setQuiz] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleGenerateQuiz = async (topic, numQuestions, difficulty) => {
    try {
      setLoading(true);
      setError(null);
      
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_BASE_URL}/quiz`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          topic: topic,
          num_questions: numQuestions,
          difficulty: difficulty,
          include_answers: true,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to generate quiz");
      }

      const data = await response.json();
      setQuiz(data);
    } catch (err) {
      setError(err.message);
      console.error("Error generating quiz:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleNewQuiz = () => {
    setQuiz(null);
    setError(null);
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="flex flex-col h-screen" style={{ background: "#0F0F0F" }}>
      {/* Top Navigation */}
      <TopNav 
        user={user} 
        onLogout={handleLogout}
        onToggleSidebar={() => navigate('/chat')}
      />

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto px-4 lg:px-8 py-8">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            
            
            <div className="flex items-center gap-3 mb-2">
              <Brain className="w-8 h-8 text-primary" />
              <h1 className="text-3xl font-bold bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] bg-clip-text text-transparent">
                Quiz Generator
              </h1>
            </div>
            <p className="text-muted-foreground">
              Test your knowledge with AI-generated quizzes from your study materials
            </p>
          </div>

          {/* Quiz Generator or Display */}
          {!quiz ? (
            <QuizGenerator
              onGenerate={handleGenerateQuiz}
              loading={loading}
              error={error}
            />
          ) : (
            <QuizDisplay
              quiz={quiz}
              onNewQuiz={handleNewQuiz}
            />
          )}
        </div>
      </div>
    </div>
  );
}
