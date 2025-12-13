import { useState } from "react";
import { CheckCircle, FileText, RefreshCw, ExternalLink } from "lucide-react";
import ReactMarkdown from "react-markdown";

export default function QuizDisplay({ quiz, onNewQuiz }) {
  const [showSources, setShowSources] = useState(false);

  // Better source display logic
  const formatSource = (source, idx) => {
    if (typeof source === 'string') {
      return { label: source, page: null };
    }
    
    // Extract filename from path or use source field
    let filename = 'Unknown Source';
    if (source.source) {
      filename = source.source.split('/').pop().split('\\').pop();
    } else if (source.filename) {
      filename = source.filename;
    } else if (source.file_path) {
      filename = source.file_path.split('/').pop().split('\\').pop();
    }
    
    return {
      label: filename,
      page: source.page || source.page_number || null,
      chunk: source.chunk_id || null,
    };
  };

  return (
    <div className="space-y-6">
      {/* Quiz Questions */}
      <div className="glass border border-border/50 rounded-2xl p-8">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <CheckCircle className="w-6 h-6 text-primary" />
            <h2 className="text-2xl font-bold text-foreground">Your Quiz</h2>
          </div>
          <button
            onClick={onNewQuiz}
            className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-white/5 transition-all text-foreground"
          >
            <RefreshCw className="w-4 h-4" />
            <span className="text-sm">New Quiz</span>
          </button>
        </div>

        {/* Quiz Content */}
        <div className="prose prose-invert max-w-none">
          <ReactMarkdown
            components={{
              p: ({ children }) => (
                <p className="text-foreground mb-4 leading-relaxed">{children}</p>
              ),
              ol: ({ children }) => (
                <ol className="list-decimal list-inside space-y-4 text-foreground">{children}</ol>
              ),
              ul: ({ children }) => (
                <ul className="list-disc list-inside space-y-2 text-foreground">{children}</ul>
              ),
              li: ({ children }) => (
                <li className="text-foreground mb-3">{children}</li>
              ),
              strong: ({ children }) => (
                <strong className="text-foreground font-semibold">{children}</strong>
              ),
            }}
          >
            {quiz.questions}
          </ReactMarkdown>
        </div>
      </div>

      {/* Sources Section */}
      {quiz.sources && quiz.sources.length > 0 && (
        <div className="glass border border-border/50 rounded-2xl p-6">
          <button
            onClick={() => setShowSources(!showSources)}
            className="flex items-center justify-between w-full"
          >
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-primary" />
              <h3 className="text-lg font-semibold text-foreground">
                Sources ({quiz.sources.length})
              </h3>
            </div>
            <span className="text-sm text-muted-foreground">
              {showSources ? "Hide" : "Show"}
            </span>
          </button>

          {showSources && (
            <div className="mt-4 space-y-2">
              {quiz.sources.map((source, idx) => {
                const formattedSource = formatSource(source, idx);
                return (
                  <div
                    key={idx}
                    className="p-4 rounded-lg bg-white/5 border border-border/30 hover:border-primary/50 transition-all"
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                        <FileText className="w-4 h-4 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground font-medium">
                          {formattedSource.label}
                        </p>
                        <div className="flex items-center gap-3 mt-1">
                          {formattedSource.page && (
                            <span className="text-xs text-muted-foreground">
                              Page {formattedSource.page}
                            </span>
                          )}
                          {formattedSource.chunk && (
                            <span className="text-xs text-muted-foreground">
                              Chunk #{formattedSource.chunk}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* No Sources Warning */}
      {(!quiz.sources || quiz.sources.length === 0) && (
        <div className="glass border border-yellow-500/50 rounded-2xl p-6 bg-yellow-500/5">
          <div className="flex items-start gap-3">
            <ExternalLink className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-semibold text-yellow-500 mb-1">
                No Sources Found
              </h3>
              <p className="text-sm text-muted-foreground">
                This quiz was generated without reference to your uploaded documents. 
                Try uploading study materials first or specify a more specific topic.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
