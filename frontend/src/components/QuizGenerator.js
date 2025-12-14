import { useState } from "react";
import { Sparkles, AlertCircle, Zap, BookOpen, Brain } from "lucide-react";

export default function QuizGenerator({ onGenerate, loading, error }) {
  const [topic, setTopic] = useState("");
  const [numQuestions, setNumQuestions] = useState(5);
  const [difficulty, setDifficulty] = useState("medium");
  

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!topic.trim()) {
      return;
    }
    onGenerate(topic, numQuestions, difficulty);
  };

  const difficultyOptions = [
    { value: "easy", label: "Easy", icon: BookOpen, color: "text-green-500" },
    { value: "medium", label: "Medium", icon: Brain, color: "text-yellow-500" },
    { value: "hard", label: "Hard", icon: Zap, color: "text-red-500" },
  ];

  return (
    <div className="glass border border-border/50 rounded-2xl p-8">
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Topic Input */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            Topic <span className="text-destructive">*</span>
          </label>
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g., Machine Learning, Python Programming, Data Structures"
            className="w-full px-4 py-3 rounded-lg bg-white/5 border border-border/50 text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all"
            disabled={loading}
            required
          />
          <p className="text-xs text-muted-foreground mt-2">
            Enter any topic you want to be quizzed on
          </p>
        </div>

        {/* Difficulty Selection */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-3">
            Difficulty Level
          </label>
          <div className="grid grid-cols-3 gap-3">
            {difficultyOptions.map((option) => {
              const Icon = option.icon;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setDifficulty(option.value)}
                  disabled={loading}
                  className={`
                    p-4 rounded-lg border-2 transition-all
                    ${difficulty === option.value
                      ? 'border-primary bg-primary/10'
                      : 'border-border/30 hover:border-border/50 bg-white/5'
                    }
                  `}
                >
                  <Icon className={`w-6 h-6 mx-auto mb-2 ${option.color}`} />
                  <span className="text-sm font-medium text-foreground block">
                    {option.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Number of Questions */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            Number of Questions
          </label>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min="3"
              max="10"
              value={numQuestions}
              onChange={(e) => setNumQuestions(parseInt(e.target.value))}
              className="flex-1"
              disabled={loading}
            />
            <div className="w-12 h-12 flex items-center justify-center rounded-lg bg-primary/10 border border-primary/20">
              <span className="text-lg font-bold text-primary">{numQuestions}</span>
            </div>
          </div>
          <div className="flex justify-between text-xs text-muted-foreground mt-2">
            <span>3 questions</span>
            <span>10 questions</span>
          </div>
        </div>


        {/* Error Message */}
        {error && (
          <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-destructive font-medium">Error</p>
              <p className="text-sm text-destructive/80">{error}</p>
            </div>
          </div>
        )}

        {/* Generate Button */}
        <button
          type="submit"
          disabled={loading || !topic.trim()}
          className="w-full flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg font-medium hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-primary/20"
        >
          {loading ? (
            <>
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
              <span>Generating Quiz...</span>
            </>
          ) : (
            <>
              <Sparkles className="w-5 h-5" />
              <span>Generate Quiz</span>
            </>
          )}
        </button>
      </form>
    </div>
  );
}
