from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.models import User


def increment_doc_version(db: Session, user_id: int) -> int:
    """Bump the user's doc_version in SQL and return the new value.

    Not `user.doc_version += 1`: requests run in parallel threads, and two uploads that both read
    N would both write N + 1, leaving caches keyed on N + 1 that miss the second document.
    """
    return db.execute(
        update(User)
        .where(User.id == user_id)
        .values(doc_version=User.doc_version + 1)
        .returning(User.doc_version)
    ).scalar_one()


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
