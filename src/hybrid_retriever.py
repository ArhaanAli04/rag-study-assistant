"""
Hybrid Retrieval System for Concept Map Generation
Wraps existing RetrievalService to provide concept-map-specific retrieval
"""

import os
import sys
from typing import List, Dict, Optional
import logging

# Add parent directory to path to import from root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval_service import RetrievalService
from index_builder import IndexBuilder
from keyword_index import BM25KeywordIndex

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConceptMapRetriever:
    """
    Specialized retriever for concept map generation
    Uses existing RetrievalService with concept-map-optimized settings
    """
    
    def __init__(self, retrieval_service: Optional[RetrievalService] = None):
        """
        Initialize the concept map retriever
        
        Args:
            retrieval_service: Optional existing RetrievalService instance
        """
        if retrieval_service:
            self.retrieval_service = retrieval_service
        else:
            # Create new instance
            logger.info("Creating new RetrievalService instance...")
            try:
                # Initialize index builder and BM25
                index_builder = IndexBuilder()
                
                # Try to load BM25 index if available
                bm25_index = None
                try:
                    bm25_index = BM25KeywordIndex()
                    logger.info("✅ BM25 index loaded")
                except Exception as e:
                    logger.warning(f"⚠️ BM25 index not available: {e}")
                
                self.retrieval_service = RetrievalService(
                    index_builder=index_builder,
                    bm25_index=bm25_index
                )
                logger.info("✅ RetrievalService initialized")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize RetrievalService: {e}")
                raise
    
    
    def retrieve_for_concept_map(
        self,
        topic: str,
        user_id: str,
        doc_version: int = 0,
        use_documents: bool = False,
        use_web: bool = True,
        max_results: int = 15
    ) -> Dict:
        """
        Retrieve context optimized for concept map generation
        
        Args:
            topic: The concept map topic
            user_id: User ID for document filtering
            doc_version: Document version for cache invalidation
            use_documents: Whether to search user documents
            use_web: Whether to search the web
            max_results: Maximum number of results to return
            
        Returns:
            Dictionary with:
                - combined_results: List of all results
                - document_results: Document-only results
                - web_results: Web-only results
                - sources: Source statistics
                - confidence: Retrieval confidence score
        """
        logger.info(f"🔍 Retrieving for concept map: '{topic}'")
        logger.info(f"   Documents: {use_documents}, Web: {use_web}")
        
        all_results = []
        document_results = []
        web_results = []
        confidence = 0.0
        
        # Case 1: Documents + Web (Full Hybrid)
        if use_documents and use_web:
            logger.info("📚🌐 Using full hybrid retrieval")
            
            result = self.retrieval_service.hybrid_retrieve(
                query=topic,
                user_id=user_id,
                doc_version=doc_version,
                top_k=max_results,
                rerank_top_k=max_results
            )
            
            all_results = result.get('results', [])
            confidence = result.get('confidence', 0.0)
            
            # Separate by source type
            for r in all_results:
                source_type = r.get('metadata', {}).get('source_type', 'local')
                if source_type == 'web':
                    web_results.append(r)
                else:
                    document_results.append(r)
        
        # Case 2: Documents Only
        elif use_documents and not use_web:
            logger.info("📚 Using documents only")
            
            # Use hybrid_retrieve but limit web results
            result = self.retrieval_service.hybrid_retrieve(
                query=topic,
                user_id=user_id,
                doc_version=doc_version,
                top_k=max_results,
                rerank_top_k=max_results
            )
            
            # Filter out web results
            all_results = [
                r for r in result.get('results', [])
                if r.get('metadata', {}).get('source_type', 'local') != 'web'
            ]
            document_results = all_results
            confidence = result.get('confidence', 0.0)
        
        # Case 3: Web Only
        elif not use_documents and use_web:
            logger.info("🌐 Using web search only")
            
            try:
                # Get web chunks directly
                web_chunks = self.retrieval_service.get_web_chunks(
                    query=topic,
                    max_results=max_results,
                    chunk_size=800,  # Larger chunks for concept maps
                    overlap=100
                )
                
                # Format as results
                for chunk in web_chunks:
                    web_results.append({
                        'text': chunk['text'],
                        'metadata': chunk['metadata'],
                        'score': 0.8  # Default web score
                    })
                
                all_results = web_results
                confidence = 70.0  # Moderate confidence for web-only
                
            except Exception as e:
                logger.error(f"❌ Web search failed: {e}")
                confidence = 0.0
        
        else:
            logger.warning("⚠️ Both use_documents and use_web are False")
        
        # Calculate source statistics
        sources = {
            'total': len(all_results),
            'documents': len(document_results),
            'web': len(web_results),
            'document_sources': self._extract_document_sources(document_results),
            'web_sources': self._extract_web_sources(web_results)
        }
        
        logger.info(f"✅ Retrieved {sources['total']} total results")
        logger.info(f"   Documents: {sources['documents']}, Web: {sources['web']}")
        logger.info(f"   Confidence: {confidence:.1f}%")
        
        return {
            'combined_results': all_results,
            'document_results': document_results,
            'web_results': web_results,
            'sources': sources,
            'topic': topic,
            'confidence': confidence
        }
    
    
    def _extract_document_sources(self, results: List[Dict]) -> List[str]:
        """Extract unique document source names"""
        sources = set()
        for r in results:
            metadata = r.get('metadata', {})
            file_name = metadata.get('file_name') or metadata.get('filename')
            if file_name:
                sources.add(file_name)
        return list(sources)
    
    
    def _extract_web_sources(self, results: List[Dict]) -> List[str]:
        """Extract unique web URLs"""
        urls = set()
        for r in results:
            metadata = r.get('metadata', {})
            url = metadata.get('url')
            if url:
                urls.add(url)
        return list(urls)
    
    
    def format_context_for_llm(self, retrieval_result: Dict) -> str:
        """
        Format retrieval results into context string for LLM
        
        Args:
            retrieval_result: Output from retrieve_for_concept_map()
            
        Returns:
            Formatted context string optimized for concept extraction
        """
        combined = retrieval_result['combined_results']
        
        if not combined:
            return f"No relevant information found for topic: {retrieval_result['topic']}"
        
        context_parts = [
            f"# Context for Topic: {retrieval_result['topic']}",
            f"# Confidence: {retrieval_result.get('confidence', 0):.1f}%",
            f"# Total Sources: {len(combined)} ({retrieval_result['sources']['documents']} documents, {retrieval_result['sources']['web']} web)",
            ""
        ]
        
        # Add document context
        doc_results = retrieval_result['document_results']
        if doc_results:
            context_parts.append("## From Your Documents:")
            for i, result in enumerate(doc_results[:10], 1):  # Limit to top 10
                metadata = result.get('metadata', {})
                source = metadata.get('file_name') or metadata.get('filename', 'Unknown')
                page = metadata.get('page_num', 'N/A')
                
                context_parts.append(f"\n[Document {i}] {source} (Page: {page})")
                context_parts.append(result.get('text', ''))
        
        # Add web context
        web_results = retrieval_result['web_results']
        if web_results:
            context_parts.append("\n## From Web Search:")
            for i, result in enumerate(web_results[:8], 1):  # Limit to top 8
                metadata = result.get('metadata', {})
                title = metadata.get('title', 'Unknown')
                url = metadata.get('url', 'N/A')
                
                context_parts.append(f"\n[Web {i}] {title}")
                context_parts.append(f"URL: {url}")
                context_parts.append(result.get('text', ''))
        
        return "\n".join(context_parts)


