# Post 10 — Projects, connectors and memory: Claude-style features in a study assistant

Publish after: Day 55 (memory shipped) · Fed by days: 18–20, 40–43, 53–55 · Format: text + short demo video + 2–3 images

## Hook
"Chat with your notes" breaks down once you have five courses. So I added what Claude has:
projects that keep each course's files and chats separate, connectors that pull material in
from Google Drive, Notion, the web and YouTube lectures, and a memory that remembers how you
learn, without letting a malicious document write itself into it.

## Concepts to explain (plain words)
- Scoped retrieval: a project is just one more filter in the WHERE clause, next to the user, but
  every cache key and every feature has to respect it, or results leak between courses
- OAuth with incremental, least-privilege scopes (Google `drive.file` + Picker): the app can see
  only the files you pick; refresh tokens stored encrypted
- Connectors as one interface (connect, list, import, sync, disconnect); imported content is as
  untrusted as an upload
- SSRF: why "import a web page by URL" has to refuse internal addresses
- Long-term memory vs. conversation memory: extracting durable facts, deduplicating them,
  retrieving the relevant ones per chat
- Memory poisoning: memories come only from the user's own words, never from documents or the web
- User control: view, edit, delete, incognito

## Outline (post + video)
1. Hook
2. Demo: create a project per course → upload → a chat cites only that course
3. Demo: import a Google Doc, a Notion page and a YouTube lecture into a project
4. Demo: say a preference once → a new chat uses it → edit it on the Memory page
5. How projects scope retrieval and caches (diagram)
6. How connectors stay least-privilege (scopes, Picker, encrypted tokens)
7. How memory is written, retrieved and protected from injection (diagram)
8. Lesson + repo link

## Visuals needed
- [ ] Screen recording of the three demos (demo documents and a demo Google/Notion account only)
- [ ] Diagram: user → project → documents/chats/memories, and where project_id filters
- [ ] Diagram: memory write path (user turns only) vs. blocked paths (documents, web, imports)
- [ ] Screenshot: Settings → Connections and the Memory page

## Material log
<!-- /run-day appends one entry per day below, newest last. -->
