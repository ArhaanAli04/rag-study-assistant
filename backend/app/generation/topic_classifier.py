"""
LLM-based topic classifier for dynamic academic subject detection
Uses the same Google GenAI SDK as llm_client.py
"""
import logging
from typing import Dict
from google import genai

logger = logging.getLogger("rag_assistant")

class TopicClassifier:
    def __init__(self, client: genai.Client, model_name: str) -> None:
        self.client = client
        self.model_name = model_name

    def classify_topic(self, text: str) -> Dict:
        """
        Extract the primary academic subject/topic from user query
        
        Args:
            text: User query text
            
        Returns:
            dict with 'topic', 'confidence', and 'method' keys
        """
        
        prompt = f"""Extract the primary academic subject from this student query.

Query: "{text}"

Return ONLY the broad academic subject category. Choose from common study domains like:
- Machine Learning
- Deep Learning
- Natural Language Processing
- Computer Vision
- Data Structures
- Algorithms
- Python Programming
- Web Development
- Database Systems
- Operating Systems
- Computer Networks
- Software Engineering
- Mathematics
- Statistics
- Physics
- Chemistry
- Biology
- History
- Literature
- Economics
- etc.

Rules:
- Return ONLY the category name (2-4 words maximum)
- If it's a greeting or general chat, return "General"
- If unclear, return "General"
- Be specific but concise

Topic:"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            
            # Extract text from response
            topic = response.text.strip() if hasattr(response, 'text') else str(response).strip()
            
            # Clean up the response
            topic = topic.replace('"', '').replace("'", "").replace('*', '').strip()
            
            # Remove common prefixes
            topic = topic.replace('Topic:', '').replace('Subject:', '').strip()
            
            # Validation
            if len(topic.split()) > 5 or len(topic) > 50 or not topic:
                topic = "General"
            
            # High confidence since LLM understands context well
            confidence = 0.85 if topic != "General" else 0.0
            
            logger.info(f"Topic extracted: '{topic}' from query: '{text[:50]}...'")
            
            return {
                'topic': topic,
                'confidence': confidence,
                'method': 'llm_extraction'
            }
            
        except Exception as e:
            logger.error(f"Topic extraction failed: {e}")
            return {
                'topic': 'General',
                'confidence': 0.0,
                'method': 'error_fallback'
            }