# Convenience function
def create_concept_retriever(retrieval_service: Optional[RetrievalService] = None) -> ConceptMapRetriever:
    """Create and return a ConceptMapRetriever instance"""
    return ConceptMapRetriever(retrieval_service=retrieval_service)


if __name__ == "__main__":
    # Quick test
    print("=" * 70)
    print("  Testing ConceptMapRetriever")
    print("=" * 70)
    
    try:
        retriever = create_concept_retriever()
        
        test_topic = "Machine Learning"
        test_user_id = "test_user"
        
        result = retriever.retrieve_for_concept_map(
            topic=test_topic,
            user_id=test_user_id,
            use_documents=False,
            use_web=True
        )
        
        print(f"\n📊 Results for '{test_topic}':")
        print(f"   Total: {result['sources']['total']}")
        print(f"   Documents: {result['sources']['documents']}")
        print(f"   Web: {result['sources']['web']}")
        print(f"   Confidence: {result['confidence']:.1f}%")
        
        if result['combined_results']:
            print(f"\n📝 Top 3 results:")
            for i, r in enumerate(result['combined_results'][:3], 1):
                source_type = r.get('metadata', {}).get('source_type', 'local')
                print(f"\n{i}. [{source_type.upper()}]")
                print(f"   Text: {r.get('text', '')[:150]}...")
        
        print("\n" + "=" * 70)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
