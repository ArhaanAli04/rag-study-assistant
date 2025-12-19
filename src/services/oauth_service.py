from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from src.config.oauth_config import get_oauth_settings

settings = get_oauth_settings()

# Initialize OAuth
oauth = OAuth()

# Register Google OAuth
oauth.register(
    name='google',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
        'redirect_uri': settings.GOOGLE_REDIRECT_URI
    }
)

def get_google_oauth_client():
    """Get configured Google OAuth client"""
    return oauth.google
