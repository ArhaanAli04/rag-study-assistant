"""FastAPI dependencies: the request-scoped DB session, the current user, and the app's services."""
from typing import Iterator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.errors import UserFriendlyError
from app.core.security import decode_access_token
from app.db.models import User
from app.db.repositories import users as users_repo
from app.db.session import SessionLocal
from app.services.container import Services

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def get_db() -> Iterator[Session]:
    # Closed after the response is sent — for /chat/stream that's after the last SSE frame
    # (FastAPI >= 0.118), which matters because the stream writes the assistant message.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_services(request: Request) -> Services:
    return request.app.state.services


def _user_for_token(db: Session, token: str) -> Optional[User]:
    try:
        email = decode_access_token(token).get("sub")
    except JWTError:
        return None
    if email is None:
        return None
    return users_repo.get_by_email(db, email)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """The user from `Authorization: Bearer <JWT>`."""
    user = _user_for_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=UserFriendlyError.get_message("auth_expired")["error"],
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_user_from_query_token(token: Optional[str] = None, db: Session = Depends(get_db)) -> User:
    """The user from `?token=<JWT>`: EventSource can't send an Authorization header (SSE)."""
    user = _user_for_token(db, token) if token else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
