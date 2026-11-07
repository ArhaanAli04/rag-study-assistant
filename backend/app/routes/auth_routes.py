from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.services.oauth_service import get_google_oauth_client
from app.core.security import create_access_token
from app.db.database import SessionLocal, User
from app.core.config import settings
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["OAuth Authentication"])


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
        
        base_url = settings.BASE_URL
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


@router.post("/logout")
async def logout():
    """Logout endpoint (frontend clears token)"""
    return {"message": "Logged out successfully"}
