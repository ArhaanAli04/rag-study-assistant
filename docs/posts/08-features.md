# Post 8 — Features: a study assistant that knows what you don't know yet

Publish after: Day 49 (v0.7.0, features restyled) · Fed by days: 36–45, 46–49 · Format: short demo video + 3–4 images

## Hook
Most "chat with your notes" apps stop at chat. Mine tracks what you've mastered — every quiz
answer, flashcard and explanation updates it — and uses that to drive adaptive quizzes, a
concept map coloured by what you don't know yet, and an "explain it back" tutor.

## Features covered
- Mastery model + Progress page (#1)
- Adaptive quiz on the Practice page, with flashcards (#2)
- Living concept map (#3)
- Feynman mode — explain it back (#4)
- PDF citation viewer (#8)
- Study guide per document (#10)

## Concepts to explain (plain words)
- Concept extraction into a shared catalogue (structured output)
- Knowledge tracing — estimating mastery from answers over time (Elo-style update + decay)
- Grounded question generation with misconception-based distractors
- LLM rubric grading of short answers and of the student's own explanation
- Spaced repetition (SM-2)
- Citation grounding all the way to a highlighted passage

## Slide / video outline
1. Hook
2. Demo: upload → concepts extracted → chat with citations that open the highlighted page
3. Demo: adaptive Practice quiz → mastery updates on Progress
4. Demo: concept map turning green as you learn; node → "quiz me"
5. Demo: explain it back → covered / missing / wrong feedback
6. The AI behind each feature, one line each; how they share one mastery model
7. Lesson + repo link

## Visuals needed
- [ ] Screen recording of the main flow (demo documents only)
- [ ] Screenshot of each feature on the new UI
- [ ] Diagram: concept catalogue + mastery model feeding every feature

## Material log
<!-- /run-day appends one entry per day below, newest last. -->
