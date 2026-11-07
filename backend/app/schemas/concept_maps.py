"""
Pydantic schemas for Concept Map API
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


class GenerateConceptMapRequest(BaseModel):
    """Request model for generating a concept map"""
    topic: str = Field(..., min_length=3, max_length=500, description="Topic for the concept map")
    use_documents: bool = Field(default=False, description="Whether to use user documents")
    use_web: bool = Field(default=True, description="Whether to use web search")
    max_concepts: int = Field(default=15, ge=5, le=30, description="Maximum number of concepts")
    max_edges: int = Field(default=20, ge=5, le=50, description="Maximum number of edges")


class ConceptNode(BaseModel):
    """A concept node"""
    id: str
    label: str
    definition: str
    source_type: str
    sources: List[str]


class ConceptEdge(BaseModel):
    """A relationship edge between concepts"""
    from_: str = Field(..., alias="from")
    to: str
    label: str
    
    class Config:
        populate_by_name = True


class SourceInfo(BaseModel):
    """Source information"""
    total: int
    documents: int
    web: int
    document_sources: Optional[List[str]] = []
    web_sources: Optional[List[str]] = []


class GenerateConceptMapResponse(BaseModel):
    """Response model for concept map generation"""
    map_id: int
    topic: str
    nodes: List[ConceptNode]
    edges: List[ConceptEdge]
    sources: SourceInfo
    metadata: Dict[str, Any]
    created_at: str


class ConceptMapSummary(BaseModel):
    """Summary of a concept map for list view"""
    id: int
    topic: str
    created_at: str
    node_count: int
    edge_count: int
    sources: Dict[str, int]
    confidence: float


class ListConceptMapsResponse(BaseModel):
    """Response model for listing concept maps"""
    maps: List[ConceptMapSummary]
    total: int


class ConceptMapDetail(BaseModel):
    """Full concept map details"""
    id: int
    topic: str
    nodes: List[ConceptNode]
    edges: List[ConceptEdge]
    metadata: Dict[str, Any]
    sources: Dict[str, int]
    created_at: str


class DeleteConceptMapResponse(BaseModel):
    """Response for delete operation"""
    message: str
    map_id: int


class SourceStatistics(BaseModel):
    """Statistics about concept map sources"""
    total_maps: int
    total_sources: Dict[str, int]
    total_nodes: int
    total_edges: int
    average_confidence: float
    maps_per_source_type: Dict[str, int]
