# Post 6 — "From a fixed pipeline to agentic RAG with LangGraph"

Publish after: Day 34 (v0.5.0) · Fed by days: 30, 31, 32, 34 · Format: PDF carousel

## Hook
My RAG pipeline ran a web search on every question, even when the answer was already in the
student's notes. Turning it into a graph that grades its own retrieval cut web calls by X%
without hurting answer quality.

## Concepts to explain (plain words)
- State graphs: nodes, shared state, edges
- Conditional edges and Corrective RAG (grade → retry or web search)
- Self-verification of answers against their sources
- Tool calling and the ReAct loop
- Iteration caps and latency budgets
- Retrieval-based conversation memory

## Slide outline
1. Hook
2. The old linear pipeline
3. The graph (diagram)
4. Corrective RAG: what "grading retrieval" means
5. Verification node: catching unsupported claims
6. Tools: when the model decides what to call
7. Results: web calls, latency, faithfulness before/after
8. Lesson + repo link

## Visuals needed
- [ ] Diagram: LangGraph graph with conditional edges
- [ ] Screenshot: Langfuse trace of a retry path
- [ ] Chart: web calls per query and faithfulness, before/after
- [ ] Example: a long session recalling an early turn

## Material log
<!-- /run-day appends one entry per day below, newest last. -->
