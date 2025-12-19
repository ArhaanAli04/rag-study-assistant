
# 🎓 RAG Study Assistant

An AI-powered study companion that transforms your documents into an interactive learning experience with intelligent Q&A, concept mapping, and quiz generation.

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.0+-blue.svg)](https://reactjs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📋 Table of Contents
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Architecture](#-architecture)
- [Setup & Installation](#-setup--installation)
- [Configuration](#-configuration)
- [Usage Guide](#-usage-guide)
- [API Documentation](#-api-documentation)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)

---

## ✨ Features

### 🤖 Intelligent Q&A System
- **Retrieval Augmented Generation (RAG)** - Combines document knowledge with web search
- **Hybrid Search** - Vector similarity + keyword matching with BM25 reranking
- **Multi-source Integration** - Seamlessly blends document content and web results
- **Confidence Scoring** - Transparent reliability metrics for every answer
- **Citation Tracking** - Every claim is backed by verifiable sources

### 📚 Document Processing
- **Multi-format Support** - PDFs, PowerPoint (PPTX), Word (DOCX), images
- **OCR Technology** - Extract text from handwritten notes and scanned documents
- **Smart Chunking** - Intelligent text segmentation with overlap for context preservation
- **Vector Embeddings** - High-quality semantic search using sentence transformers
- **Metadata Extraction** - Preserve document structure and context

### 💬 Session Management
- **Chat History** - Persistent conversation storage across sessions
- **Session Organization** - Browse and manage multiple study topics
- **Rename Sessions** - Customize session titles for better organization
- **Export Conversations**:
  - **Markdown (.md)** - Clean, readable text format
  - **PDF Document** - Professionally formatted with timestamps and sources

### 🗺️ Concept Map Generation
- **AI-Powered Visualization** - Automatically generate knowledge graphs from your materials
- **Interactive Exploration** - Click nodes to view definitions and relationships
- **Source Attribution** - Color-coded nodes by source type (web/documents)
- **Export Capabilities**:
  - **PNG Images** - High-quality lossless format
  - **JPEG Images** - Compressed format for sharing
- **Layout Algorithms** - Auto-arranged hierarchical visualization

### 📝 Quiz Generation
- **Adaptive Difficulty** - Tailored to your study materials
- **Multiple Formats** - MCQs, true/false, short answer
- **Instant Feedback** - Immediate evaluation with explanations
- **Performance Tracking** - Monitor your progress over time

### 🔐 Authentication & Security
- **OAuth 2.0 Integration** - Secure Google Sign-In
- **JWT Token Management** - Stateless authentication
- **User Isolation** - Personal document and chat spaces
- **Rate Limiting** - Protection against abuse

### ⚡ Performance Optimization
- **Redis Caching** - Fast repeated query responses
- **Async Processing** - Non-blocking document ingestion
- **FAISS Indexing** - Millisecond-level vector search
- **Streaming Responses** - Real-time answer generation

---

## 🛠️ Tech Stack

### Backend
- **Framework**: FastAPI 0.104+
- **Language**: Python 3.9+
- **Vector Database**: FAISS (Facebook AI Similarity Search)
- **Cache Layer**: Redis
- **Authentication**: OAuth 2.0 (Google), JWT
- **LLM Integration**: 
  - Google Gemini API (primary)
  - OpenAI GPT-4 (fallback)
- **Web Search**: Tavily API, SerpAPI
- **OCR**: Tesseract OCR, pytesseract
- **Document Processing**: 
  - PyPDF2, pdfplumber (PDFs)
  - python-pptx (PowerPoint)
  - python-docx (Word)
  - Pillow (images)

### Frontend
- **Framework**: React 18.0+
- **UI Library**: Tailwind CSS
- **Graph Visualization**: React Flow
- **State Management**: React Hooks
- **HTTP Client**: Axios
- **OAuth**: @react-oauth/google

### Infrastructure
- **Deployment**: Docker, Render.com, Vercel
- **Database**: PostgreSQL (planned)
- **Storage**: Cloud storage for documents (planned)
- **Monitoring**: Logging, error tracking

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│  ┌────────────┐  ┌────────────┐  ┌─────────────────────┐   │
│  │  Chat UI   │  │  Concept   │  │  Document Manager   │   │
│  │            │  │    Maps    │  │                     │   │
│  └────────────┘  └────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ REST API
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                       │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   RAG       │  │  Document    │  │  Authentication  │   │
│  │  Pipeline   │  │  Processing  │  │     (OAuth)      │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
              │              │                  │
              ▼              ▼                  ▼
┌──────────────────┐  ┌──────────────┐  ┌──────────────┐
│  FAISS Vector DB │  │    Redis     │  │  PostgreSQL  │
│  (Embeddings)    │  │   (Cache)    │  │ (Users/Logs) │
└──────────────────┘  └──────────────┘  └──────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│        External Services                 │
│  -  Google Gemini API                     │
│  -  Tavily Web Search                     │
│  -  Tesseract OCR                         │
└─────────────────────────────────────────┘
```

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.9 or higher
- Node.js 16+ and npm
- Redis server (for caching)
- Tesseract OCR (for handwritten notes)
- Git

### 1. Clone Repository
```
git clone https://github.com/yourusername/rag-study-assistant.git
cd rag-study-assistant
```

### 2. Backend Setup

#### Create Virtual Environment
```
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

#### Install Dependencies
```
pip install -r requirements.txt
```

#### Install Tesseract OCR

**Windows:**
1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install to `C:\Program Files\Tesseract-OCR\`
3. Add to PATH environment variable

**Linux:**
```
sudo apt-get install tesseract-ocr
```

**Mac:**
```
brew install tesseract
```

### 3. Frontend Setup
```
cd frontend
npm install
cd ..
```

### 4. Redis Setup

**Windows:**
- Download from: https://github.com/microsoftarchive/redis/releases
- Or use Docker: `docker run -d -p 6379:6379 redis`

**Linux:**
```
sudo apt-get install redis-server
sudo systemctl start redis
```

**Mac:**
```
brew install redis
brew services start redis
```

---

## ⚙️ Configuration

### 1. Create Environment File

Create `.env` in the root directory:

```
# LLM API Keys
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Web Search APIs
TAVILY_API_KEY=your_tavily_api_key_here
SERPAPI_API_KEY=your_serpapi_api_key_here

# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# JWT Secret
JWT_SECRET_KEY=your_super_secret_jwt_key_here_make_it_long_and_random

# Tesseract Path (Windows only)
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# Application Settings
DEBUG=True
LOG_LEVEL=INFO
```

### 2. Frontend Environment

Create `frontend/.env`:

```
REACT_APP_GOOGLE_CLIENT_ID=your_google_client_id_here
REACT_APP_API_URL=http://localhost:8000
```

### 3. Get API Keys

#### Google Gemini API
1. Visit: https://makersuite.google.com/app/apikey
2. Create API key
3. Add to `.env` as `GEMINI_API_KEY`

#### Tavily API (Web Search)
1. Visit: https://tavily.com/
2. Sign up and get API key
3. Add to `.env` as `TAVILY_API_KEY`

#### Google OAuth
1. Visit: https://console.cloud.google.com/
2. Create new project: "RAG Study Assistant"
3. Enable Google+ API
4. Configure OAuth consent screen
5. Create OAuth 2.0 credentials (Web application)
6. Add authorized origins: `http://localhost:3000`, `http://localhost:8000`
7. Add redirect URIs: `http://localhost:3000/auth/callback`, `http://localhost:8000/auth/google/callback`
8. Copy Client ID and Client Secret to `.env`

---

## 📖 Usage Guide

### Starting the Application

#### 1. Start Redis
```
# Check if Redis is running
redis-cli ping
# Should return: PONG
```

#### 2. Start Backend
```
# From root directory with venv activated
uvicorn src.main:app --reload --port 8000
```

Backend will be available at: http://localhost:8000

#### 3. Start Frontend
```
cd frontend
npm start
```

Frontend will be available at: http://localhost:3000

### Using the Application

#### 1. **Upload Documents**
- Click "Upload Documents" button
- Select PDFs, PPTX, DOCX, or images
- Wait for processing (OCR may take time for images)
- Documents are chunked and indexed automatically

#### 2. **Ask Questions**
- Type your question in the chat input
- Choose search mode:
  - **Quick**: Fast, document-only
  - **Deep**: Comprehensive with web search
- View answers with confidence scores and sources

#### 3. **Generate Concept Maps**
- Navigate to "Concept Maps" section
- Enter a topic from your study materials
- Click "Generate Map"
- Explore interactive visualization
- Export as PNG or JPEG

#### 4. **Take Quizzes**
- Go to "Quiz" section
- Select difficulty and question count
- Answer questions based on your documents
- Get instant feedback and explanations

#### 5. **Manage Sessions**
- View all chat sessions in sidebar
- Click pencil icon to rename sessions
- Export conversations as Markdown or PDF
- Delete old sessions

---

---

## 🐛 Troubleshooting

### Common Issues

#### 1. **Redis Connection Error**
```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Solution:**
```
# Check if Redis is running
redis-cli ping

# If not, start Redis
# Windows (if installed)
redis-server

# Linux
sudo systemctl start redis

# Mac
brew services start redis
```

#### 2. **Tesseract OCR Not Found**
```
TesseractNotFoundError: tesseract is not installed
```

**Solution:**
- Install Tesseract (see Installation section)
- Windows: Add to PATH or set `TESSERACT_PATH` in `.env`
- Verify: `tesseract --version`

#### 3. **API Key Invalid**
```
401 Unauthorized: Invalid API key
```

**Solution:**
- Check `.env` file has correct API keys
- Verify no extra spaces or quotes around keys
- Ensure `.env` is in root directory
- Restart backend after changing `.env`

#### 4. **Frontend Can't Connect to Backend**
```
Network Error: Failed to fetch
```

**Solution:**
- Verify backend is running: http://localhost:8000/docs
- Check `frontend/.env` has correct `REACT_APP_API_URL`
- Check for CORS issues in browser console
- Restart both frontend and backend

#### 5. **OAuth Login Failed**
```
OAuth callback error
```

**Solution:**
- Verify redirect URIs in Google Cloud Console match exactly
- Check Client ID and Secret in `.env`
- Ensure OAuth consent screen is configured
- Add your email as test user in Google Cloud Console

#### 6. **Document Upload Fails**
```
500 Internal Server Error
```

**Solution:**
- Check file format is supported (PDF, PPTX, DOCX, images)
- Verify file size is under limit (50MB)
- Check backend logs for specific error
- Ensure sufficient disk space

#### 7. **Slow Response Times**
**Solution:**
- Check Redis is running (caching helps performance)
- Reduce `top_k` parameter in queries
- Use "Quick" mode instead of "Deep"
- Consider upgrading hardware/server resources

#### 8. **Vector Search Returns No Results**
```
No relevant documents found
```

**Solution:**
- Verify documents are uploaded and processed
- Check FAISS index exists in `data/faiss/`
- Try rephrasing the question
- Upload more relevant documents

---



## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **LangChain** - RAG orchestration framework
- **FastAPI** - Modern Python web framework
- **React Flow** - Interactive graph visualization
- **FAISS** - Efficient similarity search
- **Google Gemini** - LLM API
- **Tavily** - Academic web search

---

## 📞 Contact

**Project Maintainer**: Your Name
- Email: your.email@example.com
- GitHub: [@yourusername](https://github.com/yourusername)
- LinkedIn: [Your LinkedIn](https://linkedin.com/in/yourprofile)

**Project Link**: [https://github.com/yourusername/rag-study-assistant](https://github.com/yourusername/rag-study-assistant)

---

## 🗺️ Roadmap

- [x] Core RAG pipeline
- [x] Document ingestion (PDF, PPTX, DOCX, images)
- [x] Hybrid search (vector + keyword)
- [x] Web search integration
- [x] Session management
- [x] Concept map generation
- [x] Quiz generation
- [x] Export functionality (Markdown, PDF, Images)
- [x] OAuth authentication
- [ ] PostgreSQL integration
- [ ] Docker deployment
- [ ] Cloud storage for documents
- [ ] Advanced analytics dashboard
- [ ] Mobile application
- [ ] Collaborative study sessions
- [ ] Audio/video content support

---

<p align="center">
  Made with ❤️ for students everywhere
</p>
```

***

