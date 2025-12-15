#JWT logic
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt  # pip install python-jose[cryptography]
from passlib.context import CryptContext  # pip install passlib[bcrypt]
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from error_handler import UserFriendlyError
from db import SessionLocal, User

SECRET_KEY = "CHANGE_THIS_TO_ENV_SECRET"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")  # /login endpoint [web:16][web:18]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)  # [web:10][web:16]
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=UserFriendlyError.get_message("auth_expired")['error'],
                headers={"WWW-Authenticate": "Bearer"},
            )
            
    except JWTError:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=UserFriendlyError.get_message("auth_expired")['error'],
                headers={"WWW-Authenticate": "Bearer"},
            )
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=UserFriendlyError.get_message("auth_expired")['error'],
                headers={"WWW-Authenticate": "Bearer"},
            )
    return user

# NEW: Optional auth scheme (doesn't auto-error if no token)
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

async def get_current_user_optional(
    token: str = Depends(oauth2_scheme_optional), 
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Like get_current_user, but returns None instead of raising exception
    if token is invalid or missing. Used for endpoints that accept token
    via query param (like SSE streams).
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        user = db.query(User).filter(User.email == email).first()
        return user
    except JWTError:
        return None

