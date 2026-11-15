"""
Concept Map Service - Business logic for concept map operations
Handles database operations, retrieval, and extraction
"""

import ast
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime,timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.models.concept_map import ConceptMap, ConceptMapNode
from app.retrieval.concept_map_retriever import ConceptMapRetriever
from app.generation.concept_extractor import ConceptExtractor

logger = logging.getLogger(__name__)


class NoConceptContext(Exception):
    """Retrieval found nothing in the selected sources; no map is built or saved."""


class ConceptExtractionFailed(Exception):
    """Context was found but no concepts came out of it; nothing is saved."""


def no_context_message(use_documents: bool, use_web: bool) -> str:
    if use_documents and use_web:
        return "Neither your documents nor web search found anything on this topic. Try another topic."
    if use_documents:
        return "No passages in your documents match this topic. Try another topic or turn on web search."
    return "Web search found nothing usable on this topic. Try another topic or use your documents."


def off_topic_message(topic: str, use_documents: bool, use_web: bool) -> str:
    """The model found passages but judged none of them to be about the topic."""
    if use_documents and use_web:
        return f"Neither your documents nor the web results seem to cover '{topic}'. Try another topic."
    if use_documents:
        return f"Your documents don't seem to cover '{topic}'. Try another topic or turn on web search."
    return f"The web results don't seem to cover '{topic}'. Try another topic."


def encode_sources(sources: List[str]) -> str:
    # A JSON array: the comma-joined form split "notes, week 3.pdf" into two sources.
    return json.dumps(sources)


def decode_sources(stored: Optional[str]) -> List[str]:
    if not stored:
        return []
    if stored.startswith("["):
        try:
            decoded = json.loads(stored)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return [str(s) for s in decoded]
    return stored.split(",")  # maps saved before Day 17


