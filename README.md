
# 🎓 RAG Study Assistant

An AI-powered study companion that transforms your documents into an interactive learning experience with intelligent Q&A, concept mapping, and quiz generation.

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.0+-blue.svg)](https://reactjs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **A comprehensive RAG-powered study assistant that combines document analysis, AI-driven Q&A, concept visualization, and quiz generation to enhance your learning experience.**

---

## 📋 Table of Contents
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Architecture](#-architecture)
- [Setup & Installation](#-setup--installation)
- [Usage Guide](#-usage-guide)
- [Contact](#-contact)

---

## ✨ Features

### 🤖 Intelligent Q&A System
- **Retrieval Augmented Generation (RAG)** - Combines document knowledge with web search for accurate answers
- **Hybrid Search** - Vector similarity + keyword matching with BM25 reranking for optimal retrieval
- **Multi-source Integration** - Seamlessly blends document content and real-time web results
- **Confidence Scoring** - Transparent reliability metrics (0-100%) for every answer
- **Citation Tracking** - Every claim backed by verifiable sources with document references
- **Streaming Responses** - Real-time answer generation for better user experience

### 📚 Document Processing
- **Multi-format Support** - PDFs, PowerPoint (PPTX), Word (DOCX), and images
- **OCR Technology** - Extract text from handwritten notes and scanned documents using Tesseract
- **Smart Chunking** - Intelligent text segmentation with overlap for context preservation
- **Vector Embeddings** - High-quality semantic search using sentence transformers
- **Metadata Extraction** - Preserve document structure, page numbers, and context
- **Async Processing** - Non-blocking document ingestion for large files

### 💬 Session Management
- **Persistent Chat History** - All conversations saved and organized by topic
- **Multi-session Support** - Work on multiple subjects simultaneously
- **Session Renaming** - Customize session titles for better organization
- **Export Conversations**:
  - **Markdown (.md)** - Clean, readable text format with timestamps
  - **PDF Document** - Professionally formatted with color-coded roles and sources
- **Session Deletion** - Clean up old conversations easily

### 🗺️ Concept Map Generation
- **AI-Powered Visualization** - Automatically generate knowledge graphs from your study materials
- **Interactive Exploration** - Click nodes to view definitions, relationships, and sources
- **Smart Layout** - Auto-arranged hierarchical visualization using Dagre algorithm
- **Source Attribution** - Color-coded nodes by source type (web/documents/both)
- **Export Capabilities**:
  - **PNG Images** - High-quality lossless format for presentations
  - **JPEG Images** - Compressed format for easy sharing
- **Fullscreen Mode** - Immersive viewing experience for complex maps
- **Minimap Navigation** - Bird's-eye view for large concept graphs

### 📝 Quiz Generation
- **AI-Generated Questions** - Automatically create quizzes from your documents
- **Multiple Formats** - MCQs, true/false, and short answer questions
- **Adaptive Difficulty** - Tailored to your study materials and learning level
- **Instant Feedback** - Immediate evaluation with detailed explanations
- **Source References** - Every question linked to specific document sections
- **Performance Tracking** - Monitor your progress and identify weak areas

### 🔐 Authentication & Security
- **OAuth 2.0 Integration** - Secure Google Sign-In (ready for deployment)
- **JWT Token Management** - Stateless authentication with refresh tokens
- **User Isolation** - Personal document libraries and chat spaces
- **Rate Limiting** - Protection against abuse and API overuse
- **Secure File Handling** - Sandboxed document processing

### ⚡ Performance Optimization
- **Redis Caching** - Lightning-fast responses for repeated queries
- **FAISS Vector Database** - Millisecond-level similarity search across thousands of documents
- **Async API Design** - Non-blocking operations for better concurrency
- **Efficient Chunking** - Optimized text segmentation for accurate retrieval
- **Smart Reranking** - BM25 scoring for improved result relevance

---

## 🛠️ Tech Stack

### Backend
| Technology | Purpose |
|------------|---------|
| **FastAPI 0.104+** | High-performance async web framework |
| **Python 3.9+** | Core programming language |
| **FAISS** | Facebook AI Similarity Search for vector operations |
| **Redis** | In-memory cache for query results |
| **Sentence Transformers** | Text embeddings (all-MiniLM-L6-v2) |
| **Google Gemini API** | Primary LLM for answer generation |
| **Tavily API** | Academic web search and augmentation |
| **Tesseract OCR** | Handwritten and scanned document processing |
| **PyPDF2 / pdfplumber** | PDF text extraction |
| **python-pptx** | PowerPoint processing |
| **python-docx** | Word document processing |
| **Pillow** | Image processing and OCR |
| **Authlib** | OAuth 2.0 implementation |
| **python-jose** | JWT token handling |

### Frontend
| Technology | Purpose |
|------------|---------|
| **React 18.0+** | Modern UI framework |
| **Tailwind CSS** | Utility-first styling |
| **React Flow** | Interactive graph visualization |
| **@react-oauth/google** | Google OAuth integration |
| **Axios** | HTTP client for API calls |
| **html-to-image** | Export concept maps as images |
| **jspdf** | Generate PDF exports |
| **React Hooks** | State management |

### Infrastructure & Tools
- **Git & GitHub** - Version control
- **Docker** - Containerization 
- **Render.com** - Backend hosting 
- **Vercel** - Frontend hosting 
- **SQLite** - User data and chat history 

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (React)                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Chat UI    │  │   Concept    │  │   Document Manager   │  │
│  │  (Real-time  │  │     Maps     │  │   (Multi-format)     │  │
│  │  Streaming)  │  │ (React Flow) │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ REST API (FastAPI)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │     RAG      │  │   Document   │  │   Authentication     │  │
│  │   Pipeline   │  │  Processing  │  │   (OAuth + JWT)      │  │
│  │              │  │  (OCR, PDF,  │  │                      │  │
│  │ -  Retrieval  │  │   PPTX, DOCX)│  │                      │  │
│  │ -  Reranking  │  │              │  │                      │  │
│  │ -  Generation │  │              │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                    │                      │
         ▼                    ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐
│  FAISS Vector   │  │     Redis       │  │   PostgreSQL     │
│    Database     │  │   (Cache)       │  │ (Users, Sessions)│
│                 │  │                 │  │    (Planned)     │
│ -  Embeddings    │  │ -  Query Cache   │  │                  │
│ -  Fast Search   │  │ -  Result Cache  │  │                  │
└─────────────────┘  └─────────────────┘  └──────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│                    External Services                          │
│  -  Google Gemini API (LLM)                                   │
│  -  Tavily API (Web Search)                                   │
│  -  Tesseract OCR (Text Extraction)                           │
└──────────────────────────────────────────────────────────────┘
```

### **Data Flow:**

1. **Document Upload** → OCR/Parsing → Chunking → Embedding → FAISS Index
2. **User Query** → Embedding → FAISS Search + Web Search → Reranking → LLM Generation → Streaming Response
3. **Concept Map** → Topic Analysis → Entity Extraction → Relationship Mapping → Graph Generation
4. **Quiz** → Document Analysis → Question Generation → Answer Validation

---

## 🚀 Setup & Installation

### Prerequisites
- **Python 3.9+** installed
- **Node.js 16+** and npm
- **Redis server** (for caching)
- **Git** for version control

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


### 3. Frontend Setup
```
cd frontend
npm install
cd ..
```



---


## 📖 Usage Guide

### Starting the Application

#### Step 1: Start Redis
```
# Verify Redis is running
redis-cli ping
# Expected output: PONG

# If not running, start it:
# Windows: redis-server
# Linux: sudo systemctl start redis
# Mac: brew services start redis
```

#### Step 2: Start Backend
```
# From root directory with virtual environment activated
cd src

uvicorn main:app --reload 
```

**Backend will be available at:** http://localhost:8000

**API Documentation:** http://localhost:8000/docs

#### Step 3: Start Frontend
```
cd frontend
npm start
```

**Frontend will open automatically at:** http://localhost:3000

---

### Using the Application

#### 1️⃣ Upload Documents

1. Click **"📤 Upload Documents"** button in the sidebar
2. Select your files:
   - ✅ PDFs
   - ✅ PowerPoint (.pptx)
   - ✅ Word Documents (.docx)
   - ✅ Images (with OCR for handwritten notes)
3. Click **"Upload"**
4. Wait for processing (OCR may take 10-30 seconds for images)
5. Documents are automatically:
   - Chunked into semantic segments
   - Embedded using sentence transformers
   - Indexed in FAISS for fast retrieval

**💡 Tip:** Upload multiple files at once for batch processing!

---

#### 2️⃣ Ask Questions

1. Type your question in the chat input at the bottom
2. Choose search mode:
   - **⚡ Quick Mode**: Fast document-only search (2-3 seconds)
   - **🔍 Deep Mode**: Comprehensive with web search (5-8 seconds)
3. Press **Enter** or click send button
4. Watch the AI generate your answer in real-time
5. Review:
   - **Answer** with streaming generation
   - **Confidence Score** (0-100%)
   - **Sources** with document references and web links

**💡 Tip:** Use "Quick" for straightforward questions, "Deep" for complex topics needing web context!

---

#### 3️⃣ Generate Concept Maps

1. Navigate to **"🗺️ Concept Maps"** section
2. Click **"+ New Concept Map"**
3. Enter a topic from your study materials
   - Example: "Neural Networks", "Photosynthesis", "Quantum Mechanics"
4. Click **"Generate Map"**
5. Wait 10-20 seconds for AI to:
   - Extract key concepts
   - Identify relationships
   - Build knowledge graph
6. Interact with the map:
   - **Click nodes** to view definitions
   - **Zoom** and **pan** to explore
   - **Toggle fullscreen** for better view
7. Export your map:
   - 🖼️ **PNG** - High quality, lossless (recommended)
   - 📷 **JPEG** - Smaller file size

**💡 Tip:** Color coding shows source type - Blue (web), Green (documents), Purple (both)!

---

#### 4️⃣ Take Quizzes

1. Go to **"📝 Quiz"** section
2. Click **"Generate New Quiz"**
3. Select options:
   - **Topic**: Choose from your uploaded documents
   - **Difficulty**: Easy, Medium, or Hard
   - **Number of Questions**: 5-20 questions
4. Click **"Create Quiz"**
5. Answer questions one by one
6. Get instant feedback:
   - ✅ Correct answers highlighted
   - ❌ Explanations for incorrect answers
   - 📚 Source references for learning
7. View your score and performance summary

**💡 Tip:** Review incorrect answers to identify knowledge gaps!

---

#### 5️⃣ Manage Chat Sessions

1. View all sessions in the left sidebar
2. **Rename a session**:
   - Hover over session
   - Click ✏️ pencil icon
   - Type new title
   - Press Enter to save
3. **Export conversations**:
   - Click 📥 download icon
   - Choose format:
     - **Markdown** - Plain text with formatting
     - **PDF** - Professional document with colors
4. **Delete old sessions**:
   - Click 🗑️ trash icon
   - Confirm deletion

**💡 Tip:** Organize sessions by subject (e.g., "Biology Ch.3", "ML Algorithms") for easy access!

---


## 📞 Contact


### 📧 Get in Touch
- **Email**: arhaan.ali2004@gmail.com
- **GitHub**: [@ArhaanAli04](https://github.com/ArhaanAli04)

### 🔗 Project Links

- **Live Demo**: https://rag-study-assistant-chi.vercel.app



---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---






