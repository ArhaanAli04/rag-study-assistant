from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from services.oauth_service import get_google_oauth_client
from auth import create_access_token
from db import SessionLocal, User
from config.oauth_config import get_oauth_settings
from datetime import timedelta
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["OAuth Authentication"])
settings = get_oauth_settings()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/google/login")
async def google_login(request: Request):
    """
    Initiates Google OAuth flow.
    Redirects user to Google login page.
    """
    try:
        google = get_google_oauth_client()
        
        # ✅ Get BASE_URL from environment (dynamic for production)
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        redirect_uri = f"{base_url}/auth/google/callback"
        
        logger.info(f"Initiating Google OAuth with redirect_uri: {redirect_uri}")
        
        return await google.authorize_redirect(request, redirect_uri)
    except Exception as e:
        logger.error(f"Error in google_login: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OAuth initiation failed: {str(e)}")


@router.get("/google/callback")
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
        
        logger.info(f"Google OAuth callback for user: {email}")
        
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
            logger.info(f"Created new OAuth user: {email}")
        else:
            # Update existing user info
            user.username = name
            user.name = name
            user.profile_picture = picture
            if not user.oauth_provider:
                user.oauth_provider = "google"
            db.commit()
            logger.info(f"Updated existing user: {email}")
        
        # Create JWT token
        access_token = create_access_token(
            data={"sub": user.email},
            expires_delta=timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
        )
        
        # Redirect to frontend with token
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        redirect_url = f"{frontend_url}/auth/callback?token={access_token}"
        
        logger.info(f"Redirecting to frontend: {redirect_url}")
        
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        logger.error(f"Error in google_callback: {str(e)}", exc_info=True)
        # Redirect to frontend with error
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(url=f"{frontend_url}/login?error=oauth_failed")


@router.post("/logout")
async def logout():
    """Logout endpoint (frontend clears token)"""
    return {"message": "Logged out successfully"}
