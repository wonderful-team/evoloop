# CRUD operations are no longer needed for users as we delegate to Member Center.
# This file is kept to avoid import errors if other modules perform non-user CRUD in future.
from typing import Any
from sqlmodel import Session

# Placeholder
def create_user(*, session: Session, user_create: Any) -> Any:
    pass

def update_user(*, session: Session, db_user: Any, user_in: Any) -> Any:
    pass

def get_user_by_email(*, session: Session, email: str) -> Any | None:
    pass

def authenticate(*, session: Session, email: str, password: str) -> Any | None:
    pass
