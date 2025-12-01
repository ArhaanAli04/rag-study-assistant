# AI-Powered Study Assistant with Retrieval Augmented Generation (RAG)

## Project Overview
This project builds a web-based AI assistant that helps students ask questions on their own study materials (PDFs, slides, notes). It uses advanced Retrieval Augmented Generation combining semantic vector search, keyword search, and web augmentation to deliver accurate, cited answers.

## Features
- Multi-format document ingestion: PDFs, PowerPoint, DOCX, handwritten notes with OCR
- Hybrid retrieval: Vector DB, keyword search and reranking
- Dynamic web search fallback for low confidence queries
- Structured prompt engineering with citation enforcement
- Session management with full chat history
- Caching layers to optimize performance and cost
- User authentication, rate limiting, and monitoring

## Tech Stack
- Backend: FastAPI, Python
- Frontend: Streamlit / React (to be developed)
- Vector DB: FAISS or Qdrant
- Cache: Redis (planned)
- LLMs: OpenAI GPT-4 / Google Gemini (planned)
- Web API: SerpAPI, Tavily (for academic web augmentation)
- Other: LangChain for RAG orchestration, python-dotenv for config

## Setup
1. Create `.env` file with API keys.
2. Install dependencies from `requirements.txt`.
3. Run backend with `uvicorn src.main:app --reload`.

## Project Structure
- `src/` - source code
- `data/` - uploaded documents
- `tests/` - unit and integration tests
- `configs/` - config and prompt templates
