import { useState } from "react";
import { CheckCircle, RefreshCw, Award, CheckCircle2, XCircle, Eye } from "lucide-react";

export default function QuizDisplay({ quiz, onNewQuiz }) {
  const [userAnswers, setUserAnswers] = useState({});
  const [showResults, setShowResults] = useState(false);

  // Parse quiz text into structured questions
  const parseQuiz = (text) => {
    // Remove markdown formatting artifacts
    text = text.replace(/\*\*/g, '').replace(/##/g, '');
    
    // Split by "Question X:" pattern
    const questionPattern = /Question\s+(\d+):/gi;
    const matches = [...text.matchAll(questionPattern)];
    
    if (matches.length === 0) {
      return [];
    }
    
    const questions = [];
    
    for (let i = 0; i < matches.length; i++) {
      const match = matches[i];
      const questionNumber = parseInt(match[1]);
      const startIdx = match.index + match[0].length;
      const endIdx = i < matches.length - 1 ? matches[i + 1].index : text.length;
      const block = text.substring(startIdx, endIdx).trim();
      
      const lines = block.split('\n').map(l => l.trim()).filter(l => l);
      
      let questionText = '';
      let restLines = [];
      
      if (lines.length > 0) {
        questionText = lines[0];
        restLines = lines.slice(1);
      }
      
      const options = [];
      let correctAnswer = null;
      let explanation = '';
      let explanationStarted = false;
      
      restLines.forEach((line) => {
        const optionMatch = line.match(/^([A-D])\)\s*(.+)/i);
        if (optionMatch && !explanationStarted) {
          options.push({
            letter: optionMatch[1].toUpperCase(),
            text: optionMatch[2].trim()
          });
          return;
        }
        
        const answerMatch = line.match(/Correct\s+Answer:\s*([A-D])/i);
        if (answerMatch) {
          correctAnswer = answerMatch[1].toUpperCase();
          return;
        }
        
        const explanationMatch = line.match(/Explanation:\s*(.+)/i);
        if (explanationMatch) {
          explanation = explanationMatch[1].trim();
          explanationStarted = true;
          return;
        }
        
        if (explanationStarted && !line.match(/^(Question|Correct Answer:|[A-D]\))/i)) {
          explanation += ' ' + line;
        }
      });
      
      questions.push({
        number: questionNumber,
        question: questionText,
        options,
        correctAnswer,
        explanation: explanation.trim()
      });
    }
    
    return questions;
  };

  const questions = parseQuiz(quiz.questions);

  const handleSelectAnswer = (questionNumber, selectedLetter) => {
    if (showResults) return; // Don't allow changes after showing results
    
    setUserAnswers({
      ...userAnswers,
      [questionNumber]: selectedLetter
    });
  };

  const calculateScore = () => {
    let correct = 0;
    questions.forEach(q => {
      if (userAnswers[q.number] === q.correctAnswer) {
        correct++;
      }
    });
    return { correct, total: questions.length };
  };

  const score = showResults ? calculateScore() : null;

  return (
    <div className="space-y-6">
      {/* Quiz Header */}
      <div className="glass border border-border/50 rounded-2xl p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Award className="w-6 h-6 text-primary" />
            <div>
              <h3 className="text-lg font-semibold text-foreground">{quiz.topic}</h3>
              <p className="text-sm text-muted-foreground">
                {quiz.num_questions} questions • {quiz.difficulty} difficulty
              </p>
            </div>
          </div>
          <button
            onClick={onNewQuiz}
            className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-white/5 transition-all text-foreground"
          >
            <RefreshCw className="w-4 h-4" />
            <span className="text-sm">New Quiz</span>
          </button>
        </div>
      </div>

      {/* Score Display (After Results) */}
      {showResults && score && (
        <div className="glass border border-primary/50 rounded-2xl p-6 bg-primary/5">
          <div className="text-center">
            <h3 className="text-2xl font-bold text-foreground mb-2">
              Your Score: {score.correct} / {score.total}
            </h3>
            <p className="text-lg text-muted-foreground">
              {Math.round((score.correct / score.total) * 100)}% Correct
            </p>
          </div>
        </div>
      )}

      {/* Quiz Questions */}
      {questions.length === 0 ? (
        <div className="glass border border-border/50 rounded-2xl p-8 text-center">
          <p className="text-muted-foreground">Unable to parse quiz questions. Please try generating again.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {questions.map((q) => {
            const userAnswer = userAnswers[q.number];
            const isCorrect = showResults && userAnswer === q.correctAnswer;
            const isWrong = showResults && userAnswer && userAnswer !== q.correctAnswer;

            return (
              <div key={q.number} className="glass border border-border/50 rounded-2xl p-6">
                {/* Question */}
                <div className="mb-4">
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <span className="text-sm font-bold text-primary">{q.number}</span>
                    </div>
                    <p className="text-foreground font-medium leading-relaxed flex-1">
                      {q.question}
                    </p>
                  </div>
                </div>

                {/* Options */}
                {q.options.length > 0 ? (
                  <div className="space-y-2 ml-11">
                    {q.options.map((option) => {
                      const isSelected = userAnswer === option.letter;
                      const isCorrectOption = showResults && option.letter === q.correctAnswer;
                      const isWrongSelection = showResults && isSelected && !isCorrectOption;

                      return (
                        <button
                          key={option.letter}
                          onClick={() => handleSelectAnswer(q.number, option.letter)}
                          disabled={showResults}
                          className={`
                            w-full p-3 rounded-lg border transition-all text-left
                            ${showResults
                              ? isCorrectOption
                                ? 'border-green-500/50 bg-green-500/10'
                                : isWrongSelection
                                ? 'border-red-500/50 bg-red-500/10'
                                : 'border-border/30 bg-white/5'
                              : isSelected
                              ? 'border-primary bg-primary/10'
                              : 'border-border/30 bg-white/5 hover:border-primary/50'
                            }
                            ${!showResults && 'cursor-pointer'}
                          `}
                        >
                          <div className="flex items-start gap-3">
                            <span className={`
                              font-semibold flex-shrink-0
                              ${showResults && isCorrectOption
                                ? 'text-green-500'
                                : showResults && isWrongSelection
                                ? 'text-red-500'
                                : isSelected
                                ? 'text-primary'
                                : 'text-foreground'
                              }
                            `}>
                              {option.letter})
                            </span>
                            <span className="text-foreground flex-1">{option.text}</span>
                            {showResults && isCorrectOption && (
                              <CheckCircle2 className="w-5 h-5 text-green-500 flex-shrink-0" />
                            )}
                            {showResults && isWrongSelection && (
                              <XCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-muted-foreground text-sm ml-11">No options available</p>
                )}

                {/* Explanation (Only shown after results) */}
                {showResults && q.explanation && (
                  <div className="mt-4 ml-11 p-4 rounded-lg bg-primary/5 border border-primary/20">
                    <div className="flex items-start gap-2">
                      <CheckCircle className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <p className="text-sm font-semibold text-primary mb-1">
                          Explanation
                        </p>
                        <p className="text-sm text-foreground/80 leading-relaxed">
                          {q.explanation}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Show Results Button */}
      {!showResults && questions.length > 0 && (
        <div className="sticky bottom-6 flex justify-center">
          <button
            onClick={() => setShowResults(true)}
            className="flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-[#7C3AED] to-[#3B82F6] text-white rounded-lg font-medium hover:opacity-90 transition-all shadow-lg shadow-primary/30"
          >
            <Eye className="w-5 h-5" />
            <span>Show Results</span>
          </button>
        </div>
      )}
    </div>
  );
}
