import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_services
from app.db.models import User
from app.schemas.concept_maps import (
    ConceptMapDetail,
    DeleteConceptMapResponse,
    GenerateConceptMapRequest,
    GenerateConceptMapResponse,
    ListConceptMapsResponse,
    SourceStatistics,
)
from app.services.container import Services

logger = logging.getLogger("rag_assistant.api.concepts")
router = APIRouter(prefix="/api/concepts", tags=["Concept Maps"])


@router.post("/generate", response_model=GenerateConceptMapResponse)
async def generate_concept_map(
    request: GenerateConceptMapRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    """
    Generate a new concept map

    - Retrieves context from documents and/or web
    - Extracts concepts using LLM
    - Saves to database
    - Returns structured concept map
    """
    try:
        return services.concept_map_service.generate_concept_map(
            topic=request.topic,
            user_id=current_user.id,
            db=db,
            use_documents=request.use_documents,
            use_web=request.use_web,
            max_concepts=request.max_concepts,
            max_edges=request.max_edges
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate concept map: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate concept map")


@router.get("/maps", response_model=ListConceptMapsResponse)
async def list_concept_maps(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    """
    List all concept maps for the current user

    - Ordered by creation date (newest first)
    - Includes summary information
    - Paginated results
    """
    try:
        maps = services.concept_map_service.list_user_concept_maps(
            user_id=current_user.id,
            db=db,
            limit=limit,
            offset=offset
        )

        return {
            "maps": maps,
            "total": len(maps)
        }

    except Exception as e:
        logger.error(f"Failed to list concept maps: {e}")
        raise HTTPException(status_code=500, detail="Failed to list concept maps")


@router.get("/maps/{map_id}", response_model=ConceptMapDetail)
async def get_concept_map(
    map_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    """
    Get full details of a specific concept map

    - Includes all nodes and edges
    - Includes source information
    - Verifies user ownership
    """
    try:
        concept_map = services.concept_map_service.get_concept_map_by_id(
            map_id=map_id,
            user_id=current_user.id,
            db=db
        )

        if not concept_map:
            raise HTTPException(status_code=404, detail="Concept map not found")

        return concept_map

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get concept map: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve concept map")


@router.delete("/maps/{map_id}", response_model=DeleteConceptMapResponse)
async def delete_concept_map(
    map_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    """
    Delete a concept map

    - Verifies user ownership
    - Deletes map and associated nodes
    - Returns confirmation
    """
    try:
        deleted = services.concept_map_service.delete_concept_map(
            map_id=map_id,
            user_id=current_user.id,
            db=db
        )

        if not deleted:
            raise HTTPException(status_code=404, detail="Concept map not found")

        return {
            "message": "Concept map deleted successfully",
            "map_id": map_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete concept map: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete concept map")


@router.get("/statistics", response_model=SourceStatistics)
async def get_concept_map_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    """
    Get statistics about user's concept maps

    - Total maps created
    - Source breakdown (documents vs web)
    - Average confidence scores
    - Node and edge counts
    """
    try:
        return services.concept_map_service.get_source_statistics(
            user_id=current_user.id,
            db=db
        )
    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")
