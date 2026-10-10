"""Password hashing (bcrypt) and login tokens (JWT).

- bcrypt stores a salted, slow hash, so a leaked DB doesn't reveal passwords.
- A JWT is a signed token holding the user id; the server verifies the signature
  on every request instead of keeping server-side sessions.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from ..config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    """Returns the user id, or raises jwt.InvalidTokenError."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    return int(payload["sub"])
