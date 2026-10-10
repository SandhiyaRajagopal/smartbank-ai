"""Shared FastAPI dependencies: authentication and rate limiting (layer 2, API & experience)."""
import time
from collections import defaultdict, deque

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..auth.security import decode_token
from ..config import settings
from ..db.models import User
from ..db.session import get_db

bearer = HTTPBearer(auto_error=False)


def user_from_token(token: str, db: Session) -> User:
    try:
        user_id = decode_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session. Please log in again.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return user_from_token(creds.credentials, db)


class RateLimiter:
    """Sliding-window limit per user: protects the LLM budget from abuse or runaway clients."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[int, deque] = defaultdict(deque)

    def check(self, user_id: int) -> None:
        now = time.monotonic()
        window = self.hits[user_id]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.per_minute:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many messages - please wait a minute and try again.")
        window.append(now)


chat_limiter = RateLimiter(settings.chat_rate_limit_per_min)


def trace_id(request: Request) -> str:
    return request.state.trace_id
