from fastapi import APIRouter, Request, HTTPException, Depends, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Any, Dict
from app.api.deps import get_current_user, get_db
from app.schemas.auth import PasswordChange, UserCreate
from app.services.account_service import authenticate_user
from app.services.oauth_service import get_google_oauth_client
from app.core.security import create_access_token, get_password_hash, verify_password
from app.db.database import User
from app.core.config import settings
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Authentication"])


@router.post("/register")
async def register(user: UserCreate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(email=user.email, hashed_password=get_password_hash(user.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"id": new_user.id, "email": new_user.email}


@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Dict[str, str]:
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    """
    Change user password after verifying current password
    """
     # Check if user is OAuth user (no password)
    if not current_user.hashed_password or current_user.oauth_provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change password for OAuth users. Manage your password through Google."
        )

    # Verify current password
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Check if new password is same as current
    if verify_password(password_data.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )

    # Hash and update new password
    current_user.hashed_password = get_password_hash(password_data.new_password)
    db.commit()

    return {
        "message": "Password changed successfully",
        "email": current_user.email
    }


@router.get("/me")
async def read_me(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return {"id": current_user.id, "email": current_user.email}


@router.get("/auth/google/login")
async def google_login(request: Request):
    """
    Initiates Google OAuth flow.
    Redirects user to Google login page.
    """
    try:
        google = get_google_oauth_client()
        
        base_url = settings.BASE_URL
        redirect_uri = f"{base_url}/auth/google/callback"
        
        logger.info(f"Initiating Google OAuth with redirect_uri: {redirect_uri}")
        
        return await google.authorize_redirect(request, redirect_uri)
    except Exception as e:
        logger.error(f"Error in google_login: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OAuth initiation failed: {str(e)}")


@router.get("/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """
    Handles Google OAuth callback.
    Creates/updates user and returns JWT token.
    """
    try:
        google = get_google_oauth_client()
        
        # Get token from Google
        token = await google.authorize_access_token(request)
        
        # Get user info from Google
        user_info = token.get('userinfo')
        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0])
        picture = user_info.get('picture')
        
        if not email:
            raise HTTPException(status_code=400, detail="Email not provided by Google")
        
        # No identity here: the user row (and its id) isn't loaded yet, and emails stay out of logs.
        logger.info("Google OAuth callback received")
        
        # Check if user exists
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            # Create new OAuth user
            user = User(
                email=email,
                username=name,
                name=name,
                hashed_password=None,  # OAuth users don't have passwords
                profile_picture=picture,
                oauth_provider="google"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"Created new OAuth user {user.id}")
        else:
            # Update existing user info
            user.username = name
            user.name = name
            user.profile_picture = picture
            if not user.oauth_provider:
                user.oauth_provider = "google"
            db.commit()
            logger.info(f"Updated existing OAuth user {user.id}")
        
        # Create JWT token
        access_token = create_access_token(
            data={"sub": user.email},
            expires_delta=timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
        )
        
        # Redirect to frontend with token
        frontend_url = settings.FRONTEND_URL
        redirect_url = f"{frontend_url}/auth/callback?token={access_token}"
        
        # The redirect URL carries the JWT, and emails are personal data: log the id only (G8).
        logger.info(f"Redirecting user {user.id} to the frontend OAuth callback")
        
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        logger.error(f"Error in google_callback: {str(e)}", exc_info=True)
        # Redirect to frontend with error
        frontend_url = settings.FRONTEND_URL
        return RedirectResponse(url=f"{frontend_url}/login?error=oauth_failed")


@router.post("/auth/logout")
async def logout():
    """Logout endpoint (frontend clears token)"""
    return {"message": "Logged out successfully"}
