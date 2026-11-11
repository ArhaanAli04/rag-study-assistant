from sqlalchemy.orm import Session

from app.db.models import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def create_password_user(db: Session, email: str, hashed_password: str) -> User:
    user = User(email=email, hashed_password=hashed_password)
    db.add(user)
    db.flush()  # assigns user.id before the caller commits
    return user


def create_oauth_user(db: Session, email: str, name: str, picture: str | None, provider: str) -> User:
    # OAuth users have no password; username and name both start as the provider's display name.
    user = User(
        email=email,
        username=name,
        name=name,
        hashed_password=None,
        profile_picture=picture,
        oauth_provider=provider,
    )
    db.add(user)
    db.flush()
    return user
