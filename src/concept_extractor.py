"""
Concept Extractor for Concept Map Generation
Uses LLM (Gemini) to extract concepts and relationships from hybrid context
"""

import os
import json
import re
from typing import Dict, List, Optional, Any
import logging
from google import genai  # [web:91][web:94]
from dotenv import load_dotenv


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConceptExtractor:
    """
    Extracts structured concepts and relationships from text using LLM
    Generates concept maps with proper source attribution
    """
    
    def __init__(self, model_name: str = "gemini-2.5-flash-lite"):
        """
        Initialize the concept extractor
        
        Args:
            api_key: Gemini API key (uses env var if not provided)
            model_name: Gemini model to use
        """
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not found. Set it in .env file.")
        
        # Configure Gemini
        self.client = genai.Client(api_key=api_key)
        # Initialize model
        self.model_name=model_name
        
        # Generation config for structured output
        self.generation_config = {
            "temperature": 0.3,  # Lower for more consistent structured output
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 4096,
        }
        
        logger.info(f" ConceptExtractor initialized with {model_name}")
    
    
    def _build_extraction_prompt(
        self,
        topic: str,
        context: str,
        max_concepts: int = 15,
        max_edges: int = 20
    ) -> str:
        """
        Build the prompt for concept extraction
        
        Args:
            topic: The concept map topic
            context: Retrieved context (documents + web)
            max_concepts: Maximum number of concepts to extract
            max_edges: Maximum number of relationships to extract
            
        Returns:
            Formatted prompt string
        """
        prompt = f"""You are an expert at creating educational concept maps. Your task is to extract key concepts and their relationships from the given context about "{topic}".

# Context Information:
{context}

# Task:
Create a concept map by identifying:
1. **Key Concepts (Nodes)**: Important ideas, terms, definitions, or entities related to "{topic}"
2. **Relationships (Edges)**: How these concepts connect to each other

# Instructions:
- Extract up to {max_concepts} most important concepts
- Identify up to {max_edges} meaningful relationships between concepts
- Each concept should have:
  - A clear, concise label (2-5 words)
  - A brief definition/description (1-2 sentences)
  - Source attribution (document name or web URL)
- Each relationship should have:
  - Source concept
  - Target concept  
  - Relationship label (verb/phrase describing the connection)
- Focus on concepts that are:
  - Central to understanding "{topic}"
  - Well-explained in the context
  - Interconnected with other concepts
- Avoid:
  - Generic concepts (unless central to the topic)
  - Concepts not explained in the context
  - Duplicate or redundant concepts

# Output Format:
Return ONLY a valid JSON object with this exact structure (no markdown, no code blocks, just raw JSON):

{{
  "topic": "{topic}",
  "nodes": [
    {{
      "id": "concept_1",
      "label": "Concept Name",
      "definition": "Brief explanation of the concept",
      "source_type": "web" or "document",
      "sources": ["Source URL or filename"]
    }}
  ],
  "edges": [
    {{
      "from": "concept_1",
      "to": "concept_2",
      "label": "relationship description"
    }}
  ]
}}

# Important Notes:
1. Use snake_case IDs (e.g., "neural_network", "attention_mechanism")
2. Ensure all edge references point to valid node IDs
3. Keep labels concise (2-5 words)
4. Keep definitions informative but brief (1-2 sentences)
5. Return ONLY the JSON - no explanation, no markdown formatting

Now extract the concept map:"""
        
        return prompt
    
    
    def _parse_llm_response(self, response_text: str) -> Optional[Dict]:
        """
        Parse LLM response into structured JSON
        
        Args:
            response_text: Raw response from LLM
            
        Returns:
            Parsed JSON dict or None if parsing fails
        """
        try:
            cleaned = response_text.strip()
            
            # Remove any markdown formatting
            # Look for JSON object boundaries
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            
            if start_idx != -1 and end_idx != -1:
                cleaned = cleaned[start_idx:end_idx+1]
            
            # Parse JSON
            result = json.loads(cleaned)
            
            logger.info(f"✅ Parsed {len(result.get('nodes', []))} nodes and {len(result.get('edges', []))} edges")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse JSON: {e}")
            logger.error(f"Response text preview: {response_text[:500]}...")
            
            # Try regex extraction as fallback
            try:
                import re
                match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if match:
                    result = json.loads(match.group(0))
                    logger.info("✅ Recovered JSON from text using regex")
                    return result
            except Exception as ex:
                logger.error(f"❌ Regex extraction failed: {ex}")
            
            return None


    
    
    def _validate_and_clean_concept_map(self, concept_map: Dict) -> Dict:
        """
        Validate and clean the concept map data
        
        Args:
            concept_map: Raw concept map from LLM
            
        Returns:
            Cleaned and validated concept map
        """
        # Ensure required fields exist
        if "nodes" not in concept_map:
            concept_map["nodes"] = []
        if "edges" not in concept_map:
            concept_map["edges"] = []
        
        # Validate nodes
        valid_nodes = []
        node_ids = set()
        
        for node in concept_map["nodes"]:
            # Check required fields
            if "id" not in node or "label" not in node:
                logger.warning(f" Skipping node without id or label: {node}")
                continue
            
            # Ensure unique IDs
            if node["id"] in node_ids:
                logger.warning(f" Duplicate node ID: {node['id']}")
                node["id"] = f"{node['id']}_{len(valid_nodes)}"
            
            node_ids.add(node["id"])
            
            # Add default values for missing fields
            if "definition" not in node:
                node["definition"] = ""
            if "source_type" not in node:
                node["source_type"] = "unknown"
            if "sources" not in node:
                node["sources"] = []
            
            valid_nodes.append(node)
        
        # Validate edges
        valid_edges = []
        
        for edge in concept_map["edges"]:
            # Check required fields
            if "from" not in edge or "to" not in edge:
                logger.warning(f" Skipping edge without from/to: {edge}")
                continue
            
            # Check that referenced nodes exist
            if edge["from"] not in node_ids or edge["to"] not in node_ids:
                logger.warning(f" Skipping edge with invalid node reference: {edge['from']} -> {edge['to']}")
                continue
            
            # Add default label if missing
            if "label" not in edge:
                edge["label"] = "relates to"
            
            valid_edges.append(edge)
        
        concept_map["nodes"] = valid_nodes
        concept_map["edges"] = valid_edges
        
        logger.info(f" Validated: {len(valid_nodes)} nodes, {len(valid_edges)} edges")
        
        return concept_map
    
    
    def _add_source_attribution(
        self,
        concept_map: Dict,
        retrieval_result: Dict
    ) -> Dict:
        """
        Enhance concept map with detailed source attribution
        
        Args:
            concept_map: Concept map from LLM
            retrieval_result: Original retrieval result with source metadata
            
        Returns:
            Concept map with enhanced source attribution
        """
        # Extract source information from retrieval result
        doc_sources = retrieval_result.get('sources', {}).get('document_sources', [])
        web_sources = retrieval_result.get('sources', {}).get('web_sources', [])
        
        # Add source summary to concept map
        concept_map['source_summary'] = {
            'total_sources': len(doc_sources) + len(web_sources),
            'document_sources': doc_sources,
            'web_sources': web_sources,
            'confidence': retrieval_result.get('confidence', 0.0)
        }
        
        # Enhance node sources with more details
        for node in concept_map.get('nodes', []):
            # If sources list is empty or generic, try to infer from source_type
            if not node.get('sources'):
                if node.get('source_type') == 'web' and web_sources:
                    node['sources'] = [web_sources]  # Assign first web source
                elif node.get('source_type') == 'document' and doc_sources:
                    node['sources'] = [doc_sources]  # Assign first doc source
        
        return concept_map
    
    
    def extract_concepts_from_context(
        self,
        topic: str,
        context: str,
        retrieval_result: Optional[Dict] = None,
        max_concepts: int = 15,
        max_edges: int = 20
    ) -> Optional[Dict]:
        """
        Extract concepts from context using LLM
        
        Args:
            topic: The concept map topic
            context: Retrieved context (from hybrid retrieval)
            retrieval_result: Original retrieval result for source attribution
            max_concepts: Maximum concepts to extract
            max_edges: Maximum relationships to extract
            
        Returns:
            Structured concept map dict or None if extraction fails
        """
        logger.info(f" Extracting concepts for topic: '{topic}'")
        logger.info(f"   Context length: {len(context)} characters")
        
        # Check for empty context
        if not context or len(context.strip()) < 100:
            logger.warning(" Context too short or empty")
            return self._create_empty_concept_map(topic, "Insufficient context available")
        
        # Build prompt
        prompt = self._build_extraction_prompt(
            topic=topic,
            context=context,
            max_concepts=max_concepts,
            max_edges=max_edges
        )
        
        try:
            # Call Gemini API
            logger.info(" Calling Gemini API...")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            
            # Get response text
            response_text = response.text
            logger.info(f" Received response ({len(response_text)} chars)")
            
            # Parse response
            concept_map = self._parse_llm_response(response_text)
            
            if not concept_map:
                logger.error(" Failed to parse concept map")
                return self._create_empty_concept_map(topic, "Failed to parse LLM response")
            
            # Validate and clean
            concept_map = self._validate_and_clean_concept_map(concept_map)
            
            # Add source attribution
            if retrieval_result:
                concept_map = self._add_source_attribution(concept_map, retrieval_result)
            
            # Add metadata
            concept_map['metadata'] = {
                'topic': topic,
                'node_count': len(concept_map.get('nodes', [])),
                'edge_count': len(concept_map.get('edges', [])),
                'context_length': len(context),
                'model': 'gemini-1.5-flash'
            }
            
            logger.info(f" Extraction complete: {concept_map['metadata']['node_count']} nodes, {concept_map['metadata']['edge_count']} edges")
            
            return concept_map
            
        except Exception as e:
            logger.error(f" Concept extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return self._create_empty_concept_map(topic, f"Extraction error: {str(e)}")
    
    
    def extract_concepts_from_hybrid_sources(
        self,
        topic: str,
        retrieval_result: Dict,
        max_concepts: int = 15,
        max_edges: int = 20
    ) -> Optional[Dict]:
        """
        Extract concepts from hybrid retrieval result
        Convenience method that formats context from retrieval result
        
        Args:
            topic: The concept map topic
            retrieval_result: Result from ConceptMapRetriever
            max_concepts: Maximum concepts to extract
            max_edges: Maximum relationships to extract
            
        Returns:
            Structured concept map dict or None if extraction fails
        """
        # Format context from retrieval result
        context_parts = []
        
        # Add document context
        doc_results = retrieval_result.get('document_results', [])
        if doc_results:
            context_parts.append("## From Documents:\n")
            for i, result in enumerate(doc_results[:10], 1):
                metadata = result.get('metadata', {})
                source = metadata.get('file_name', 'Unknown')
                context_parts.append(f"\n[Document {i}] {source}:")
                context_parts.append(result.get('text', ''))
        
        # Add web context
        web_results = retrieval_result.get('web_results', [])
        if web_results:
            context_parts.append("\n\n## From Web:\n")
            for i, result in enumerate(web_results[:8], 1):
                metadata = result.get('metadata', {})
                title = metadata.get('title', 'Unknown')
                url = metadata.get('url', 'N/A')
                context_parts.append(f"\n[Web {i}] {title} ({url}):")
                context_parts.append(result.get('text', ''))
        
        context = "\n".join(context_parts)
        
        # Extract concepts
        return self.extract_concepts_from_context(
            topic=topic,
            context=context,
            retrieval_result=retrieval_result,
            max_concepts=max_concepts,
            max_edges=max_edges
        )
    
    
    def _create_empty_concept_map(self, topic: str, reason: str) -> Dict:
        """
        Create an empty concept map with error information
        
        Args:
            topic: The topic
            reason: Reason for empty map
            
        Returns:
            Empty concept map structure
        """
        logger.warning(f" Creating empty concept map: {reason}")
        
        return {
            "topic": topic,
            "nodes": [],
            "edges": [],
            "metadata": {
                "topic": topic,
                "node_count": 0,
                "edge_count": 0,
                "error": reason
            },
            "source_summary": {
                "total_sources": 0,
                "document_sources": [],
                "web_sources": [],
                "confidence": 0.0
            }
        }
    
    
    def format_concept_map_summary(self, concept_map: Dict) -> str:
        """
        Format a human-readable summary of the concept map
        
        Args:
            concept_map: Concept map structure
            
        Returns:
            Formatted summary string
        """
        if not concept_map:
            return "No concept map available"
        
        lines = [
            "=" * 70,
            f"  Concept Map: {concept_map.get('topic', 'Unknown')}",
            "=" * 70,
            ""
        ]
        
        # Metadata
        metadata = concept_map.get('metadata', {})
        lines.append(f"📊 Statistics:")
        lines.append(f"   Nodes: {metadata.get('node_count', 0)}")
        lines.append(f"   Edges: {metadata.get('edge_count', 0)}")
        
        # Source summary
        sources = concept_map.get('source_summary', {})
        lines.append(f"\n📚 Sources:")
        lines.append(f"   Total: {sources.get('total_sources', 0)}")
        lines.append(f"   Confidence: {sources.get('confidence', 0):.1f}%")
        
        # Nodes
        nodes = concept_map.get('nodes', [])
        if nodes:
            lines.append(f"\n🔵 Key Concepts:")
            for i, node in enumerate(nodes[:10], 1):
                lines.append(f"\n{i}. {node.get('label', 'Unknown')}")
                lines.append(f"   {node.get('definition', 'No definition')[:100]}...")
                sources_list = node.get('sources', [])
                if sources_list:
                    lines.append(f"   Source: {sources_list}")
        
        # Edges
        edges = concept_map.get('edges', [])
        if edges:
            lines.append(f"\n🔗 Relationships:")
            for i, edge in enumerate(edges[:10], 1):
                lines.append(f"{i}. {edge.get('from', '?')} --[{edge.get('label', 'relates to')}]--> {edge.get('to', '?')}")
        
        lines.append("\n" + "=" * 70)
        
        return "\n".join(lines)


# Convenience function
def create_concept_extractor() -> ConceptExtractor:
    """Create and return a ConceptExtractor instance"""
    return ConceptExtractor()


if __name__ == "__main__":
    # Quick test
    print("=" * 70)
    print("  Testing ConceptExtractor")
    print("=" * 70)
    
    try:
        extractor = create_concept_extractor()
        
        # Test with sample context
        test_topic = "Neural Networks"
        test_context = """
        Neural networks are computing systems inspired by biological neural networks.
        They consist of interconnected nodes (neurons) organized in layers.
        
        Deep learning uses neural networks with multiple layers (deep neural networks).
        Backpropagation is the algorithm used to train neural networks by calculating gradients.
        
        Activation functions introduce non-linearity into neural networks.
        Common activation functions include ReLU, sigmoid, and tanh.
        """
        
        concept_map = extractor.extract_concepts_from_context(
            topic=test_topic,
            context=test_context,
            max_concepts=8,
            max_edges=10
        )
        
        if concept_map:
            print("\n" + extractor.format_concept_map_summary(concept_map))
        else:
            print("\n❌ Failed to extract concepts")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
