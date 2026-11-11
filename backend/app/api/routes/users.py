from dataclasses import asdict
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_services
from app.db.models import Document, User
from app.ingestion.upload_storage import UPLOAD_ROOT
from app.schemas.users import ProfileUpdate
from app.services.account_service import delete_user_account
from app.services.container import Services

router = APIRouter(prefix="/user", tags=["Users"])


@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    return {
        "email": current_user.email,
        "name": current_user.name if hasattr(current_user, 'name') and current_user.name else current_user.username,
        "username": current_user.username if hasattr(current_user, 'username') else "",
        "profile_picture": current_user.profile_picture if hasattr(current_user, 'profile_picture') else None,
        "oauth_provider": current_user.oauth_provider if hasattr(current_user, 'oauth_provider') else None,
        "created_at": current_user.created_at if hasattr(current_user, 'created_at') else None
    }


@router.put("/profile")
async def update_profile(
    profile: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    # Update user name
    current_user.name = profile.name
    db.commit()

    return {
        "message": "Profile updated successfully",
        "email": current_user.email,
        "name": current_user.name
    }


@router.get("/stats")
async def get_user_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get user statistics for profile"""

    # Count documents uploaded by user
    document_count = db.query(Document).filter(
        Document.user_id == str(current_user.id),
        Document.is_active == True
    ).count()

    # Get account creation date
    created_at = current_user.created_at if hasattr(current_user, 'created_at') and current_user.created_at else None

    return {
        "member_since": created_at.isoformat() if created_at else None,
        "plan": "Free",  # Can be dynamic later if you add paid plans
        "documents_uploaded": document_count,
        "documents_limit": 10,  # Free plan limit
        "email": current_user.email,
        "name": current_user.name if hasattr(current_user, 'name') else ""
    }


@router.delete("/delete")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services),
) -> Dict[str, Any]:
    summary = delete_user_account(
        db,
        current_user,
        indexes=[services.index_builder.get_index(), services.bm25_index],
        semantic_cache=services.semantic_cache,
        retrieval_cache=services.retrieval_service,
        upload_root=UPLOAD_ROOT,
    )
    return {"message": "Account deleted successfully", "deleted": asdict(summary)}
