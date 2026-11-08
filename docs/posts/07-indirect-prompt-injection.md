# Post 7 — "The realistic attack on RAG isn't the user — it's the PDF"

Publish after: Day 37 (defences deployed) · Fed by days: 35 (moderation), 36 · Format: text + 2–3 images (or a short video)

## Hook
I hid one line of white text in a PDF, uploaded it, and my study assistant started giving
wrong answers. Here's how indirect prompt injection works and the layers I added against it.

## Concepts to explain (plain words)
- Direct vs. indirect prompt injection
- Why RAG makes indirect injection the main threat
- Spotlighting: delimiting retrieved text as data
- Canary tokens
- Markdown image exfiltration and why it matters in a chat UI
- Hidden / zero-width text scanning at upload
- Model-based moderation vs. keyword lists
- Red-teaming with an attack success rate metric

## Outline
1. Hook (the poisoned PDF demo)
2. Direct vs. indirect injection
3. How the attack reaches the model in a RAG pipeline
4. The exfiltration trick (described as a class, no working payload)
5. Defence layers, one line each
6. Attack success rate before/after on the red-team set
7. What no defence fully solves
8. Lesson + repo link

## Visuals needed
- [ ] Diagram: where untrusted text enters the prompt, and each defence layer
- [ ] Chart: attack success rate before/after per layer
- [ ] Screenshot/video: the demo with a test document (never a real user's file)

## Material log
<!-- /run-day appends one entry per day below, newest last. -->