class ConceptMapService:
    """
    Service layer for concept map operations
    Orchestrates retrieval, extraction, and database operations
    """

    def __init__(self, retriever: ConceptMapRetriever, extractor: ConceptExtractor) -> None:
        self.retriever = retriever
        self.extractor = extractor

    def generate_concept_map(
        self,
        topic: str,
        user_id: int,
        doc_version: int,
        db: Session,
        use_documents: bool = False,
        use_web: bool = True,
        max_concepts: int = 15,
        max_edges: int = 20
    ) -> Dict[str, Any]:
        """Retrieve → extract → save; returns map_id, nodes, edges, sources, metadata, created_at.

        Raises NoConceptContext when the selected sources return nothing or the model flags what they
        returned as off-topic (vector search always returns the nearest chunks, Day 17 live check: a
        "French Revolution" map was built from photosynthesis notes), and ConceptExtractionFailed when
        no concept comes out — in every case nothing is saved, instead of a 0-concept or wrong map.
        """
        logger.info("Generating concept map for user %s", user_id)
        retrieval_result = self.retriever.retrieve_for_concept_map(
            topic=topic,
            user_id=str(user_id),
            doc_version=doc_version,
            use_documents=use_documents,
            use_web=use_web,
            max_results=12,
        )
        if retrieval_result["sources"]["total"] == 0:
            raise NoConceptContext(no_context_message(use_documents, use_web))

        concept_map_data = self.extractor.extract_concepts_from_hybrid_sources(
            topic=topic,
            retrieval_result=retrieval_result,
            max_concepts=max_concepts,
            max_edges=max_edges,
        )
        if concept_map_data.get("off_topic") is True:
            raise NoConceptContext(off_topic_message(topic, use_documents, use_web))
        if not concept_map_data.get("nodes"):
            raise ConceptExtractionFailed(
                "Couldn't build a concept map from the passages found. Try again or rephrase the topic."
            )

        map_id = self._save_concept_map_to_db(
            user_id=user_id,
            topic=topic,
            concept_map_data=concept_map_data,
            retrieval_result=retrieval_result,
            db=db,
        )
        logger.info("Concept map %s saved: %d nodes", map_id, len(concept_map_data["nodes"]))
        return self._format_generate_response(
            map_id=map_id,
            concept_map_data=concept_map_data,
            retrieval_result=retrieval_result,
        )
    
    
    def _save_concept_map_to_db(
        self,
        user_id: int,
        topic: str,
        concept_map_data: Dict,
        retrieval_result: Dict,
        db: Session
    ) -> int:
        """
        Save concept map and nodes to database
        
        Args:
            user_id: User ID
            topic: Topic name
            concept_map_data: Concept map from extractor
            retrieval_result: Retrieval result for source metadata
            db: Database session
            
        Returns:
            Created concept map ID
        """
        try:
            # Extract metadata
            metadata = concept_map_data.get('metadata', {})
            source_summary = concept_map_data.get('source_summary', {})
            
            # Create ConceptMap record
            concept_map = ConceptMap(
                user_id=user_id,
                topic=topic,
                node_count=metadata.get('node_count', 0),
                edge_count=metadata.get('edge_count', 0),
                source_document_count=len(source_summary.get('document_sources', [])),
                source_web_count=len(source_summary.get('web_sources', [])),
                confidence_score=source_summary.get('confidence', 0.0),
                created_at=datetime.utcnow()
            )
            
            db.add(concept_map)
            db.flush()  # Get the ID
            
            # Create ConceptMapNode records
            nodes = concept_map_data.get('nodes', [])
            edges = concept_map_data.get('edges', [])
            
            for node in nodes:
                node_record = ConceptMapNode(
                    map_id=concept_map.id,
                    node_id=node.get('id', ''),
                    label=node.get('label', ''),
                    definition=node.get('definition', ''),
                    source_type=node.get('source_type', 'unknown'),
                    sources_json=encode_sources(node.get('sources', [])),
                )
                db.add(node_record)
            
            # Store edges as JSON in the concept_map metadata (we don't have a separate table)
            # We'll add edges as JSON field in the response
            concept_map.edges_json = str(edges)  # You might want to add this column to your model
            
            db.commit()
            
            logger.info(f" Saved concept map to database (ID: {concept_map.id})")
            logger.info(f"   Nodes: {len(nodes)}, Edges: {len(edges)}")
            
            return concept_map.id
            
        except Exception as e:
            db.rollback()
            logger.error(f" Failed to save to database: {e}")
            raise
    
    
    def _format_generate_response(
        self,
        map_id: int,
        concept_map_data: Dict,
        retrieval_result: Dict
    ) -> Dict[str, Any]:
        """
        Format the generate endpoint response
        
        Args:
            map_id: Created concept map ID
            concept_map_data: Concept map data
            retrieval_result: Retrieval result
            
        Returns:
            Formatted response dictionary
        """
        return {
            "map_id": map_id,
            "topic": concept_map_data.get('topic', ''),
            "nodes": concept_map_data.get('nodes', []),
            "edges": concept_map_data.get('edges', []),
            "sources": {
                "total": retrieval_result['sources']['total'],
                "documents": retrieval_result['sources']['documents'],
                "web": retrieval_result['sources']['web'],
                "document_sources": retrieval_result['sources'].get('document_sources', []),
                "web_sources": retrieval_result['sources'].get('web_sources', [])
            },
            "metadata": concept_map_data.get('metadata', {}),
            "created_at": datetime.utcnow().isoformat()
        }
    
    
    def list_user_concept_maps(
        self,
        user_id: int,
        db: Session,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all concept maps for a user
        
        Args:
            user_id: User ID
            db: Database session
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of concept map summaries
        """
        try:
            # Query concept maps ordered by created_at DESC
            maps = db.query(ConceptMap)\
                .filter(ConceptMap.user_id == user_id)\
                .order_by(desc(ConceptMap.created_at))\
                .limit(limit)\
                .offset(offset)\
                .all()
            
            # Format response
            result = []
            for map_obj in maps:
                result.append({
                    "id": map_obj.id,
                    "topic": map_obj.topic,
                    "created_at": map_obj.created_at.replace(tzinfo=timezone.utc).isoformat(),
                    "node_count": map_obj.node_count,
                    "edge_count": map_obj.edge_count,
                    "sources": {
                        "documents": map_obj.source_document_count,
                        "web": map_obj.source_web_count
                    },
                    "confidence": map_obj.confidence_score
                })
            
            logger.info(f" Listed {len(result)} concept maps for user {user_id}")
            return result
            
        except Exception as e:
            logger.error(f" Failed to list concept maps: {e}")
            raise
    
    
    def get_concept_map_by_id(
        self,
        map_id: int,
        user_id: int,
        db: Session
    ) -> Optional[Dict[str, Any]]:
        """
        Get full concept map data by ID
        
        Args:
            map_id: Concept map ID
            user_id: User ID (for ownership verification)
            db: Database session
            
        Returns:
            Full concept map data or None if not found
        """
        try:
            # Query concept map with ownership check
            concept_map = db.query(ConceptMap)\
                .filter(ConceptMap.id == map_id)\
                .filter(ConceptMap.user_id == user_id)\
                .first()
            
            if not concept_map:
                logger.warning(f" Concept map {map_id} not found or access denied for user {user_id}")
                return None
            
            # Query nodes
            nodes = db.query(ConceptMapNode)\
                .filter(ConceptMapNode.map_id == map_id)\
                .all()
            
            # Format nodes
            formatted_nodes = []
            for node in nodes:
                formatted_nodes.append({
                    "id": node.node_id,
                    "label": node.label,
                    "definition": node.definition,
                    "source_type": node.source_type,
                    "sources": decode_sources(node.sources_json),
                })

            # Parse edges from stored JSON (if available)
            edges = []
            if hasattr(concept_map, 'edges_json') and concept_map.edges_json:
                try:
                    edges = ast.literal_eval(concept_map.edges_json)
                except (ValueError, SyntaxError):
                    logger.warning("Concept map %s has unreadable edges", map_id)
                    edges = []
            
            # Format response
            result = {
                "id": concept_map.id,
                "topic": concept_map.topic,
                "nodes": formatted_nodes,
                "edges": edges,
                "metadata": {
                    "node_count": concept_map.node_count,
                    "edge_count": concept_map.edge_count,
                    "confidence": concept_map.confidence_score
                },
                "sources": {
                    "documents": concept_map.source_document_count,
                    "web": concept_map.source_web_count
                },
                "created_at": concept_map.created_at.isoformat()
            }
            
            logger.info(f" Retrieved concept map {map_id}")
            return result
            
        except Exception as e:
            logger.error(f" Failed to get concept map: {e}")
            raise
    
    
    def delete_concept_map(
        self,
        map_id: int,
        user_id: int,
        db: Session
    ) -> bool:
        """
        Delete a concept map
        
        Args:
            map_id: Concept map ID
            user_id: User ID (for ownership verification)
            db: Database session
            
        Returns:
            True if deleted, False if not found
        """
        try:
            # Query concept map with ownership check
            concept_map = db.query(ConceptMap)\
                .filter(ConceptMap.id == map_id)\
                .filter(ConceptMap.user_id == user_id)\
                .first()
            
            if not concept_map:
                logger.warning(f" Concept map {map_id} not found or access denied for user {user_id}")
                return False
            
            # Delete associated nodes
            db.query(ConceptMapNode)\
                .filter(ConceptMapNode.map_id == map_id)\
                .delete()
            
            # Delete concept map
            db.delete(concept_map)
            db.commit()
            
            logger.info(f" Deleted concept map {map_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f" Failed to delete concept map: {e}")
            raise
    
    
    def get_source_statistics(
        self,
        user_id: int,
        db: Session
    ) -> Dict[str, Any]:
        """
        Get statistics about concept map sources
        
        Args:
            user_id: User ID
            db: Database session
            
        Returns:
            Source statistics
        """
        try:
            maps = db.query(ConceptMap)\
                .filter(ConceptMap.user_id == user_id)\
                .all()
            
            total_maps = len(maps)
            total_documents = sum(m.source_document_count for m in maps)
            total_web = sum(m.source_web_count for m in maps)
            total_nodes = sum(m.node_count for m in maps)
            total_edges = sum(m.edge_count for m in maps)
            avg_confidence = sum(m.confidence_score for m in maps) / total_maps if total_maps > 0 else 0.0
            
            return {
                "total_maps": total_maps,
                "total_sources": {
                    "documents": total_documents,
                    "web": total_web,
                    "total": total_documents + total_web
                },
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "average_confidence": round(avg_confidence, 2),
                "maps_per_source_type": {
                    "documents_only": len([m for m in maps if m.source_document_count > 0 and m.source_web_count == 0]),
                    "web_only": len([m for m in maps if m.source_web_count > 0 and m.source_document_count == 0]),
                    "hybrid": len([m for m in maps if m.source_document_count > 0 and m.source_web_count > 0])
                }
            }
            
        except Exception as e:
            logger.error(f" Failed to get statistics: {e}")
            raise
