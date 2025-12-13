import { useState } from "react";
import { Sparkles, AlertCircle } from "lucide-react";

export default function QuizGenerator({ onGenerate, loading, error }) {
  const [topic, setTopic] = useState("");
  const [numQuestions, setNumQuestions] = useState(5);

  const handleSubmit = (e) => {
    e.preventDefault();
    onGenerate(topic, numQuestions);
  };

  return (
    <div className="glass border border-border/50 rounded-2xl p-8">
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Topic Input */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-2">
            Topic (Optional)
          </label>
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g., Machine Learning, Cross-validation, Neural Networks"
            className="w-full px-4 py-3 rounded-lg bg-white/5 border border-border/50 text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition-all"
            disabled={loading}
          />
          <p className="text-xs text-muted-foreground mt-2">
            Leave blank to generate questions from all your study materials
          </p>
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
          disabled={loading}
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
