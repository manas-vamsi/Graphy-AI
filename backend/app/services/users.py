"""Single local user bootstrap (no auth in the local-first MVP)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User

DEFAULT_EMAIL = "local@graphy.ai"


def get_default_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == DEFAULT_EMAIL))
    if user is None:
        user = User(email=DEFAULT_EMAIL, name="Local User")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
